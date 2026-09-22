"""
Resumen de tendencias, enviado por Telegram con fotos.

Ya no intenta detectar ventas (no era fiable). Muestra los anuncios
ACTIVOS ahora mismo con más interés: favoritos actuales y, si los hemos
visto en más de un escaneo, cuánto les han subido los favoritos.
"""

import os
import requests
from analizar import (
    ARCHIVO_HISTORIAL,
    cargar_historial,
    analizar_interes,
    analizar_top_racha,
    analizar_modelos_tendencia,
)
from telegram_bot import enviar_mensaje, enviar_foto
from collections import defaultdict

TOP_PRODUCTOS = 8
TOP_MARCAS = 8
PRECIO_MINIMO = 70  # € — solo se muestran anuncios a partir de este precio
EDAD_MAXIMA_DIAS = 7  # ignoramos anuncios que llevamos rastreando más tiempo que esto: ya no son "nuevos"

SIMBOLOS_MONEDA = {"EUR": "€", "USD": "$", "GBP": "£"}

# Tasas de respaldo (unidades de esa moneda por 1 EUR) por si la API de
# cambio en vivo no responde. Aproximadas: mejor una comparación algo
# desviada que dejar el bot sin poder filtrar por precio.
TASAS_RESPALDO = {"EUR": 1.0, "USD": 1.08, "GBP": 0.86}


def obtener_tasas_cambio() -> dict:
    """
    Tasas de cambio a EUR (unidades de esa moneda por 1 EUR), para comparar
    PRECIO_MINIMO (en EUR) contra anuncios en otra moneda sin falsear el
    filtro. Vinted a veces devuelve todo el lote en USD (según la IP de
    quien pregunta), así que sin esto un anuncio de 72$ (~67€) pasaría el
    filtro de "≥70" por simple coincidencia numérica.
    """
    try:
        resp = requests.get(
            "https://api.frankfurter.app/latest?from=EUR&to=USD,GBP", timeout=5
        )
        if resp.status_code == 200:
            tasas = resp.json().get("rates") or {}
            if tasas:
                tasas["EUR"] = 1.0
                return tasas
    except requests.RequestException:
        pass
    return dict(TASAS_RESPALDO)


def simbolo_moneda(moneda) -> str:
    """
    Desde el cambio de API, Vinted a veces muestra anuncios en otra moneda
    (según la IP de quien pregunta). No forzamos EUR en el escaneo porque
    eso puede dejar el bot sin datos — en vez de eso, mostramos el símbolo
    que corresponda a cada anuncio en concreto.
    """
    if not moneda:
        return "€"
    return SIMBOLOS_MONEDA.get(moneda, f" {moneda}")


def _precio_en_eur(r, tasas) -> float:
    try:
        precio = float(r["precio"])
    except (TypeError, ValueError):
        return 0.0
    tasa = tasas.get(r.get("moneda") or "EUR", 1.0) or 1.0
    return precio / tasa


def _precio_valido(r, tasas):
    return _precio_en_eur(r, tasas) >= PRECIO_MINIMO


def _es_reciente(r):
    """True si llevamos viendo este anuncio (desde su primer escaneo) EDAD_MAXIMA_DIAS o menos."""
    return r["horas_visible"] <= EDAD_MAXIMA_DIAS * 24


