"""
Paso 2b: Analizar el historial acumulado por escanear.py.

Qué hace:
- Lee data/historial.csv (todas las fotos que has ido guardando).
- Para cada anuncio, calcula cuándo se vio por primera vez y por última vez.
- Un anuncio que dejó de aparecer en el escaneo más reciente es CANDIDATO a
  vendido/retirado — pero eso puede ser un falso positivo si simplemente
  quedó fuera de las páginas que escaneamos (mucho volumen de anuncios
  nuevos empujándolo fuera). Por eso, antes de darlo por bueno, se
  confirma visitando directamente la página del anuncio en Vinted: si
  Vinted devuelve "no encontrado", es que de verdad ya no está.
- Combina eso con los favoritos que tenía para dar una puntuación de interés.
- Agrupa también por marca para ver qué marcas se mueven más.

Ejecútalo cuando ya tengas varios escaneos guardados (ideal: escaneos
repartidos en al menos 2-3 días distintos).
"""

import csv
import os
from datetime import datetime
from collections import defaultdict

from vinted_api import crear_sesion_autenticada, item_sigue_activo

ARCHIVO_HISTORIAL = os.path.join("data", "historial.csv")

# Cuántos candidatos (como máximo) se verifican contra Vinted en cada
# ejecución, para no disparar demasiadas peticiones. Se verifican primero
# los de mayor puntuación, que son los que de verdad importan mostrar.
MAX_VERIFICACIONES = 60


def cargar_historial():
    filas = []
    with open(ARCHIVO_HISTORIAL, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for fila in reader:
            fila["fecha_escaneo"] = datetime.fromisoformat(fila["fecha_escaneo"])
            filas.append(fila)
    return filas


def analizar(filas):
    """Calcula candidatos a 'vendido' SIN verificar todavía contra Vinted."""
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
        num_apariciones = len(apariciones)

        candidato_vendido = ultima_vez < ultimo_escaneo

        duracion_horas = (ultima_vez - primera_vez).total_seconds() / 3600
        favoritos = int(apariciones[-1]["favoritos"] or 0)

        # Con una sola aparición no hay forma fiable de saber cuánto duró
        # visible (podría llevar publicado desde antes de nuestro primer
        # escaneo). En ese caso no calculamos puntuación por duración.
        duracion_fiable = num_apariciones >= 2
        if duracion_fiable:
            puntuacion = favoritos / (duracion_horas + 1)
        else:
            puntuacion = None

        resultados.append({
            "item_id": item_id,
            "titulo": apariciones[-1]["titulo"],
            "marca": apariciones[-1]["marca"],
            "precio": apariciones[-1]["precio"],
            "favoritos": favoritos,
            "duracion_horas": round(duracion_horas, 1) if duracion_fiable else None,
            "duracion_fiable": duracion_fiable,
            "num_apariciones": num_apariciones,
            "vendido_o_retirado": candidato_vendido,  # candidato, aún sin confirmar
            "puntuacion": round(puntuacion, 2) if puntuacion is not None else None,
            "url": apariciones[-1]["url"],
            "foto_url": apariciones[-1].get("foto_url", ""),
        })

    return resultados, escaneos_unicos


def analizar_confirmado(filas):
    """
    Igual que analizar(), pero confirma contra Vinted los candidatos a
    'vendido' antes de darlos por buenos, para eliminar los falsos
    positivos causados por el volumen de anuncios nuevos.
    """
    resultados, escaneos = analizar(filas)

    if len(escaneos) < 2:
        return resultados, escaneos

    candidatos = [r for r in resultados if r["vendido_o_retirado"] and r["duracion_fiable"]]
    candidatos.sort(key=lambda r: r["puntuacion"], reverse=True)

    a_verificar = candidatos[:MAX_VERIFICACIONES]
    no_verificados = candidatos[MAX_VERIFICACIONES:]

    # Los que no llegamos a verificar (por el límite), los dejamos fuera
    # del top de "vendidos" para no arriesgar falsos positivos.
    for r in no_verificados:
        r["vendido_o_retirado"] = False

    sesion = crear_sesion_autenticada()
    if sesion is None:
        print("⚠️ No se pudo verificar contra Vinted (fallo de sesión). Se muestran solo candidatos sin confirmar.")
        return resultados, escaneos

    confirmados = 0
    for r in a_verificar:
        activo = item_sigue_activo(sesion, r["item_id"])
        r["vendido_o_retirado"] = not activo
        if r["vendido_o_retirado"]:
            confirmados += 1

    print(f"Verificados {len(a_verificar)} candidatos contra Vinted → {confirmados} confirmados como vendidos/retirados de verdad.")

    return resultados, escaneos


if __name__ == "__main__":
    if not os.path.exists(ARCHIVO_HISTORIAL):
        print("Todavía no hay historial. Ejecuta escanear.py primero (varias veces, en días distintos).")
    else:
        filas = cargar_historial()
        resultados, escaneos = analizar_confirmado(filas)

        print(f"Escaneos acumulados: {len(escaneos)}")
        if len(escaneos) < 2:
            print("Necesitas al menos 2 escaneos (en momentos distintos) para poder comparar. Vuelve a ejecutar escanear.py más tarde.")
        else:
            vendidos = [r for r in resultados if r["vendido_o_retirado"] and r["duracion_fiable"]]
            vendidos.sort(key=lambda r: r["puntuacion"], reverse=True)

            print(f"\n🔥 TOP anuncios confirmados como vendidos/retirados, con más favoritos:\n")
            for r in vendidos[:20]:
                print(f"- [{r['puntuacion']}] {r['titulo']} ({r['marca']}) | {r['precio']}€ | "
                      f"{r['favoritos']} favs | visible {r['duracion_horas']}h | {r['url']}")

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
