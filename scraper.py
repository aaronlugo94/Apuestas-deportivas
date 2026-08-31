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
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}


def fetch_messages(url: str = BASE_URL) -> list[dict]:
    """
    Devuelve una lista de mensajes recientes del canal:
    [{"id": "123", "text": "...", "date": "..."}]
    El preview web solo trae ~20 mensajes más recientes por request;
    para el propósito de este bot (polling frecuente) es suficiente.
    """
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    messages = []
    for wrap in soup.select("div.tgme_widget_message_wrap"):
        msg_div = wrap.select_one("div.tgme_widget_message")
        if not msg_div:
            continue
        msg_id = msg_div.get("data-post", "")  # ej. "canal/123"

        text_div = msg_div.select_one("div.tgme_widget_message_text")
        text = text_div.get_text(separator="\n").strip() if text_div else ""

        time_tag = msg_div.select_one("time")
        date = time_tag.get("datetime") if time_tag else None

        if text:
            messages.append({"id": msg_id, "text": text, "date": date})

    return messages


if __name__ == "__main__":
    for m in fetch_messages():
        print("---", m["id"], m["date"])
        print(m["text"][:200])
