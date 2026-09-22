"""
Paso 2b: Analizar el historial acumulado por escanear.py.

Enfoque (v3): en vez de intentar detectar si un anuncio se vendió (esto
resultó no ser fiable comprobándolo contra Vinted), medimos el INTERÉS
REAL de anuncios que siguen activos ahora mismo:

- Cuántos favoritos tiene un anuncio en el escaneo más reciente.
- Si lo hemos visto en más de un escaneo, cuánto le han subido los
  favoritos desde que lo vimos por primera vez, y en cuántas horas.

Esto es un dato 100% real en cada momento (viene directo de Vinted en
cada escaneo), no requiere verificar nada aparte, así que no puede dar
falsos positivos.
"""

import csv
import os
import re
from datetime import datetime, timedelta
from collections import defaultdict

ARCHIVO_HISTORIAL = os.path.join("data", "historial.csv")

# Palabras que no aportan a identificar el MODELO concreto (tallas, estado,
# palabras sueltas de relleno en varios idiomas de los títulos que aparecen
# en Vinted España). No es una lista exhaustiva: el objetivo es agrupar
# "razonablemente bien", no perfecto.
_PALABRAS_RUIDO_MODELO = {
    "new", "used", "size", "sz", "uk", "us", "eu", "womens", "women", "woman",
    "mens", "man", "shoes", "shoe", "sneakers", "sneaker", "trainers", "trainer",
    "boots", "boot", "vtg", "vintage", "og", "original", "edicion", "edición",
    "especial", "special", "brand", "box", "in", "with", "and", "the", "for",
    "de", "et", "pour", "avec", "para", "con",
}


def _limpiar_palabra_modelo(palabra: str) -> str:
    return re.sub(r"[^\wáéíóúñ]", "", palabra.lower())


def extraer_modelo(titulo: str, marca: str) -> str:
    """
    Heurística para sacar 1-2 palabras que identifiquen el MODELO dentro de
    la marca (ej. "Samba" en "Adidas Samba edición especial", "9060" en
    "New Balance 9060"). Busca la marca dentro del título y se queda con lo
    que viene justo después; si no la encuentra (ej. "Nb 9060" en vez de
    "New Balance 9060"), coge las primeras palabras "útiles" del título.

    No es perfecto — títulos en varios idiomas, abreviaturas de marca — pero
    agrupa razonablemente bien anuncios del mismo modelo entre vendedores
    distintos, que es lo que hace falta para ver qué modelo se repite como
    tendencia (más fiable que fijarse en un solo anuncio suelto).
    """
    if not titulo:
        return ""

    palabras = [_limpiar_palabra_modelo(p) for p in titulo.split()]
    palabras = [p for p in palabras if p]

    marca_palabras = [_limpiar_palabra_modelo(p) for p in (marca or "").split()]
    marca_palabras = [p for p in marca_palabras if p]

    inicio = 0
    if marca_palabras:
        texto = " ".join(palabras)
        texto_marca = " ".join(marca_palabras)
        idx = texto.find(texto_marca)
        if idx != -1:
            inicio = len(texto[:idx].split()) + len(marca_palabras)

    candidatas = []
    for p in palabras[inicio:]:
        if p in _PALABRAS_RUIDO_MODELO:
            continue
        if p.isdigit() and len(p) <= 2:
            continue  # probablemente una talla suelta (ej. "8", "40"), no un modelo
        candidatas.append(p)
        if len(candidatas) == 2:
            break

    return " ".join(candidatas)


