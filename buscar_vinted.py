"""
Paso 1 (v2): Buscar anuncios de zapatillas en Vinted.

Vinted no tiene API pública oficial. Su web usa internamente un endpoint tipo:

    https://www.vinted.es/api/v2/catalog/items

Ese endpoint exige un token de autenticación (no solo una cookie cualquiera).
En vez de copiarlo a mano del navegador (que caduca y da guerra), este script
lo consigue el solo:

1. Abre una "sesión" con requests.Session() (como si fuera un navegador).
2. Visita la portada de Vinted una vez -> Vinted le devuelve unas cookies,
   entre ellas 'access_token_web', que es el token que necesitamos.
3. Usa ese token en la cabecera Authorization de la petición de búsqueda.

Ya no hace falta tocar DevTools ni copiar nada a mano.
"""

import requests

# --- CONFIGURACIÓN ---
DOMINIO = "www.vinted.es"   # cambia si usas vinted.com, vinted.fr, etc.
BUSQUEDA = "nike air max"
# ----------------------

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
        print("⚠️ No se encontró la cookie 'access_token_web'. Vinted puede haber cambiado su sistema de sesión.")
        return None

    sesion.headers["Authorization"] = f"Bearer {token}"
    return sesion


def buscar_anuncios(sesion, texto_busqueda: str, por_pagina: int = 20):
    """Consulta el catálogo de Vinted y devuelve la lista de anuncios encontrados."""
    url = f"https://{DOMINIO}/api/v2/catalog/items"
    params = {
        "search_text": texto_busqueda,
        "per_page": por_pagina,
        "order": "newest_first",
    }

    respuesta = sesion.get(url, params=params, timeout=10)

    if respuesta.status_code != 200:
        print(f"⚠️ Error {respuesta.status_code} al buscar.")
        print(respuesta.text[:500])
        return []

    datos = respuesta.json()
    return datos.get("items", [])


if __name__ == "__main__":
    print("Iniciando sesión con Vinted...")
    sesion = crear_sesion_autenticada()

    if sesion is None:
        print("No se pudo continuar. Revisa el mensaje de arriba.")
    else:
        print("Sesión conseguida. Buscando...\n")
        anuncios = buscar_anuncios(sesion, BUSQUEDA)

        print(f"Encontrados {len(anuncios)} anuncios para '{BUSQUEDA}':\n")

        for a in anuncios:
            titulo = a.get("title")
            precio = a.get("price", {}).get("amount")
            moneda = a.get("price", {}).get("currency_code")
            url_item = a.get("url")
            print(f"- {titulo} | {precio} {moneda} | {url_item}")
