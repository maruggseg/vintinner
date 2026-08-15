"""
Consulta bajo demanda: escríbele /resumen a tu bot en Telegram y, la próxima
vez que este script se ejecute (programado cada pocos minutos), te contestará
con el resumen de tendencias actual.

Guarda en data/telegram_offset.txt cuál fue el último mensaje que ya procesó,
para no contestar dos veces al mismo mensaje ni reenviar mensajes viejos.
"""

import os
from telegram_bot import obtener_mensajes_nuevos, enviar_mensaje
from analizar import ARCHIVO_HISTORIAL, cargar_historial, analizar
from alertas import construir_mensaje

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


def generar_resumen_actual():
    if not os.path.exists(ARCHIVO_HISTORIAL):
        return "Todavía no hay ningún escaneo guardado. Espera al próximo escaneo automático."
    filas = cargar_historial()
    resultados, escaneos = analizar(filas)
    return construir_mensaje(resultados, escaneos)


if __name__ == "__main__":
    offset = leer_offset()
    mensajes = obtener_mensajes_nuevos(offset)

    if not mensajes:
        print("Sin mensajes nuevos.")
    else:
        max_update_id = offset
        for m in mensajes:
            max_update_id = max(max_update_id, m["update_id"] + 1)
            texto = m.get("message", {}).get("text", "").strip().lower()

            if texto in ("/resumen", "/start", "resumen"):
                print(f"Comando recibido: {texto}. Generando resumen...")
                resumen = generar_resumen_actual()
                enviar_mensaje(resumen)
            else:
                print(f"Mensaje ignorado (no es un comando reconocido): {texto!r}")

        guardar_offset(max_update_id)
        print("✅ Offset actualizado.")
