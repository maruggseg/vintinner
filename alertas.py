"""
Resumen diario de tendencias, enviado por Telegram.

Reutiliza la misma lógica de analizar.py, pero en vez de imprimir en la
terminal, arma un mensaje corto con el top de productos y marcas, y lo
manda a tu Telegram. Pensado para ejecutarse UNA vez al día (programado
aparte de escanear.py, que sigue corriendo varias veces al día).
"""

import os
from analizar import ARCHIVO_HISTORIAL, cargar_historial, analizar
from telegram_bot import enviar_mensaje

TOP_PRODUCTOS = 10
TOP_MARCAS = 8


def construir_mensaje(resultados, escaneos):
    if len(escaneos) < 2:
        return (
            "📊 Resumen Vinted\n\n"
            f"Solo hay {len(escaneos)} escaneo(s) todavía. "
            "Necesito al menos 2 en momentos distintos para poder comparar. "
            "Mañana debería haber más datos."
        )

    vendidos = [r for r in resultados if r["vendido_o_retirado"]]
    vendidos.sort(key=lambda r: r["puntuacion"], reverse=True)

    lineas = ["📊 *Resumen diario Vinted*", ""]
    lineas.append(f"Escaneos analizados: {len(escaneos)}")
    lineas.append(f"Anuncios que se movieron: {len(vendidos)}")
    lineas.append("")
    lineas.append("🔥 Top productos con más interés:")

    for r in vendidos[:TOP_PRODUCTOS]:
        lineas.append(
            f"- {r['titulo']} ({r['marca'] or 's/marca'}) | {r['precio']}€ | "
            f"{r['favoritos']} favs | visible {r['duracion_horas']}h"
        )

    # Ranking por marca
    from collections import defaultdict
    por_marca = defaultdict(list)
    for r in vendidos:
        if r["marca"]:
            por_marca[r["marca"]].append(r["puntuacion"])

    if por_marca:
        ranking_marcas = sorted(
            por_marca.items(),
            key=lambda kv: sum(kv[1]) / len(kv[1]),
            reverse=True,
        )
        lineas.append("")
        lineas.append("📈 Marcas con más interés:")
        for marca, puntuaciones in ranking_marcas[:TOP_MARCAS]:
            media = sum(puntuaciones) / len(puntuaciones)
            lineas.append(f"- {marca}: {round(media, 2)} ({len(puntuaciones)} anuncios)")

    return "\n".join(lineas)


if __name__ == "__main__":
    if not os.path.exists(ARCHIVO_HISTORIAL):
        print("Todavía no hay historial. Ejecuta escanear.py primero.")
    else:
        filas = cargar_historial()
        resultados, escaneos = analizar(filas)

        mensaje = construir_mensaje(resultados, escaneos)
        ok = enviar_mensaje(mensaje)

        if ok:
            print("✅ Resumen enviado por Telegram.")
        else:
            print("❌ No se pudo enviar. Mira el error de arriba.")
