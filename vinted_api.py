"""
Módulo compartido: conexión a Vinted.

Lo usan tanto escanear.py como (en el futuro) el bot de Telegram.
No hay que tocar nada de este archivo.
"""

import requests

DOMINIO = "www.vinted.es"  # cambia si usas vinted.com, vinted.fr, etc.

HEADERS_BASE = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}


def crear_sesion_autenticada():
    """Visita la portada de Vinted para obtener cookies + token de sesión válidos."""
    sesion = requests.Session()
    sesion.headers.update(HEADERS_BASE)

    resp = sesion.get(f"https://{DOMINIO}/", timeout=10)
    if resp.status_code != 200:
        print(f"⚠️ No se pudo cargar la portada de Vinted (status {resp.status_code}).")
        return None

    token = sesion.cookies.get("access_token_web")
    if not token:
        print("⚠️ No se encontró la cookie 'access_token_web'.")
        return None

    sesion.headers["Authorization"] = f"Bearer {token}"
    return sesion


def buscar_anuncios(sesion, texto_busqueda: str, pagina: int = 1, por_pagina: int = 96):
    """Consulta el catálogo de Vinted y devuelve la lista de anuncios de una página."""
    url = f"https://{DOMINIO}/api/v2/catalog/items"
    params = {
        "search_text": texto_busqueda,
        "per_page": por_pagina,
        "page": pagina,
        "order": "newest_first",
    }

    respuesta = sesion.get(url, params=params, timeout=10)
    if respuesta.status_code != 200:
        print(f"⚠️ Error {respuesta.status_code} al buscar (página {pagina}).")
        return []

    return respuesta.json().get("items", [])


def buscar_varias_paginas(sesion, texto_busqueda: str, num_paginas: int = 3):
    """Junta varias páginas de resultados en una sola lista."""
    todos = []
    for pagina in range(1, num_paginas + 1):
        items = buscar_anuncios(sesion, texto_busqueda, pagina=pagina)
        if not items:
            break
        todos.extend(items)
    return todos


def buscar_por_categoria(sesion, catalog_ids, pagina: int = 1, por_pagina: int = 96, precio_desde: float = None):
    """
    Igual que buscar_anuncios, pero filtrando por categoría real de Vinted
    (mucho más preciso que buscar por palabras sueltas, sin ruido de otras
    cosas que casualmente mencionan la palabra en el título/descripción).
    """
    url = f"https://{DOMINIO}/api/v2/catalog/items"
    params = {
        "catalog_ids": catalog_ids,
        "per_page": por_pagina,
        "page": pagina,
        "order": "newest_first",
    }
    if precio_desde is not None:
        params["price_from"] = precio_desde

    respuesta = sesion.get(url, params=params, timeout=10)
    if respuesta.status_code != 200:
        print(f"⚠️ Error {respuesta.status_code} al buscar por categoría (página {pagina}).")
        print(f"   URL: {respuesta.url}")
        print(f"   Respuesta: {respuesta.text[:500]}")
        return []

    return respuesta.json().get("items", [])


def buscar_categoria_varias_paginas(sesion, catalog_ids, num_paginas: int = 3, precio_desde: float = None):
    """Junta varias páginas de resultados de una categoría en una sola lista."""
    todos = []
    for pagina in range(1, num_paginas + 1):
        items = buscar_por_categoria(sesion, catalog_ids, pagina=pagina, precio_desde=precio_desde)
        if not items:
            break
        todos.extend(items)
    return todos


def item_sigue_activo(sesion, item_id) -> bool:
    """
    Comprueba directamente en Vinted si un anuncio concreto sigue activo.
    Devuelve False si Vinted responde 404 (no encontrado). Cualquier otra
    cosa (200, error de red, bloqueo temporal...) se trata como "activo".

    Este resultado NO se da por definitivo aquí mismo — quien llama a esta
    función exige además una segunda confirmación en una ejecución distinta
    antes de marcar el anuncio como vendido de verdad (ver analizar.py).
    """
    url = f"https://{DOMINIO}/api/v2/items/{item_id}"
    try:
        resp = sesion.get(url, timeout=10)
    except requests.RequestException:
        return True

    return resp.status_code != 404
