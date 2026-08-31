"""
scraper.py — Descarga y parsea el preview web público de un canal de Telegram
(https://t.me/s/<canal>), sin necesidad de login ni API_ID/API_HASH.
"""
import os
import requests
from bs4 import BeautifulSoup

CHANNEL_USERNAME = os.environ.get("SOURCE_CHANNEL", "Apuestas_Deportivas_Futbo")
BASE_URL = f"https://t.me/s/{CHANNEL_USERNAME}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    # El preview web de Telegram se cachea agresivamente en su CDN;
    # estos headers ayudan a reducir (no garantizan eliminar) ese caché.
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


def fetch_messages(url: str = BASE_URL) -> list[dict]:
    """
    Devuelve una lista de mensajes recientes del canal:
    [{"id": "123", "text": "...", "date": "..."}]
    El preview web solo trae ~20 mensajes más recientes por request;
    para el propósito de este bot (polling frecuente) es suficiente.
    """
    # Cache-busting adicional por querystring, por si el CDN ignora los headers
    import time
    resp = requests.get(url, headers=HEADERS, params={"_": int(time.time())}, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    messages = []
    for wrap in soup.select("div.tgme_widget_message_wrap"):
        msg_div = wrap.select_one("div.tgme_widget_message")
        if not msg_div:
            continue
        msg_id = msg_div.get("data-post", "")  # ej. "canal/123"

        # Junta TODO el texto visible del mensaje, incluyendo el bloque de
        # "reply" (cuando el cupón viene como respuesta a otro mensaje, como
        # el "Video message" que se ve en el canal) -- antes solo tomábamos
        # tgme_widget_message_text, que puede excluir el texto del cupón si
        # está en un bloque separado.
        text_parts = []
        for sel in ("div.tgme_widget_message_reply", "div.tgme_widget_message_text"):
            for el in msg_div.select(sel):
                t = el.get_text(separator="\n").strip()
                if t:
                    text_parts.append(t)
        text = "\n".join(text_parts)

        time_tag = msg_div.select_one("time")
        date = time_tag.get("datetime") if time_tag else None

        if text:
            messages.append({"id": msg_id, "text": text, "date": date})

    return messages


if __name__ == "__main__":
    for m in fetch_messages():
        print("---", m["id"], m["date"])
        print(m["text"][:200])

