"""
Seguimiento de perfiles de Vinted.

Lee la lista de perfiles de data/perfiles.txt (uno por línea: el enlace al
perfil, p. ej. https://www.vinted.es/member/12345678-nombre, o solo el
número), descarga todos sus artículos publicados y guarda en
data/perfiles.json, para cada artículo:
  - cuándo lo subió y cuándo lo vimos por primera vez,
  - favoritos y visitas actuales, y su evolución (una muestra por hora),
  - si sigue activo, está reservado, se vendió o desapareció.

Solo usa datos PÚBLICOS (los que ve cualquiera en el perfil). Las ofertas
y los mensajes de compradores solo los ve el dueño de la cuenta, así que
no se pueden seguir desde aquí.

Lo ejecuta el workflow de GitHub Actions justo después de escanear.py.
"""

import json
import os
import re
import time
from datetime import datetime, timedelta

from vinted_api import DOMINIO, crear_sesion_autenticada

ARCHIVO_PERFILES = os.path.join("data", "perfiles.txt")
ARCHIVO_DATOS = os.path.join("data", "perfiles.json")

PAGINAS_MAXIMAS = 5          # 5 x 96 = hasta 480 artículos por perfil
PAUSA_ENTRE_PETICIONES = 1.0  # segundos; ir despacio para no llamar la atención
MUESTRA_CADA = timedelta(hours=1)        # un punto de la evolución por hora
RETENCION_SERIE = timedelta(days=14)     # puntos más viejos se descartan
RETENCION_DESAPARECIDOS = timedelta(days=14)  # artículos que ya no están


def leer_perfiles():
    """Devuelve la lista de IDs (str) de data/perfiles.txt, sin duplicados."""
    if not os.path.exists(ARCHIVO_PERFILES):
        return []
    ids = []
    with open(ARCHIVO_PERFILES, encoding="utf-8") as f:
        for linea in f:
            linea = linea.split("#", 1)[0].strip()
            id_perfil = id_de_perfil(linea)
            if id_perfil and id_perfil not in ids:
                ids.append(id_perfil)
    return ids


def id_de_perfil(texto: str):
    """Saca el número de usuario de un enlace de perfil (o de un número suelto)."""
    texto = (texto or "").strip()
    if texto.isdigit():
        return texto
    m = re.search(r"/member/(?:general/)?(\d+)", texto)
    return m.group(1) if m else None


def _get_json(sesion, url, params=None):
    time.sleep(PAUSA_ENTRE_PETICIONES)
    try:
        resp = sesion.get(url, params=params, timeout=15)
    except Exception as e:  # red caída, timeout...
        print(f"   ⚠️ {url}: {type(e).__name__}")
        return None, None
    if resp.status_code != 200:
        print(f"   ⚠️ {url} -> {resp.status_code}: {resp.text[:200]!r}")
        return resp.status_code, None
    try:
        return 200, resp.json()
    except ValueError:
        print(f"   ⚠️ {url} -> respuesta que no es JSON")
        return 200, None


def info_perfil(sesion, id_perfil):
    _, datos = _get_json(sesion, f"https://{DOMINIO}/api/v2/users/{id_perfil}")
    usuario = (datos or {}).get("user") or {}
    foto = usuario.get("photo") or {}
    return {
        "nombre": usuario.get("login") or f"Perfil {id_perfil}",
        "foto": foto.get("url") or "",
        "valoracion": usuario.get("feedback_reputation"),
        "num_valoraciones": usuario.get("feedback_count"),
        "seguidores": usuario.get("followers_count"),
    }


def articulos_perfil(sesion, id_perfil):
    """
    Devuelve (articulos, completo). "completo" es False si no pudimos
    recorrer todas las páginas: entonces no damos por desaparecido nada.
    """
    articulos = []
    for pagina in range(1, PAGINAS_MAXIMAS + 1):
        estado, datos = _get_json(
            sesion,
            f"https://{DOMINIO}/api/v2/wardrobe/{id_perfil}/items",
            {"page": pagina, "per_page": 96, "order": "newest_first"},
        )
        if datos is None:
            return articulos, False
        items = datos.get("items") or []
        articulos.extend(items)
        paginacion = datos.get("pagination") or {}
        total_paginas = paginacion.get("total_pages") or 1
        if not items or pagina >= total_paginas:
            return articulos, True
    return articulos, False


# ---------- extraer campos (el formato del armario varía un poco) ----------

def _precio(a):
    p = a.get("price")
    if isinstance(p, dict):
        return p.get("amount"), p.get("currency_code") or "EUR"
    return p, a.get("currency") or "EUR"


def _foto(a):
    fotos = a.get("photos") or []
    foto = a.get("photo") or (fotos[0] if fotos else {}) or {}
    if not isinstance(foto, dict):
        return "", None
    url = foto.get("url") or foto.get("full_size_url") or ""
    marca_tiempo = (foto.get("high_resolution") or {}).get("timestamp")
    return url, marca_tiempo


def _talla(a):
    if a.get("size_title"):
        return a["size_title"]
    segunda = (a.get("item_box") or {}).get("second_line") or ""
    return segunda.split("·")[0].strip()


def _marca(a):
    return a.get("brand_title") or (a.get("item_box") or {}).get("first_line") or ""


def _url(a):
    url = a.get("url") or ""
    if url.startswith("/"):
        return f"https://{DOMINIO}{url}"
    return url or f"https://{DOMINIO}/items/{a.get('id')}"


