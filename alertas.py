"""
Resumen diario de tendencias, enviado por Telegram.

Ahora manda:
1. Un mensaje corto con el resumen general (cuántos escaneos, cuántos confirmados).
2. Una FOTO por cada producto top, con precio/favoritos/duración en el pie
   de foto y el link para abrirlo directo en Vinted.
3. Un mensaje final con el ranking de marcas.

Reutilizable tanto para el resumen diario automático (alertas.py) como
para la consulta bajo demanda (comando.py), por eso la lógica de "generar
y mandar" vive en enviar_resumen_telegram(), no solo en construir_mensaje().
"""

import os
from analizar import ARCHIVO_HISTORIAL, cargar_historial, analizar_confirmado
from telegram_bot import enviar_mensaje, enviar_foto

TOP_PRODUCTOS = 8
TOP_MARCAS = 8
PRECIO_MINIMO = 60  # € — solo se muestran anuncios a partir de este precio


def _precio_valido(r):
    try:
        return float(r["precio"]) >= PRECIO_MINIMO
    except (TypeError, ValueError):
        return False


def _preparar_datos(resultados, escaneos):
    """Filtra y ordena los resultados. Devuelve (confirmados, top_productos, ranking_marcas)."""
    confirmados = [
        r for r in resultados
        if r["vendido_o_retirado"] and r["duracion_fiable"] and _precio_valido(r)
    ]
    top_productos = sorted(confirmados, key=lambda r: (r["favoritos"], r["puntuacion"]), reverse=True)

    from collections import defaultdict
    por_marca = defaultdict(list)
    for r in confirmados:
        if r["marca"]:
            try:
                precio_num = float(r["precio"])
            except (TypeError, ValueError):
                precio_num = None
            por_marca[r["marca"]].append((r["puntuacion"], precio_num))

    ranking_marcas = sorted(
        por_marca.items(),
        key=lambda kv: sum(p for p, _ in kv[1]) / len(kv[1]),
        reverse=True,
    )

    return confirmados, top_productos, ranking_marcas


def enviar_resumen_telegram(resultados, escaneos, chat_id=None):
    """Genera el resumen y lo manda por Telegram (texto + fotos + texto)."""
    if len(escaneos) < 2:
        enviar_mensaje(
            f"📊 Resumen Vinted\n\n"
            f"Solo hay {len(escaneos)} escaneo(s) todavía. "
            "Necesito al menos 2 en momentos distintos para poder comparar. "
            "Vuelve a preguntar en unas horas.",
            chat_id=chat_id,
        )
        return

    confirmados, top_productos, ranking_marcas = _preparar_datos(resultados, escaneos)

    intro = (
        "📊 Resumen diario Vinted\n\n"
        f"Escaneos analizados: {len(escaneos)}\n"
        f"Anuncios vendidos/retirados confirmados (≥{PRECIO_MINIMO}€): {len(confirmados)}"
    )
    enviar_mensaje(intro, chat_id=chat_id)

    if not top_productos:
        enviar_mensaje(f"No hay productos de ≥{PRECIO_MINIMO}€ confirmados todavía. Prueba más tarde.", chat_id=chat_id)
        return

    for r in top_productos[:TOP_PRODUCTOS]:
        caption = (
            f"{r['titulo']}\n"
            f"Marca: {r['marca'] or 's/marca'}\n"
            f"Precio: {r['precio']}€\n"
            f"Favoritos: {r['favoritos']}\n"
            f"Visible: {r['duracion_horas']}h\n"
            f"{r['url']}"
        )
        if r.get("foto_url"):
            enviar_foto(r["foto_url"], caption, chat_id=chat_id)
        else:
            enviar_mensaje(caption, chat_id=chat_id)

    if ranking_marcas:
        lineas = ["📈 Marcas con más interés:"]
        for marca, datos in ranking_marcas[:TOP_MARCAS]:
            puntuaciones = [p for p, _ in datos]
            precios = [pr for _, pr in datos if pr is not None]
            media_puntuacion = round(sum(puntuaciones) / len(puntuaciones), 2)
            texto_precio = ""
            if precios:
                media_precio = round(sum(precios) / len(precios), 2)
                texto_precio = f" | precio medio {media_precio}€"
            lineas.append(f"- {marca}: {media_puntuacion} ({len(datos)} anuncios){texto_precio}")
        enviar_mensaje("\n".join(lineas), chat_id=chat_id)


if __name__ == "__main__":
    if not os.path.exists(ARCHIVO_HISTORIAL):
        print("Todavía no hay historial. Ejecuta escanear.py primero.")
    else:
        filas = cargar_historial()
        resultados, escaneos = analizar_confirmado(filas)
        enviar_resumen_telegram(resultados, escaneos)
        print("✅ Resumen enviado por Telegram (texto + fotos).")
