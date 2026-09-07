"""
results_checker.py — Verifica el resultado REAL de los partidos (vía
TheStatsAPI) para resolver automáticamente las señales pendientes, sin
depender de que el canal publique su propio resumen ni de hacerlo a mano.

NOTA: TheStatsAPI da un trial gratis de 7 días; después cobra desde
$50 USD/mes. Si decides no pagar, este módulo simplemente deja de poder
verificar (la app sigue funcionando igual, solo hay que resolver a mano
desde el dashboard).

Flujo:
1. Toma las señales pendientes cuyo evento ya debería haber terminado
   (fecha_evento + margen de 3 horas en el pasado).
2. Busca el partido correspondiente en TheStatsAPI por fecha + nombres
   de equipo (con matching aproximado, ya que los nombres del canal no
   siempre coinciden exactamente con los oficiales).
3. Si el partido ya terminó (status 'finished'), aplica la regla del
   mercado (G1, G2, 1X, X2, Total más/menos de N) sobre el marcador real.
4. Resuelve la señal en la base de datos con el resultado correcto.

Mercados que NO se resuelven automáticamente (quedan pendientes para
resolver a mano): hándicaps con línea, mercados de córners/tarjetas,
o cualquier mercado que este módulo no reconozca -- mejor dejarlos
pendientes que arriesgar un cálculo incorrecto.
"""
import os
import re
import logging
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

import requests

import db

log = logging.getLogger("results-checker")

API_KEY = os.environ.get("STATS_API_KEY")
API_BASE = "https://api.thestatsapi.com/api"
HEADERS = {"Authorization": f"Bearer {API_KEY}"} if API_KEY else {}

# Margen tras la hora de inicio del evento antes de intentar buscar el
# resultado (para dar tiempo a que el partido termine)
MARGEN_HORAS = 3


def _normalize(name: str) -> str:
    if not name:
        return ""
    name = name.lower().strip()
    for a, b in [("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"), ("ñ", "n")]:
        name = name.replace(a, b)
    # Quita sufijos comunes que difieren entre canal y API
    for palabra in ["fc", "cf", "sc", "de", "club", "atletico", "deportivo"]:
        name = re.sub(rf"\b{palabra}\b", "", name)
    return re.sub(r"\s+", " ", name).strip()


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


def _infer_event_datetime(fecha_evento: str, fecha_publicacion_iso: str) -> datetime | None:
    """
    fecha_evento viene como 'DD.MM HH:MM' sin año. Se infiere el año a
    partir de fecha_publicacion (cuándo se capturó la señal).
    """
    if not fecha_evento:
        return None
    try:
        dia_mes, hora = fecha_evento.split(" ")
        dia, mes = dia_mes.split(".")
        pub_dt = datetime.fromisoformat(fecha_publicacion_iso)
        anio = pub_dt.year
        evento_dt = datetime(anio, int(mes), int(dia), *map(int, hora.split(":")), tzinfo=timezone.utc)
        # Si el evento "quedó" muy en el futuro respecto a la publicación
        # (ej. se publicó en diciembre para un evento de enero), es del año siguiente
        if evento_dt < pub_dt - timedelta(days=180):
            evento_dt = evento_dt.replace(year=anio + 1)
        return evento_dt
    except (ValueError, IndexError):
        return None


