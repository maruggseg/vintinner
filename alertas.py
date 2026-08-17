"""
Resumen de tendencias, enviado por Telegram con fotos.

Ya no intenta detectar ventas (no era fiable). Muestra los anuncios
ACTIVOS ahora mismo con más interés: favoritos actuales y, si los hemos
visto en más de un escaneo, cuánto les han subido los favoritos.
"""

import os
from analizar import ARCHIVO_HISTORIAL, cargar_historial, analizar_interes, analizar_top_racha
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
                print(f"→ Enviando foto: id={r['item_id']} {r['titulo'][:40]!r} | url: {r['foto_url']}")
                enviado = enviar_foto(r["foto_url"], caption, chat_id=chat_id)
                print(f"  resultado enviar_foto: {'OK' if enviado else 'FALLÓ, mando solo texto'}")
                if not enviado:
                    # La foto falló al enviarse (ej. Vinted bloqueó la descarga) — mandamos el texto igualmente.
                    enviar_mensaje(caption, chat_id=chat_id)
            else:
                print(f"→ Sin foto_url para: id={r['item_id']} {r['titulo'][:40]!r} — mando solo texto")
                enviar_mensaje(caption, chat_id=chat_id)

    if ranking_marcas:
        lineas = ["📈 Marcas con más interés (favoritos medios):", ""]
        for marca, favs in ranking_marcas:
            media = round(sum(favs) / len(favs), 2)
            lineas.append(f"- {marca}: {media} ({len(favs)} anuncios)")
        enviar_mensaje("\n".join(lineas), chat_id=chat_id)


def enviar_top_racha_telegram(filas, chat_id=None, dias=3):
    """
    Comando separado del resumen normal: los 10 anuncios que MÁS RÁPIDO han
    subido de favoritos en los últimos `dias` días (no solo en el último
    escaneo, sino mirando toda esa ventana de tiempo).
    """
    top = analizar_top_racha(filas, dias=dias, precio_minimo=PRECIO_MINIMO, top_n=10)

    if not top:
        enviar_mensaje(
            f"🚀 Top con más subida de favoritos ({dias} días)\n\n"
            f"Todavía no hay suficientes datos o ningún anuncio ≥{PRECIO_MINIMO}€ "
            "ha ganado favoritos en este periodo. Prueba más tarde.",
            chat_id=chat_id,
        )
        return

    enviar_mensaje(f"🚀 Top 10 con más subida de favoritos (últimos {dias} días)", chat_id=chat_id)


    for i, r in enumerate(top, start=1):
        caption = (
            f"#{i} — {r['titulo']}\n"
            f"Marca: {r['marca'] or 's/marca'}\n"
            f"Precio: {r['precio']}€\n"
            f"Favoritos: {r['favoritos_inicio']} → {r['favoritos_ahora']} "
            f"(+{r['crecimiento_favoritos']} en {r['horas']}h)\n"
            f"{r['url']}"
        )
        if r.get("foto_url"):
            enviado = enviar_foto(r["foto_url"], caption, chat_id=chat_id)
            if not enviado:
                enviar_mensaje(caption, chat_id=chat_id)
        else:
            enviar_mensaje(caption, chat_id=chat_id)


if __name__ == "__main__":
    if not os.path.exists(ARCHIVO_HISTORIAL):
        print("Todavía no hay historial. Ejecuta escanear.py primero.")
    else:
        filas = cargar_historial()
        resultados, escaneos = analizar_interes(filas)
        enviar_resumen_telegram(resultados, escaneos)
        print("✅ Resumen enviado por Telegram.")