def top_y_marcas(resultados, escaneos):
    # Orden: primero velocidad de favoritos (lo que "se mueve" ahora), favoritos
    # totales como desempate. Solo anuncios recientes, para que uno viejo con
    # muchos favoritos acumulados no tape a lo que está despegando ahora.
    tasas = obtener_tasas_cambio()
    validos = [r for r in resultados if _precio_valido(r, tasas) and _es_reciente(r)]
    validos.sort(key=lambda r: (r["velocidad_favoritos"], r["favoritos"]), reverse=True)
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
        f"📊 Resumen Vinted — mejores para vender ahora\n\n"
        f"Escaneos analizados: {len(escaneos)}\n"
        f"Anuncios activos ≥{PRECIO_MINIMO}€ y vistos por primera vez hace ≤{EDAD_MAXIMA_DIAS} días: {total_validos}"
    )
    enviar_mensaje(intro, chat_id=chat_id)

    if not top:
        enviar_mensaje(
            f"No hay anuncios recientes (≤{EDAD_MAXIMA_DIAS} días) de ≥{PRECIO_MINIMO}€ todavía. Prueba más tarde.",
            chat_id=chat_id,
        )
    else:
        for r in top:
            crecimiento_txt = (
                f"+{r['crecimiento_favoritos']} favs en {r['horas_visible']}h "
                f"({r['velocidad_favoritos']} favs/h)"
                if r["num_apariciones"] >= 2 else "recién detectado"
            )
            caption = (
                f"{r['titulo']}\n"
                f"Marca: {r['marca'] or 's/marca'}\n"
                f"Precio: {r['precio']}{simbolo_moneda(r.get('moneda'))}\n"
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


def enviar_top_racha_telegram(filas, chat_id=None, dias=EDAD_MAXIMA_DIAS):
    """
    Comando separado del resumen normal: los 10 anuncios que MÁS RÁPIDO han
    subido de favoritos en los últimos `dias` días (no solo en el último
    escaneo, sino mirando toda esa ventana de tiempo).
    """
    tasas = obtener_tasas_cambio()
    top = analizar_top_racha(filas, dias=dias, precio_minimo=PRECIO_MINIMO, top_n=10, tasas=tasas)

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
            f"Precio: {r['precio']}{simbolo_moneda(r.get('moneda'))}\n"
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


def enviar_modelos_tendencia_telegram(filas, chat_id=None, dias=EDAD_MAXIMA_DIAS):
    """
    A diferencia de /resumen y /top (que muestran anuncios sueltos), esto
    agrupa por marca+modelo para enseñar qué SE REPITE como tendencia entre
    varios vendedores distintos — la señal más fiable de "esto se vende
    bien", útil para decidir qué buscar al comprar para revender.
    """
    tasas = obtener_tasas_cambio()
    tendencias = analizar_modelos_tendencia(
        filas, dias=dias, precio_minimo=PRECIO_MINIMO, min_anuncios=3, top_n=10, tasas=tasas
    )

    if not tendencias:
        enviar_mensaje(
            f"🏆 Modelos en tendencia (últimos {dias} días)\n\n"
            f"Todavía no hay ningún modelo visto en 3+ anuncios distintos de ≥{PRECIO_MINIMO}€ "
            "en este periodo. Prueba más tarde.",
            chat_id=chat_id,
        )
        return

    enviar_mensaje(
        f"🏆 Modelos en tendencia (últimos {dias} días)\n\n"
        "Marca + modelo que se repite con buen interés entre varios vendedores "
        "distintos (no solo un anuncio suelto con suerte).",
        chat_id=chat_id,
    )

    for i, t in enumerate(tendencias, start=1):
        caption = (
            f"#{i} — {t['marca'] or 's/marca'} {t['modelo']}\n"
            f"Visto en {t['num_anuncios']} anuncios distintos\n"
            f"Favoritos medios: {t['favoritos_media']} | Ritmo medio: {t['velocidad_media']} favs/h\n"
            f"Precio medio: ~{t['precio_medio_eur']}€\n"
            f"Ejemplo: {t['ejemplo_titulo']}\n"
            f"{t['ejemplo_url']}"
        )
        enviar_mensaje(caption, chat_id=chat_id)


if __name__ == "__main__":
    if not os.path.exists(ARCHIVO_HISTORIAL):
        print("Todavía no hay historial. Ejecuta escanear.py primero.")
    else:
        filas = cargar_historial()
        resultados, escaneos = analizar_interes(filas)
        enviar_resumen_telegram(resultados, escaneos)
        print("✅ Resumen enviado por Telegram.")