def cargar_historial():
    filas = []
    with open(ARCHIVO_HISTORIAL, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for fila in reader:
            fila["fecha_escaneo"] = datetime.fromisoformat(fila["fecha_escaneo"])
            filas.append(fila)
    return filas


def analizar_interes(filas):
    """
    Devuelve el interés de los anuncios que SIGUEN activos en el escaneo
    más reciente (no intenta saber qué pasó con los que ya no aparecen).
    """
    if not filas:
        return [], set()

    escaneos_unicos = sorted(set(f["fecha_escaneo"] for f in filas))
    ultimo_escaneo = escaneos_unicos[-1]

    por_item = defaultdict(list)
    for f in filas:
        por_item[f["item_id"]].append(f)

    resultados = []
    for item_id, apariciones in por_item.items():
        apariciones.sort(key=lambda x: x["fecha_escaneo"])

        # Solo nos interesan anuncios que siguen ahí AHORA (en el último escaneo).
        if apariciones[-1]["fecha_escaneo"] != ultimo_escaneo:
            continue

        primera_vez = apariciones[0]["fecha_escaneo"]
        ultima_vez = apariciones[-1]["fecha_escaneo"]
        num_apariciones = len(apariciones)

        favoritos_ahora = int(apariciones[-1]["favoritos"] or 0)
        favoritos_primera = int(apariciones[0]["favoritos"] or 0)
        horas_visible = (ultima_vez - primera_vez).total_seconds() / 3600
        crecimiento_favoritos = favoritos_ahora - favoritos_primera
        velocidad_favoritos = crecimiento_favoritos / (horas_visible + 1) if num_apariciones >= 2 else 0.0

        resultados.append({
            "item_id": item_id,
            "titulo": apariciones[-1]["titulo"],
            "marca": apariciones[-1]["marca"],
            "precio": apariciones[-1]["precio"],
            "moneda": apariciones[-1].get("moneda", "EUR"),
            "favoritos": favoritos_ahora,
            "crecimiento_favoritos": crecimiento_favoritos,
            "horas_visible": round(horas_visible, 1),
            "velocidad_favoritos": round(velocidad_favoritos, 2),
            "num_apariciones": num_apariciones,
            "url": apariciones[-1]["url"],
            "foto_url": apariciones[-1].get("foto_url", ""),
        })

    return resultados, escaneos_unicos


def analizar_top_racha(filas, dias=3, precio_minimo=60, top_n=5, tasas=None):
    """
    Ranking distinto al de 'interés ahora mismo': mira TODA la ventana de
    los últimos `dias` días (no solo el escaneo más reciente) y calcula,
    para cada anuncio visto 2+ veces en ese periodo, cuántos favoritos ha
    ganado y en cuánto tiempo. Devuelve los `top_n` que más rápido subieron.

    `tasas`: diccionario {moneda: unidades por 1 EUR} para poder comparar
    precio_minimo (en EUR) contra anuncios en otra moneda. Si no se pasa,
    no se convierte nada (se asume todo en EUR).
    """
    if not filas:
        return []

    tasas = tasas or {"EUR": 1.0}
    limite = datetime.now() - timedelta(days=dias)
    filas_periodo = [f for f in filas if f["fecha_escaneo"] >= limite]

    por_item = defaultdict(list)
    for f in filas_periodo:
        por_item[f["item_id"]].append(f)

    candidatos = []
    for item_id, apariciones in por_item.items():
        apariciones.sort(key=lambda x: x["fecha_escaneo"])
        if len(apariciones) < 2:
            continue  # necesitamos al menos 2 avistamientos para medir crecimiento

        try:
            precio_original = float(apariciones[-1]["precio"])
        except (TypeError, ValueError):
            precio_original = 0
        moneda = apariciones[-1].get("moneda", "EUR")
        tasa = tasas.get(moneda, 1.0) or 1.0
        precio_eur = precio_original / tasa
        if precio_eur < precio_minimo:
            continue

        primera_vez = apariciones[0]["fecha_escaneo"]
        ultima_vez = apariciones[-1]["fecha_escaneo"]
        favoritos_primera = int(apariciones[0]["favoritos"] or 0)
        favoritos_ultima = int(apariciones[-1]["favoritos"] or 0)
        crecimiento = favoritos_ultima - favoritos_primera

        if crecimiento <= 0:
            continue  # sin subida real de favoritos, no interesa para este ranking

        horas = (ultima_vez - primera_vez).total_seconds() / 3600
        velocidad = crecimiento / (horas + 1)

        candidatos.append({
            "item_id": item_id,
            "titulo": apariciones[-1]["titulo"],
            "marca": apariciones[-1]["marca"],
            "precio": apariciones[-1]["precio"],
            "moneda": apariciones[-1].get("moneda", "EUR"),
            "favoritos_inicio": favoritos_primera,
            "favoritos_ahora": favoritos_ultima,
            "crecimiento_favoritos": crecimiento,
            "horas": round(horas, 1),
            "velocidad_favoritos": round(velocidad, 2),
            "url": apariciones[-1]["url"],
            "foto_url": apariciones[-1].get("foto_url", ""),
        })

    candidatos.sort(key=lambda r: (r["velocidad_favoritos"], r["crecimiento_favoritos"]), reverse=True)
    return candidatos[:top_n]


def analizar_modelos_tendencia(filas, dias=7, precio_minimo=70, min_anuncios=3, top_n=10, tasas=None):
    """
    A diferencia de analizar_top_racha (que mira anuncios sueltos), esto
    agrupa por MARCA + MODELO (heurística sobre el título, ver
    extraer_modelo) para detectar qué modelo se repite con buen interés
    entre varios vendedores distintos — señal mucho más fiable de "esto se
    vende bien" que un anuncio individual, que puede haber despegado por
    razones propias de ese vendedor (mejores fotos, precio de ganga, etc).

    Solo cuentan los modelos vistos en `min_anuncios` anuncios DISTINTOS
    o más dentro de la ventana de `dias`.
    """
    if not filas:
        return []

    tasas = tasas or {"EUR": 1.0}
    limite = datetime.now() - timedelta(days=dias)
    filas_periodo = [f for f in filas if f["fecha_escaneo"] >= limite]

    por_item = defaultdict(list)
    for f in filas_periodo:
        por_item[f["item_id"]].append(f)

    resumen_items = []
    for item_id, apariciones in por_item.items():
        apariciones.sort(key=lambda x: x["fecha_escaneo"])
        primera, ultima = apariciones[0], apariciones[-1]

        try:
            precio_original = float(ultima["precio"])
        except (TypeError, ValueError):
            continue
        moneda = ultima.get("moneda", "EUR")
        tasa = tasas.get(moneda, 1.0) or 1.0
        precio_eur = precio_original / tasa
        if precio_eur < precio_minimo:
            continue

        marca = (ultima.get("marca") or "").strip()
        modelo = extraer_modelo(ultima.get("titulo", ""), marca)
        if not modelo:
            continue

        favoritos_ahora = int(ultima["favoritos"] or 0)
        favoritos_primera = int(primera["favoritos"] or 0)
        horas = (ultima["fecha_escaneo"] - primera["fecha_escaneo"]).total_seconds() / 3600
        velocidad = (favoritos_ahora - favoritos_primera) / (horas + 1) if len(apariciones) >= 2 else 0.0

        resumen_items.append({
            "item_id": item_id,
            "marca": marca,
            "modelo": modelo,
            "precio_eur": precio_eur,
            "favoritos": favoritos_ahora,
            "velocidad": velocidad,
            "titulo": ultima.get("titulo", ""),
            "url": ultima.get("url", ""),
        })

    grupos = defaultdict(list)
    for r in resumen_items:
        grupos[(r["marca"], r["modelo"])].append(r)

    tendencias = []
    for (marca, modelo), items in grupos.items():
        if len({i["item_id"] for i in items}) < min_anuncios:
            continue

        velocidad_media = sum(i["velocidad"] for i in items) / len(items)
        favoritos_media = sum(i["favoritos"] for i in items) / len(items)
        precio_medio = sum(i["precio_eur"] for i in items) / len(items)
        ejemplo = max(items, key=lambda i: i["favoritos"])

        tendencias.append({
            "marca": marca,
            "modelo": modelo,
            "num_anuncios": len({i["item_id"] for i in items}),
            "velocidad_media": round(velocidad_media, 2),
            "favoritos_media": round(favoritos_media, 1),
            "precio_medio_eur": round(precio_medio, 1),
            "ejemplo_titulo": ejemplo["titulo"],
            "ejemplo_url": ejemplo["url"],
        })

    tendencias.sort(key=lambda t: (t["velocidad_media"], t["num_anuncios"]), reverse=True)
    return tendencias[:top_n]


if __name__ == "__main__":
    if not os.path.exists(ARCHIVO_HISTORIAL):
        print("Todavía no hay historial. Ejecuta escanear.py primero (varias veces).")
    else:
        filas = cargar_historial()
        resultados, escaneos = analizar_interes(filas)

        print(f"Escaneos acumulados: {len(escaneos)}")
        if len(escaneos) < 2:
            print("Necesitas al menos 2 escaneos para ver crecimiento de favoritos. Vuelve a ejecutar escanear.py más tarde.")
        else:
            top = sorted(resultados, key=lambda r: (r["velocidad_favoritos"], r["favoritos"]), reverse=True)

            print(f"\n🔥 TOP anuncios activos con más interés:\n")
            for r in top[:20]:
                print(f"- {r['titulo']} ({r['marca']}) | {r['precio']} {r['moneda']} | "
                      f"{r['favoritos']} favs (+{r['crecimiento_favoritos']} en {r['horas_visible']}h) | {r['url']}")

            por_marca = defaultdict(list)
            for r in top:
                if r["marca"]:
                    por_marca[r["marca"]].append(r["favoritos"])

            ranking_marcas = sorted(
                por_marca.items(),
                key=lambda kv: sum(kv[1]) / len(kv[1]),
                reverse=True,
            )

            print(f"\n📊 Marcas con más interés (favoritos medios):\n")
            for marca, favs in ranking_marcas[:15]:
                media = sum(favs) / len(favs)
                print(f"- {marca}: {round(media, 2)} (basado en {len(favs)} anuncios)")