def _fetch_fixtures_by_date(date_str: str) -> list[dict]:
    """date_str en formato YYYY-MM-DD. Devuelve la lista de partidos finalizados de ese día."""
    try:
        resp = requests.get(
            f"{API_BASE}/football/matches",
            headers=HEADERS,
            params={
                "date_from": date_str,
                "date_to": date_str,
                "status": "finished",
                "per_page": 100,
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("data", [])
    except requests.RequestException as e:
        log.warning(f"Error consultando TheStatsAPI: {e}")
        return []


def _find_matching_fixture(fixtures: list[dict], local: str, visitante: str, umbral: float = 0.55):
    """Busca el partido cuyo home/away se parezca más a los nombres del canal."""
    mejor = None
    mejor_score = 0.0
    for fx in fixtures:
        home = fx["home_team"]["name"]
        away = fx["away_team"]["name"]
        score = (_similar(local, home) + _similar(visitante, away)) / 2
        # También probar cruzado por si el canal invirtió local/visitante
        score_cruzado = (_similar(local, away) + _similar(visitante, home)) / 2
        score = max(score, score_cruzado)
        if score > mejor_score:
            mejor_score = score
            mejor = fx
    if mejor_score >= umbral:
        return mejor
    return None


def _evaluar_mercado(mercado: str, goles_local: int, goles_visitante: int) -> bool | None:
    """
    Devuelve True (ganó), False (perdió), o None (mercado no soportado,
    no tocar la señal).
    """
    if mercado is None:
        return None
    m = mercado.strip().upper()

    if m in ("G1", "1"):
        return goles_local > goles_visitante
    if m in ("G2", "2"):
        return goles_visitante > goles_local
    if m in ("1X", "X1"):
        return goles_local >= goles_visitante
    if m in ("2X", "X2"):
        return goles_visitante >= goles_local
    if m == "X":
        return goles_local == goles_visitante

    total_match = re.match(r"TOTAL\s+MENOS\s+DE\s*\(?([\d.,]+)\)?", m)
    if total_match:
        linea = float(total_match.group(1).replace(",", "."))
        return (goles_local + goles_visitante) < linea

    total_match = re.match(r"TOTAL\s+M[ÁA]S\s+DE\s*\(?([\d.,]+)\)?", m)
    if total_match:
        linea = float(total_match.group(1).replace(",", "."))
        return (goles_local + goles_visitante) > linea

    # Hándicaps, córners, tarjetas, etc. -- no soportado, dejar pendiente
    return None


def check_pending_signals():
    """
    Recorre las señales pendientes con evento ya terminado y trata de
    resolverlas contra resultados reales. Devuelve un resumen de lo que hizo.
    """
    if not API_KEY:
        log.warning("Falta STATS_API_KEY -- no se puede verificar resultados automáticamente.")
        return

    ahora = datetime.now(timezone.utc)
    signals = db.get_all_signals()
    pendientes = [s for s in signals if s["estado"] == "pendiente" and s["cuota"]]

    fixtures_cache = {}  # date_str -> lista de partidos, para no repetir requests

    for s in pendientes:
        evento_dt = _infer_event_datetime(s["fecha_evento"], s["fecha_publicacion"])
        if evento_dt is None:
            continue
        if ahora < evento_dt + timedelta(hours=MARGEN_HORAS):
            continue  # el partido probablemente no ha terminado aún

        date_str = evento_dt.strftime("%Y-%m-%d")
        if date_str not in fixtures_cache:
            fixtures_cache[date_str] = _fetch_fixtures_by_date(date_str)
        fixtures = fixtures_cache[date_str]

        fixture = _find_matching_fixture(fixtures, s["equipo_local"], s["equipo_visitante"])
        if fixture is None:
            log.info(f"Señal #{s['id']}: no se encontró el partido en TheStatsAPI todavía.")
            continue

        if fixture.get("status") != "finished":
            log.info(f"Señal #{s['id']}: partido encontrado pero aún no finalizado (status={fixture.get('status')}).")
            continue

        goles_local_api = fixture["score"]["home"]
        goles_visit_api = fixture["score"]["away"]
        # Si el canal tenía local/visitante invertidos respecto a la API, hay que voltear el marcador
        cruzado = _similar(s["equipo_local"], fixture["away_team"]["name"]) > \
            _similar(s["equipo_local"], fixture["home_team"]["name"])
        if cruzado:
            goles_local_api, goles_visit_api = goles_visit_api, goles_local_api

        gano = _evaluar_mercado(s["mercado"], goles_local_api, goles_visit_api)
        if gano is None:
            log.info(f"Señal #{s['id']}: mercado '{s['mercado']}' no soportado para auto-resolución.")
            continue

        resultado = "ganada" if gano else "perdida"
        db.resolve_by_id(s["id"], resultado)
        log.info(
            f"Señal #{s['id']} resuelta automáticamente vía API: "
            f"{s['equipo_local']} {goles_local_api}-{goles_visit_api} {s['equipo_visitante']} "
            f"-> mercado '{s['mercado']}' = {resultado}"
        )
