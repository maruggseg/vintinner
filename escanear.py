"""
Paso 2a: Escanear zapatillas y guardar una "foto" con fecha y hora.

Ejecuta este script varias veces al día (a mano, o automatizado).
Cada ejecución añade una fila por cada anuncio visto a data/historial.csv,
con la fecha/hora en que lo viste. Con eso, analizar.py podrá saber
cuándo apareció un anuncio y cuándo dejó de verse.
"""

import csv
import os
from datetime import datetime, timedelta

from vinted_api import crear_sesion_autenticada, buscar_categoria_varias_paginas

# --- CONFIGURACIÓN ---
CATALOG_IDS = "2632"            # Zapatillas MUJER (Vinted) — antes incluía también 1242 (hombre)
PRECIO_DESDE = 70               # solo traemos anuncios que ya cumplen el mínimo de precio
PAGINAS_A_REVISAR = 3           # 3 páginas x 96 = hasta ~288 anuncios por escaneo
ARCHIVO_HISTORIAL = os.path.join("data", "historial.csv")

# Con escaneos cada 10 min (288 filas/escaneo) el historial crece ~11MB/día.
# Sin podar, llegaría al límite de 100MB de GitHub por archivo en menos de
# una semana y el "git push" del workflow empezaría a fallar. Ningún análisis
# actual mira más allá de 7 días (ver EDAD_MAXIMA_DIAS en alertas.py), así
# que podamos exactamente a esa ventana.
RETENCION_DIAS = 7
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
            return miniaturas[-1].get("url", "")

    fotos = anuncio.get("photos") or []
    if fotos and isinstance(fotos, list):
        primera = fotos[0]
        if isinstance(primera, dict):
            return primera.get("url") or primera.get("full_size_url", "")

    return ""


def url_completa(anuncio: dict) -> str:
    """
    Desde el cambio de API de Vinted, el campo "url" del anuncio ya no viene
    absoluto (https://www.vinted.es/items/...), sino como ruta relativa
    (/items/...). Completamos el dominio si hace falta.
    """
    url = anuncio.get("url") or ""
    if not url:
        return ""
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return f"https://www.vinted.es{url}" if url.startswith("/") else f"https://www.vinted.es/{url}"


def extraer_marca(anuncio: dict) -> str:
    """
    El campo suelto "brand_title" desapareció del nuevo API de Vinted; ahora
    la marca viene dentro de item_box.first_line (verificado contra
    accessibility_label, que la repite tal cual como "Marque: <marca>").
    """
    item_box = anuncio.get("item_box") or {}
    return item_box.get("first_line") or ""


def extraer_talla(anuncio: dict) -> str:
    """
    "size_title" también desapareció; item_box.second_line combina talla y
    estado del artículo separados por " · " (ej. "41.5 · Très bon état").
    Nos quedamos solo con la talla.
    """
    item_box = anuncio.get("item_box") or {}
    segunda_linea = item_box.get("second_line") or ""
    return segunda_linea.split("·")[0].strip()


def guardar_snapshot(anuncios):
    """
    Devuelve (guardados, con_foto): cuántos anuncios se escribieron y
    cuántos de esos traían foto. Guardamos todos, sea cual sea su moneda
    (se ve en el CSV en la columna "moneda") — filtrar por EUR aquí es
    peligroso: Vinted decide en qué moneda mostrar cada anuncio según la IP
    de quien pregunta, y la IP de los runners de GitHub Actions hace que
    a veces TODO el lote venga en USD aunque sea el mercado español.
    """
    ahora = datetime.now().isoformat(timespec="seconds")
    existe = os.path.exists(ARCHIVO_HISTORIAL)

    guardados = 0
    con_foto = 0
    with open(ARCHIVO_HISTORIAL, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not existe:
            writer.writerow(CABECERAS)

        for a in anuncios:
            precio = a.get("price") or {}
            foto_url = extraer_foto_url(a)
            writer.writerow([
                ahora,
                a.get("id"),
                a.get("title"),
                extraer_marca(a),
                precio.get("amount"),
                precio.get("currency_code"),
                a.get("favourite_count", 0),
                extraer_talla(a),
                url_completa(a),
                foto_url,
            ])
            guardados += 1
            if foto_url:
                con_foto += 1

    return guardados, con_foto


def podar_historial_antiguo() -> int:
    """Elimina del CSV las filas de más de RETENCION_DIAS. Devuelve cuántas se quitaron."""
    if not os.path.exists(ARCHIVO_HISTORIAL):
        return 0

    limite = datetime.now() - timedelta(days=RETENCION_DIAS)

    with open(ARCHIVO_HISTORIAL, newline="", encoding="utf-8") as f:
        lector = csv.reader(f)
        cabecera = next(lector)
        todas = list(lector)

    filas_recientes = [fila for fila in todas if datetime.fromisoformat(fila[0]) >= limite]
    eliminadas = len(todas) - len(filas_recientes)
    if eliminadas <= 0:
        return 0

    archivo_temporal = ARCHIVO_HISTORIAL + ".tmp"
    with open(archivo_temporal, "w", newline="", encoding="utf-8") as f:
        escritor = csv.writer(f)
        escritor.writerow(cabecera)
        escritor.writerows(filas_recientes)
    os.replace(archivo_temporal, ARCHIVO_HISTORIAL)

    return eliminadas


if __name__ == "__main__":
    print("Conectando con Vinted...")
    sesion = crear_sesion_autenticada()

    if sesion is None:
        print("No se pudo conectar. Revisa el mensaje de arriba.")
    else:
        print(f"Buscando categoría Zapatillas (mujer), ≥{PRECIO_DESDE}€ ({PAGINAS_A_REVISAR} páginas)...")
        anuncios = buscar_categoria_varias_paginas(sesion, CATALOG_IDS, PAGINAS_A_REVISAR, precio_desde=PRECIO_DESDE)

        os.makedirs("data", exist_ok=True)
        guardados, con_foto = guardar_snapshot(anuncios)
        eliminadas = podar_historial_antiguo()

        print(f"✅ Guardados {guardados} anuncios en {ARCHIVO_HISTORIAL} ({con_foto} con foto detectada)")
        if eliminadas:
            print(f"🧹 Podadas {eliminadas} filas de más de {RETENCION_DIAS} días")
