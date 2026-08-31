"""
filters.py — Detecta si un mensaje del canal es una señal real de apuesta
(cupón con Cuota/Apuesta/Posibles ganancias + equipos) vs. ruido
(promos de 1XBET, publicidad de VIP, videos, resúmenes diarios, etc.)
"""
import re
import hashlib

# Patrones clave que indican un cupón real de apuesta
SIGNAL_MARKERS = ["cuota:", "apuesta:", "posibles ganancias:", "estado:"]

# Palabras que indican que es puro ruido/promo, aunque coincida algo arriba
NOISE_MARKERS = [
    "código promocional", "codigo promocional", "app store", "google play",
    "bonificación", "bonificacion", "grupo vip", "suscripción vip",
    "suscripcion vip", "comprar subscripción", "comprar suscripción",
    "contacto @hugolucky", "resultado de hoy", "estadísticas del canal",
    "estadisticas del canal",
]

TEAM_LINE_RE = re.compile(
    r"^(?P<local>[\wÁÉÍÓÚÑáéíóúñ .]+?)\s*[-–]\s*(?P<visitante>[\wÁÉÍÓÚÑáéíóúñ .]+)$",
    re.MULTILINE,
)
CUOTA_RE = re.compile(r"cuota:\s*([\d.,]+)", re.IGNORECASE)
MERCADO_RE = re.compile(r"(?:➡️|->|\bG1\b|\bG2\b|\bHándicap\b|\bHandicap\b)[^\n]*", re.IGNORECASE)
FECHA_RE = re.compile(r"\b\d{1,2}\.\d{1,2}\s+\d{1,2}:\d{2}\b")


def is_real_signal(text: str) -> bool:
    """
    True si el mensaje parece un cupón real de apuesta.

    Nota: los cupones reales de este canal casi siempre vienen acompañados
    del pie promocional (código HUGO500, contacto @HugoLucky, etc.), así
    que NO usamos NOISE_MARKERS para descartar aquí -- eso descartaría
    también los cupones reales. NOISE_MARKERS se usa solo para distinguir
    promos puras que no traen ningún dato de cupón.
    """
    if not text:
        return False
    lower = text.lower()
    return all(m in lower for m in SIGNAL_MARKERS)


def is_daily_summary(text: str) -> bool:
    """True si el mensaje es el resumen tipo 'Resultado de hoy: 1.64 ✅ / 1.66 ❌...'"""
    if not text:
        return False
    lower = text.lower()
    return "resultado de hoy" in lower


def parse_signal(text: str, message_id: str) -> dict | None:
    """
    Extrae los campos relevantes de un cupón real.
    Devuelve None si no logra extraer lo mínimo (cuota + equipos).
    """
    cuota_match = CUOTA_RE.search(text)
    if not cuota_match:
        return None
    try:
        cuota = float(cuota_match.group(1).replace(",", "."))
    except ValueError:
        return None

    equipo_local, equipo_visitante = None, None
    for m in TEAM_LINE_RE.finditer(text):
        local, visit = m.group("local").strip(), m.group("visitante").strip()
        # Evita capturar líneas que no son de equipos (muy cortas o con números sueltos)
        if len(local) > 2 and len(visit) > 2 and not local.isdigit():
            equipo_local, equipo_visitante = local, visit
            break

    mercado_match = MERCADO_RE.search(text)
    mercado = mercado_match.group(0).strip() if mercado_match else None

    fecha_match = FECHA_RE.search(text)
    fecha_evento = fecha_match.group(0) if fecha_match else None

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
