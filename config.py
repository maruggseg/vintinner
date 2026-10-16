"""
Configuración del proyecto.

Funciona en dos modos:
- En tu PC: si rellenas TELEGRAM_TOKEN y TELEGRAM_CHAT_ID aquí abajo, se usan esos.
- En GitHub Actions: se leen automáticamente de los "Secrets" del repositorio
  (así el token no queda visible en el código que subes a internet).
"""

import os

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "PEGA_AQUI_TU_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "PEGA_AQUI_TU_CHAT_ID")
