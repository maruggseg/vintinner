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
from datetime import datetime, timedelta
from collections import defaultdict

ARCHIVO_HISTORIAL = os.path.join("data", "historial.csv")


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
            "favoritos": favoritos_ahora,
            "crecimiento_favoritos": crecimiento_favoritos,
            "horas_visible": round(horas_visible, 1),
            "velocidad_favoritos": round(velocidad_favoritos, 2),
            "num_apariciones": num_apariciones,
            "url": apariciones[-1]["url"],
            "foto_url": apariciones[-1].get("foto_url", ""),
        })

    return resultados, escaneos_unicos


def analizar_top_racha(filas, dias=3, precio_minimo=60, top_n=5):
    """
    Ranking distinto al de 'interés ahora mismo': mira TODA la ventana de
    los últimos `dias` días (no solo el escaneo más reciente) y calcula,
    para cada anuncio visto 2+ veces en ese periodo, cuántos favoritos ha
    ganado y en cuánto tiempo. Devuelve los `top_n` que más rápido subieron.
    """
    if not filas:
        return []

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
            precio = float(apariciones[-1]["precio"])
        except (TypeError, ValueError):
            precio = 0
        if precio < precio_minimo:
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
                print(f"- {r['titulo']} ({r['marca']}) | {r['precio']}€ | "
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