def _estado(a):
    if a.get("is_closed") or a.get("item_closing_action") == "sold" or a.get("is_sold"):
        return "vendido"
    if a.get("is_reserved"):
        return "reservado"
    if a.get("is_hidden"):
        return "oculto"
    return "activo"


def _subido(a, marca_tiempo_foto):
    for clave in ("created_at_ts", "created_at"):
        valor = a.get(clave)
        if isinstance(valor, (int, float)):
            return datetime.fromtimestamp(valor).isoformat(timespec="seconds")
        if isinstance(valor, str) and valor:
            try:
                return datetime.fromisoformat(valor.replace("Z", "+00:00")).replace(tzinfo=None).isoformat(timespec="seconds")
            except ValueError:
                pass
    # Truco habitual: la foto principal lleva la hora en que se subió.
    if isinstance(marca_tiempo_foto, (int, float)):
        return datetime.fromtimestamp(marca_tiempo_foto).isoformat(timespec="seconds")
    return None


# ---------- guardar ----------

def cargar_datos():
    if os.path.exists(ARCHIVO_DATOS):
        with open(ARCHIVO_DATOS, encoding="utf-8") as f:
            return json.load(f)
    return {"perfiles": {}, "articulos": {}}


def actualizar_articulo(guardado, a, id_perfil, ahora):
    precio, moneda = _precio(a)
    foto_url, marca_tiempo = _foto(a)
    favs = a.get("favourite_count") or 0
    vistas = a.get("view_count")
    estado = _estado(a)
    ahora_iso = ahora.isoformat(timespec="seconds")

    nuevo = guardado is None
    g = guardado or {"primera_vez": ahora_iso, "serie": []}
    if g.get("estado") != "vendido" and estado == "vendido":
        g["vendido_en"] = ahora_iso
    g.update({
        "perfil_id": id_perfil,
        "titulo": a.get("title") or "",
        "marca": _marca(a),
        "talla": _talla(a),
        "precio": precio,
        "moneda": moneda,
        "url": _url(a),
        "foto_url": foto_url or g.get("foto_url", ""),
        "subido": _subido(a, marca_tiempo) or g.get("subido"),
        "ultima_vez": ahora_iso,
        "favs": favs,
        "vistas": vistas,
        "estado": estado,
    })

    serie = g["serie"]
    if not serie or ahora - datetime.fromisoformat(serie[-1][0]) >= MUESTRA_CADA:
        serie.append([ahora_iso, favs, vistas])
    limite = ahora - RETENCION_SERIE
    g["serie"] = [p for p in serie if datetime.fromisoformat(p[0]) >= limite]
    return g, nuevo


def main():
    perfiles = leer_perfiles()
    datos = cargar_datos()
    ahora = datetime.now()
    ahora_iso = ahora.isoformat(timespec="seconds")

    # Quitar perfiles que ya no están en la lista (y sus artículos).
    for id_viejo in list(datos["perfiles"]):
        if id_viejo not in perfiles:
            del datos["perfiles"][id_viejo]
    datos["articulos"] = {k: v for k, v in datos["articulos"].items() if v.get("perfil_id") in perfiles}

    if not perfiles:
        print("No hay perfiles en data/perfiles.txt; nada que seguir.")
    else:
        sesion = crear_sesion_autenticada()
        if sesion is None:
            print("No se pudo conectar con Vinted.")
            return

        for id_perfil in perfiles:
            print(f"👤 Perfil {id_perfil}")
            perfil = datos["perfiles"].get(id_perfil, {"id": id_perfil})
            perfil.update(info_perfil(sesion, id_perfil))
            perfil["url"] = f"https://{DOMINIO}/member/{id_perfil}"

            articulos, completo = articulos_perfil(sesion, id_perfil)
            if not articulos and not completo:
                perfil["error"] = "No se pudo leer el perfil en el último escaneo"
                datos["perfiles"][id_perfil] = perfil
                continue
            perfil.pop("error", None)
            perfil["ultimo_escaneo"] = ahora_iso

            vistos, nuevos = set(), 0
            for a in articulos:
                id_art = str(a.get("id"))
                vistos.add(id_art)
                datos["articulos"][id_art], es_nuevo = actualizar_articulo(
                    datos["articulos"].get(id_art), a, id_perfil, ahora
                )
                nuevos += es_nuevo

            # Lo que estaba y ya no aparece: vendido o borrado por el vendedor.
            if completo:
                for id_art, g in datos["articulos"].items():
                    if g["perfil_id"] == id_perfil and id_art not in vistos and g.get("estado") not in ("vendido", "desaparecido"):
                        g["estado"] = "desaparecido"
                        g["desaparecido_en"] = ahora_iso

            datos["perfiles"][id_perfil] = perfil
            print(f"   {len(articulos)} artículos ({nuevos} nuevos), completo={completo}")

    # Podar artículos que llevan tiempo sin aparecer.
    limite = ahora - RETENCION_DESAPARECIDOS
    datos["articulos"] = {
        k: v for k, v in datos["articulos"].items()
        if datetime.fromisoformat(v["ultima_vez"]) >= limite
    }
    datos["actualizado"] = ahora_iso

    os.makedirs("data", exist_ok=True)
    temporal = ARCHIVO_DATOS + ".tmp"
    with open(temporal, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(temporal, ARCHIVO_DATOS)
    print(f"✅ {len(datos['perfiles'])} perfiles, {len(datos['articulos'])} artículos en {ARCHIVO_DATOS}")


if __name__ == "__main__":
    main()
