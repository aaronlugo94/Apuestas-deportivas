"""
main.py — Loop principal del worker.
Corre en Railway como proceso tipo 'worker' (sin puerto HTTP).
"""
import os
import time
import logging

from scraper import fetch_messages
from filters import is_real_signal, is_daily_summary, parse_signal, parse_daily_results, message_hash
from notifier import send_signal
import db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("signal-bot")

POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", "180"))  # 3 min default
DEFAULT_STAKE_UNIDADES = float(os.environ.get("DEFAULT_STAKE_UNIDADES", "1"))
DEBUG_MODE = os.environ.get("DEBUG_MODE", "false").lower() == "true"


def process_once():
    messages = fetch_messages()
    log.info(f"Obtenidos {len(messages)} mensajes del canal.")

    if DEBUG_MODE and messages:
        log.info(f"[DEBUG] IDs más recientes: {[m['id'] for m in messages[:5]]}")
        log.info(f"[DEBUG] Texto del más reciente:\n{messages[0]['text'][:500]}")

    for msg in messages:
        msg_id = msg["id"] or message_hash(msg["text"])
        text = msg["text"]

        if db.signal_exists(msg_id):
            continue

        if DEBUG_MODE and "cuota" in text.lower() and not is_real_signal(text):
            log.info(f"[DEBUG] Mensaje con 'cuota' pero NO paso el filtro (id={msg_id}):\n{text[:500]}")

        if is_real_signal(text):
            parsed = parse_signal(text, msg_id)
            if parsed and parsed["cuota"]:
                db.insert_signal(
                    raw_message_id=parsed["raw_message_id"],
                    fecha_evento=parsed["fecha_evento"],
                    equipo_local=parsed["equipo_local"],
                    equipo_visitante=parsed["equipo_visitante"],
                    mercado=parsed["mercado"],
                    cuota=parsed["cuota"],
                    stake_unidades=DEFAULT_STAKE_UNIDADES,
                )
                send_signal(parsed, parsed["cuota"])
                log.info(f"Nueva señal guardada y enviada: {parsed}")
            else:
                # Marca como "vista" igual para no reintentar, aunque no se haya podido parsear bien
                db.insert_signal(msg_id, None, None, None, None, 0, 0)
                log.warning(f"Señal detectada pero no se pudo parsear completamente: {msg_id}")

        elif is_daily_summary(text):
            results = parse_daily_results(text)
            for cuota, estado in results:
                updated = db.resolve_pending_by_cuota(cuota, estado)
                if updated:
                    log.info(f"Resuelta señal con cuota {cuota} -> {estado}")
                else:
                    log.info(f"No se encontró señal pendiente para cuota {cuota}")
            # Guardamos el resumen también como "visto" para no reprocesarlo
            db.insert_signal(msg_id, None, None, None, None, 0, 0)


def main():
    db.init_db()
    log.info("Bot iniciado. Polling cada %s segundos.", POLL_INTERVAL_SECONDS)
    while True:
        try:
            process_once()
        except Exception as e:
            log.exception(f"Error en el ciclo principal: {e}")
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
