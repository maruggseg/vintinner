"""
Consulta bajo demanda: escríbele /resumen a tu bot en Telegram y, la próxima
vez que este script se ejecute (programado cada pocos minutos), te contestará
con fotos de los productos top y el ranking de marcas.

Guarda en data/telegram_offset.txt cuál fue el último mensaje que ya procesó,
para no contestar dos veces al mismo mensaje ni reenviar mensajes viejos.
"""

import os
from telegram_bot import obtener_mensajes_nuevos
from analizar import ARCHIVO_HISTORIAL, cargar_historial, analizar_interes
from alertas import enviar_resumen_telegram, enviar_top_racha_telegram

ARCHIVO_OFFSET = os.path.join("data", "telegram_offset.txt")


def leer_offset():
    if os.path.exists(ARCHIVO_OFFSET):
        with open(ARCHIVO_OFFSET, "r") as f:
            contenido = f.read().strip()
            return int(contenido) if contenido else 0
    return 0


def guardar_offset(offset: int):
    os.makedirs("data", exist_ok=True)
    with open(ARCHIVO_OFFSET, "w") as f:
        f.write(str(offset))


if __name__ == "__main__":
    offset = leer_offset()
    mensajes = obtener_mensajes_nuevos(offset)

    if not mensajes:
        print("Sin mensajes nuevos.")
    else:
        max_update_id = offset
        for m in mensajes:
            max_update_id = max(max_update_id, m["update_id"] + 1)
            mensaje_obj = m.get("message", {})
            texto = mensaje_obj.get("text", "").strip().lower()
            chat_id_origen = mensaje_obj.get("chat", {}).get("id")

            if texto in ("/resumen", "/start", "resumen"):
                print(f"Comando recibido de {chat_id_origen}: {texto}. Generando resumen...")
                if not os.path.exists(ARCHIVO_HISTORIAL):
                    from telegram_bot import enviar_mensaje
                    enviar_mensaje("Todavía no hay ningún escaneo guardado.", chat_id=chat_id_origen)
                else:
                    filas = cargar_historial()
                    resultados, escaneos = analizar_interes(filas)
                    enviar_resumen_telegram(resultados, escaneos, chat_id=chat_id_origen)
            elif texto in ("/top", "top"):
                print(f"Comando recibido de {chat_id_origen}: {texto}. Generando top de racha...")
                if not os.path.exists(ARCHIVO_HISTORIAL):
                    from telegram_bot import enviar_mensaje
                    enviar_mensaje("Todavía no hay ningún escaneo guardado.", chat_id=chat_id_origen)
                else:
                    filas = cargar_historial()
                    enviar_top_racha_telegram(filas, chat_id=chat_id_origen, dias=7)
            else:
                print(f"Mensaje ignorado (no es un comando reconocido): {texto!r}")

        guardar_offset(max_update_id)
        print("✅ Offset actualizado.")
