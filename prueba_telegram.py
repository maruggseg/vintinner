"""
Prueba rápida: manda un mensaje de prueba a tu Telegram.

Ejecuta esto después de rellenar config.py con tu TOKEN y CHAT_ID.
Si todo va bien, te llegará un mensaje al móvil en segundos.
"""

from telegram_bot import enviar_mensaje

if __name__ == "__main__":
    ok = enviar_mensaje("🤖 ¡Funciona! Este es un mensaje de prueba de tu bot de Vinted.")
    if ok:
        print("✅ Mensaje enviado. Revisa tu Telegram.")
    else:
        print("❌ Algo falló, mira el error de arriba.")
