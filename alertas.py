"""
Resumen de tendencias, enviado por Telegram con fotos.

Ya no intenta detectar ventas (no era fiable). Muestra los anuncios
ACTIVOS ahora mismo con más interés: favoritos actuales y, si los hemos
visto en más de un escaneo, cuánto les han subido los favoritos.
"""

import os
from analizar import ARCHIVO_HISTORIAL, cargar_historial, analizar_interes
from telegram_bot import enviar_mensaje, enviar_foto
from collections import defaultdict

TOP_PRODUCTOS = 8
TOP_MARCAS = 8
PRECIO_MINIMO = 60  # € — solo se muestran anuncios a partir de este precio


def _precio_valido(r):
    try:
        return float(r["precio"]) >= PRECIO_MINIMO
    except (TypeError, ValueError):
        return False


def top_y_marcas(resultados, escaneos):
    validos = [r for r in resultados if _precio_valido(r)]
    validos.sort(key=lambda r: (r["favoritos"], r["velocidad_favoritos"]), reverse=True)
    top = validos[:TOP_PRODUCTOS]

    por_marca = defaultdict(list)
    for r in validos:
        if r["marca"]:
            por_marca[r["marca"]].append(r["favoritos"])

    ranking_marcas = sorted(
        por_marca.items(),
        key=lambda kv: sum(kv[1]) / len(kv[1]),
        reverse=True,
    )[:TOP_MARCAS]

    return top, ranking_marcas, len(validos)


def enviar_resumen_telegram(resultados, escaneos, chat_id=None):
    if len(escaneos) < 2:
        enviar_mensaje(
            f"📊 Resumen Vinted\n\nSolo hay {len(escaneos)} escaneo(s) todavía. "
            "Necesito al menos 2 para poder mostrar tendencias. Prueba más tarde.",
            chat_id=chat_id,
        )
        return

    top, ranking_marcas, total_validos = top_y_marcas(resultados, escaneos)

    intro = (
        f"📊 Resumen Vinted\n\n"
        f"Escaneos analizados: {len(escaneos)}\n"
        f"Anuncios activos ≥{PRECIO_MINIMO}€: {total_validos}"
    )
    enviar_mensaje(intro, chat_id=chat_id)

    if not top:
        enviar_mensaje(f"No hay anuncios activos de ≥{PRECIO_MINIMO}€ todavía. Prueba más tarde.", chat_id=chat_id)
    else:
        for r in top:
            crecimiento_txt = (
                f"+{r['crecimiento_favoritos']} favs en {r['horas_visible']}h"
                if r["num_apariciones"] >= 2 else "recién detectado"
            )
            caption = (
                f"{r['titulo']}\n"
                f"Marca: {r['marca'] or 's/marca'}\n"
                f"Precio: {r['precio']}€\n"
                f"Favoritos ahora: {r['favoritos']} ({crecimiento_txt})\n"
                f"{r['url']}"
            )
            if r.get("foto_url"):
                enviar_foto(r["foto_url"], caption, chat_id=chat_id)
            else:
                enviar_mensaje(caption, chat_id=chat_id)

    if ranking_marcas:
        lineas = ["📈 Marcas con más interés (favoritos medios):", ""]
        for marca, favs in ranking_marcas:
            media = round(sum(favs) / len(favs), 2)
            lineas.append(f"- {marca}: {media} ({len(favs)} anuncios)")
        enviar_mensaje("\n".join(lineas), chat_id=chat_id)


if __name__ == "__main__":
    if not os.path.exists(ARCHIVO_HISTORIAL):
        print("Todavía no hay historial. Ejecuta escanear.py primero.")
    else:
        filas = cargar_historial()
        resultados, escaneos = analizar_interes(filas)
        enviar_resumen_telegram(resultados, escaneos)
        print("✅ Resumen enviado por Telegram.")
