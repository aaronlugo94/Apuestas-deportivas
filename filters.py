"""
filters.py — Detecta si un mensaje del canal es una señal real de apuesta
vs. ruido (promos de 1XBET, publicidad de VIP, videos, resúmenes diarios).

IMPORTANTE: el cupón visual (con "Cuota:", "Apuesta:", "Posibles
ganancias:", "Estado:") es una IMAGEN adjunta al mensaje, no texto -- el
scraper solo lee el caption/texto del mensaje, que trae un formato
distinto y más suelto, típicamente así:

    1.69
    Futebol🥅Colombia. Categoria Primera A
    Deportivo Pasto - Deportivo Pereira
    ➡️ Total menos de (2.5)
    📅31.08 20:00
    🔗 Apuesta aquí➡️1XBET
    🎁 Usa el código promocional HUGO500
    ✉️ Contacto @HugoLucky

Este módulo parsea ESE formato (el real del caption), no el de la imagen.
"""
import re
import hashlib

# Marcador más confiable de un cupón real: siempre presente en los picks
# reales, nunca en promos puras ni en captions de video.
SIGNAL_FOOTER_MARKER = "apuesta aquí"

# Mensajes que traen esto son puro resumen diario, no un pick nuevo
DAILY_SUMMARY_MARKER = "resultado de hoy"

# Línea "Equipo A - Equipo B" (sin fecha pegada, a diferencia del texto de la imagen)
TEAM_LINE_RE = re.compile(
    r"^(?P<local>[\wÁÉÍÓÚÑáéíóúñ .]{3,40}?)\s*[-–]\s*(?P<visitante>[\wÁÉÍÓÚÑáéíóúñ .]{3,40})$",
    re.MULTILINE,
)
# Primera línea "sola" del mensaje: la cuota, tipo "1.69" o "1,69"
CUOTA_LINE_RE = re.compile(r"^\s*(\d{1,2}[.,]\d{1,3})\s*$", re.MULTILINE)
# Línea de mercado, empieza con la flecha
MERCADO_RE = re.compile(r"➡️\s*([^\n]+)")
# Fecha del evento, tipo "28.08 21:30" o "31.08 20:00"
FECHA_RE = re.compile(r"\b(\d{1,2}\.\d{1,2}\s+\d{1,2}:\d{2})\b")


def is_real_signal(text: str) -> bool:
    """
    True si el mensaje trae el footer característico de un cupón real
    ("Apuesta aquí"), que no aparece en promos puras ni en captions de video.
    """
    if not text:
        return False
    return SIGNAL_FOOTER_MARKER in text.lower()


def is_daily_summary(text: str) -> bool:
    """True si el mensaje es el resumen tipo 'Resultado de hoy: 1.64 ✅ / 1.66 ❌...'"""
    if not text:
        return False
    return DAILY_SUMMARY_MARKER in text.lower()


def parse_signal(text: str, message_id: str) -> dict | None:
    """
    Extrae los campos relevantes de un cupón real del CAPTION (no de la imagen).
    Devuelve None si no logra extraer lo mínimo (cuota + equipos).
    """
    cuota = None
    cuota_match = CUOTA_LINE_RE.search(text)
    if cuota_match:
        try:
            cuota = float(cuota_match.group(1).replace(",", "."))
        except ValueError:
            cuota = None

    equipo_local, equipo_visitante = None, None
    for m in TEAM_LINE_RE.finditer(text):
        local, visit = m.group("local").strip(), m.group("visitante").strip()
        if len(local) > 2 and len(visit) > 2 and not local.isdigit():
            equipo_local, equipo_visitante = local, visit
            break

    if cuota is None or equipo_local is None:
        return None

    mercado_match = MERCADO_RE.search(text)
    mercado = mercado_match.group(1).strip() if mercado_match else None

    fecha_match = FECHA_RE.search(text)
    fecha_evento = fecha_match.group(1) if fecha_match else None

    return {
        "raw_message_id": message_id,
        "fecha_evento": fecha_evento,
        "equipo_local": equipo_local,
        "equipo_visitante": equipo_visitante,
        "mercado": mercado,
        "cuota": cuota,
    }


def parse_daily_results(text: str) -> list[tuple[float, str]]:
    """
    Parsea el resumen diario tipo:
        1.64 ✅
        1.66 ❌
        1.96 ❌
    Devuelve lista de tuplas (cuota, 'ganada'|'perdida').
    """
    results = []
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r"^([\d.,]+)\s*([✅❌✔️❎])", line)
        if not m:
            continue
        try:
            cuota = float(m.group(1).replace(",", "."))
        except ValueError:
            continue
        estado = "ganada" if m.group(2) in ("✅", "✔️") else "perdida"
        results.append((cuota, estado))
    return results


def message_hash(text: str, msg_id: str = "") -> str:
    """Genera un id estable para deduplicar (por si el scraping no trae id real)."""
    base = (msg_id + "|" + (text or "")).encode("utf-8")
    return hashlib.sha256(base).hexdigest()[:16]
