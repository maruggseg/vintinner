"""
Resumen diario de tendencias, enviado por Telegram.

Reutiliza la misma lógica de analizar.py, pero en vez de imprimir en la
terminal, arma un mensaje corto con el top de productos y marcas, y lo
manda a tu Telegram. Pensado para ejecutarse UNA vez al día (programado
aparte de escanear.py, que sigue corriendo varias veces al día).
"""

import os
from analizar import ARCHIVO_HISTORIAL, cargar_historial, analizar_confirmado
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

    confirmados = [r for r in resultados if r["vendido_o_retirado"] and r["duracion_fiable"]]
    vendidos = [r for r in confirmados if r["favoritos"] > 0]
    vendidos.sort(key=lambda r: r["puntuacion"], reverse=True)

    lineas = ["📊 *Resumen diario Vinted*", ""]
    lineas.append(f"Escaneos analizados: {len(escaneos)}")
    lineas.append(f"Anuncios vendidos/retirados confirmados: {len(confirmados)}")
    lineas.append(f"Con al menos 1 favorito: {len(vendidos)}")
    lineas.append("")
    lineas.append("🔥 Top productos con más interés:")

    for r in vendidos[:TOP_PRODUCTOS]:
        lineas.append(
            f"- {r['titulo']} ({r['marca'] or 's/marca'}) | {r['precio']}€ | "
            f"{r['favoritos']} favs | visible {r['duracion_horas']}h"
        )

    # Ranking por marca (puntuación media + precio medio de venta)
    from collections import defaultdict
    por_marca = defaultdict(list)
    for r in vendidos:
        if r["marca"]:
            try:
                precio_num = float(r["precio"])
            except (TypeError, ValueError):
                precio_num = None
            por_marca[r["marca"]].append((r["puntuacion"], precio_num))

    if por_marca:
        ranking_marcas = sorted(
            por_marca.items(),
            key=lambda kv: sum(p for p, _ in kv[1]) / len(kv[1]),
            reverse=True,
        )
        lineas.append("")
        lineas.append("📈 Marcas con más interés:")
        for marca, datos in ranking_marcas[:TOP_MARCAS]:
            puntuaciones = [p for p, _ in datos]
            precios = [pr for _, pr in datos if pr is not None]
            media_puntuacion = round(sum(puntuaciones) / len(puntuaciones), 2)
            texto_precio = ""
            if precios:
                media_precio = round(sum(precios) / len(precios), 2)
                texto_precio = f" | precio medio {media_precio}€"
            lineas.append(f"- {marca}: {media_puntuacion} ({len(datos)} anuncios){texto_precio}")

    return "\n".join(lineas)


if __name__ == "__main__":
    if not os.path.exists(ARCHIVO_HISTORIAL):
        print("Todavía no hay historial. Ejecuta escanear.py primero.")
    else:
        filas = cargar_historial()
        resultados, escaneos = analizar_confirmado(filas)

        mensaje = construir_mensaje(resultados, escaneos)
        ok = enviar_mensaje(mensaje)

        if ok:
            print("✅ Resumen enviado por Telegram.")
        else:
            print("❌ No se pudo enviar. Mira el error de arriba.")
