"""
Módulo compartido: enviar mensajes por Telegram.

Lo usan prueba_telegram.py y alertas.py. No hace falta tocar este archivo.
"""

import requests
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID


def enviar_mensaje(texto: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": texto,
        "disable_web_page_preview": True,
    }

    resp = requests.post(url, data=payload, timeout=10)

    if resp.status_code != 200:
        print(f"⚠️ Error al enviar a Telegram ({resp.status_code}): {resp.text}")
        return False

    return True


def obtener_mensajes_nuevos(offset: int = 0):
    """Devuelve los mensajes recibidos por el bot desde el último 'offset' visto."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    params = {"offset": offset, "timeout": 0}

    resp = requests.get(url, params=params, timeout=10)
    if resp.status_code != 200:
        print(f"⚠️ Error al consultar Telegram ({resp.status_code}): {resp.text}")
        return []

    return resp.json().get("result", [])
