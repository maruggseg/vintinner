"""
Paso 2a: Escanear zapatillas y guardar una "foto" con fecha y hora.

Ejecuta este script varias veces al día (a mano, o luego automatizado).
Cada ejecución añade una fila por cada anuncio visto a data/historial.csv,
con la fecha/hora en que lo viste. Con eso, analizar.py podrá saber
cuándo apareció un anuncio y cuándo dejó de verse (= probablemente vendido).

NO necesitas tocar nada de este archivo salvo, si quieres, PAGINAS_A_REVISAR.
"""

import csv
import os
from datetime import datetime

from vinted_api import crear_sesion_autenticada, buscar_varias_paginas

# --- CONFIGURACIÓN ---
BUSQUEDA = "zapatillas"       # barrido amplio, sin filtrar marca
PAGINAS_A_REVISAR = 3          # 3 páginas x 96 = hasta ~288 anuncios por escaneo
ARCHIVO_HISTORIAL = os.path.join("data", "historial.csv")
# ----------------------

CABECERAS = [
    "fecha_escaneo", "item_id", "titulo", "marca", "precio", "moneda",
    "favoritos", "talla", "url", "foto_url",
]


def extraer_foto_url(anuncio: dict) -> str:
    """
    Saca la URL de la foto de portada del anuncio. Vinted no siempre usa la
    misma estructura, así que probamos varias rutas posibles por si acaso.
    Solo devolvemos UNA foto (la principal), nunca la galería completa.
    """
    foto = anuncio.get("photo") or {}

    if isinstance(foto, dict):
        if foto.get("url"):
            return foto["url"]
        if foto.get("full_size_url"):
            return foto["full_size_url"]
        miniaturas = foto.get("thumbnails") or []
        if miniaturas:
            # Cogemos la miniatura de mayor resolución (suele ser la última de la lista)
            return miniaturas[-1].get("url", "")

    # Alternativa: algunos anuncios traen una lista "photos" en vez de "photo"
    fotos = anuncio.get("photos") or []
    if fotos and isinstance(fotos, list):
        primera = fotos[0]
        if isinstance(primera, dict):
            return primera.get("url") or primera.get("full_size_url", "")

    return ""


def guardar_snapshot(anuncios):
    ahora = datetime.now().isoformat(timespec="seconds")
    existe = os.path.exists(ARCHIVO_HISTORIAL)

    with open(ARCHIVO_HISTORIAL, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not existe:
            writer.writerow(CABECERAS)

        for a in anuncios:
            writer.writerow([
                ahora,
                a.get("id"),
                a.get("title"),
                (a.get("brand_title") or ""),
                a.get("price", {}).get("amount"),
                a.get("price", {}).get("currency_code"),
                a.get("favourite_count", 0),
                (a.get("size_title") or ""),
                a.get("url"),
                extraer_foto_url(a),
            ])


if __name__ == "__main__":
    print("Conectando con Vinted...")
    sesion = crear_sesion_autenticada()

    if sesion is None:
        print("No se pudo conectar. Revisa el mensaje de arriba.")
    else:
        print(f"Buscando '{BUSQUEDA}' ({PAGINAS_A_REVISAR} páginas)...")
        anuncios = buscar_varias_paginas(sesion, BUSQUEDA, PAGINAS_A_REVISAR)

        os.makedirs("data", exist_ok=True)
        guardar_snapshot(anuncios)

        con_foto = sum(1 for a in anuncios if extraer_foto_url(a))
        print(f"✅ Guardados {len(anuncios)} anuncios en {ARCHIVO_HISTORIAL} ({con_foto} con foto detectada)")
        print("Repite este escaneo varias veces al día durante unos días.")
        print("Cuantos más escaneos acumules, mejor funcionará analizar.py")
