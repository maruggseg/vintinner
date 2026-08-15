"""
Paso 2b: Analizar el historial acumulado por escanear.py.

Qué hace:
- Lee data/historial.csv (todas las fotos que has ido guardando).
- Para cada anuncio, calcula cuándo se vio por primera vez y por última vez.
- Un anuncio que dejó de aparecer en el escaneo más reciente = probablemente
  vendido o retirado. Cuanto menos tiempo estuvo visible, más "caliente".
- Combina eso con los favoritos que tenía para dar una puntuación de interés.
- Agrupa también por marca para ver qué marcas se mueven más.

Ejecútalo cuando ya tengas varios escaneos guardados (ideal: escaneos
repartidos en al menos 2-3 días distintos).
"""

import csv
import os
from datetime import datetime
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


def analizar(filas):
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
        primera_vez = apariciones[0]["fecha_escaneo"]
        ultima_vez = apariciones[-1]["fecha_escaneo"]

        vendido_o_retirado = ultima_vez < ultimo_escaneo

        duracion_horas = (ultima_vez - primera_vez).total_seconds() / 3600
        favoritos = int(apariciones[-1]["favoritos"] or 0)

        # Puntuación: más favoritos y menos duración = más "caliente".
        # +1 en duración para no dividir por cero.
        puntuacion = favoritos / (duracion_horas + 1)

        resultados.append({
            "titulo": apariciones[-1]["titulo"],
            "marca": apariciones[-1]["marca"],
            "precio": apariciones[-1]["precio"],
            "favoritos": favoritos,
            "duracion_horas": round(duracion_horas, 1),
            "vendido_o_retirado": vendido_o_retirado,
            "puntuacion": round(puntuacion, 2),
            "url": apariciones[-1]["url"],
        })

    return resultados, escaneos_unicos


if __name__ == "__main__":
    if not os.path.exists(ARCHIVO_HISTORIAL):
        print("Todavía no hay historial. Ejecuta escanear.py primero (varias veces, en días distintos).")
    else:
        filas = cargar_historial()
        resultados, escaneos = analizar(filas)

        print(f"Escaneos acumulados: {len(escaneos)}")
        if len(escaneos) < 2:
            print("Necesitas al menos 2 escaneos (en momentos distintos) para poder comparar. Vuelve a ejecutar escanear.py más tarde.")
        else:
            vendidos = [r for r in resultados if r["vendido_o_retirado"]]
            vendidos.sort(key=lambda r: r["puntuacion"], reverse=True)

            print(f"\n🔥 TOP anuncios que desaparecieron rápido con más favoritos:\n")
            for r in vendidos[:20]:
                print(f"- [{r['puntuacion']}] {r['titulo']} ({r['marca']}) | {r['precio']}€ | "
                      f"{r['favoritos']} favs | visible {r['duracion_horas']}h | {r['url']}")

            # Ranking por marca
            por_marca = defaultdict(list)
            for r in vendidos:
                if r["marca"]:
                    por_marca[r["marca"]].append(r["puntuacion"])

            ranking_marcas = sorted(
                por_marca.items(),
                key=lambda kv: sum(kv[1]) / len(kv[1]),
                reverse=True,
            )

            print(f"\n📊 Marcas con más interés (puntuación media):\n")
            for marca, puntuaciones in ranking_marcas[:15]:
                media = sum(puntuaciones) / len(puntuaciones)
                print(f"- {marca}: {round(media, 2)} (basado en {len(puntuaciones)} anuncios)")
