"""
notifier.py — Envía las señales filtradas a tu propio canal/chat de Telegram
usando un bot normal (Bot API), creado con @BotFather.
"""
import os
import requests

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")  # tu canal destino, ej. "@mi_canal_filtrado"

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"


def send_signal(parsed: dict, cuota: float):
    if not BOT_TOKEN or not CHAT_ID:
        print("[notifier] Falta TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID, no se envía.")
        return

    local = parsed.get("equipo_local") or "?"
    visitante = parsed.get("equipo_visitante") or "?"
    mercado = parsed.get("mercado") or "?"
    fecha = parsed.get("fecha_evento") or "?"

    text = (
        f"📡 Señal detectada\n\n"
        f"{local} vs {visitante}\n"
        f"Mercado: {mercado}\n"
        f"Cuota: {cuota}\n"
        f"Fecha evento: {fecha}"
    )

    try:
        r = requests.post(API_URL, json={"chat_id": CHAT_ID, "text": text}, timeout=10)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"[notifier] Error enviando mensaje: {e}")
