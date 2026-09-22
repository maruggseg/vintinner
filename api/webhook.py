"""
Webhook para Vercel: Telegram llama directamente a esta función en cuanto
alguien le escribe al bot, así que la respuesta es casi instantánea (nada
de esperar a que GitHub Actions revise cada X minutos).

Es autocontenida (no importa los demás archivos del proyecto) para evitar
líos de rutas dentro del entorno de Vercel.

Variable de entorno necesaria en Vercel: TELEGRAM_TOKEN
"""

import os
import csv
import json
import re
from datetime import datetime, timedelta
from collections import defaultdict
from http.server import BaseHTTPRequestHandler

import requests

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
DOMINIO_TELEGRAM = "https://api.telegram.org/bot" + TELEGRAM_TOKEN

ARCHIVO_HISTORIAL = os.path.join(os.path.dirname(__file__), "..", "data", "historial.csv")
PRECIO_MINIMO = 70
EDAD_MAXIMA_DIAS = 7  # ignoramos anuncios que llevamos rastreando más tiempo que esto: ya no son "nuevos"

TASAS_RESPALDO = {"EUR": 1.0, "USD": 1.08, "GBP": 0.86}


def obtener_tasas_cambio() -> dict:
    """Tasas a EUR (unidades de esa moneda por 1 EUR); respaldo fijo si la API falla."""
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


def enviar_mensaje(texto, chat_id):
    requests.post(f"{DOMINIO_TELEGRAM}/sendMessage", data={
        "chat_id": chat_id, "text": texto, "disable_web_page_preview": True,
    }, timeout=15)


def enviar_foto(foto_url, caption, chat_id):
    try:
        resp = requests.post(f"{DOMINIO_TELEGRAM}/sendPhoto", data={
            "chat_id": chat_id, "photo": foto_url, "caption": caption,
        }, timeout=15)
        return resp.status_code == 200
    except requests.RequestException:
        return False


def cargar_historial():
    filas = []
    if not os.path.exists(ARCHIVO_HISTORIAL):
        return filas
    with open(ARCHIVO_HISTORIAL, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for fila in reader:
            fila["fecha_escaneo"] = datetime.fromisoformat(fila["fecha_escaneo"])
            filas.append(fila)
    return filas


def _precio_en_eur(precio_str, moneda, tasas) -> float:
    try:
        precio = float(precio_str)
    except (TypeError, ValueError):
        return 0.0
    tasa = tasas.get(moneda or "EUR", 1.0) or 1.0
    return precio / tasa


def _precio_valido(precio_str, moneda, tasas):
    return _precio_en_eur(precio_str, moneda, tasas) >= PRECIO_MINIMO


SIMBOLOS_MONEDA = {"EUR": "€", "USD": "$", "GBP": "£"}


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
    """Ver la versión gemela en analizar.py — misma heurística, código
    duplicado a propósito porque este archivo es autocontenido para Vercel."""
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
            continue
        candidatas.append(p)
        if len(candidatas) == 2:
            break

    return " ".join(candidatas)


def simbolo_moneda(moneda) -> str:
    """
    Vinted a veces muestra anuncios en otra moneda según la IP de quien
    pregunta, así que no forzamos EUR al guardar — mostramos el símbolo
    que corresponda a cada anuncio en concreto.
    """
    if not moneda:
        return "€"
    return SIMBOLOS_MONEDA.get(moneda, f" {moneda}")


def comando_resumen(chat_id):
    filas = cargar_historial()
    if not filas:
        enviar_mensaje("Todavía no hay ningún escaneo guardado.", chat_id)
        return

    escaneos = sorted(set(f["fecha_escaneo"] for f in filas))
    if len(escaneos) < 2:
        enviar_mensaje(f"Solo hay {len(escaneos)} escaneo(s) todavía. Prueba más tarde.", chat_id)
        return

    ultimo = escaneos[-1]
    tasas = obtener_tasas_cambio()
    por_item = defaultdict(list)
    for f in filas:
        por_item[f["item_id"]].append(f)

    resultados = []
    for item_id, apariciones in por_item.items():
        apariciones.sort(key=lambda x: x["fecha_escaneo"])
        if apariciones[-1]["fecha_escaneo"] != ultimo:
            continue
        if not _precio_valido(apariciones[-1]["precio"], apariciones[-1].get("moneda"), tasas):
            continue

        primera, ultima = apariciones[0], apariciones[-1]
        horas = (ultima["fecha_escaneo"] - primera["fecha_escaneo"]).total_seconds() / 3600
        if horas > EDAD_MAXIMA_DIAS * 24:
            continue  # lo llevamos rastreando demasiado tiempo, ya no cuenta como "reciente"

        fav_ahora = int(ultima["favoritos"] or 0)
        fav_inicio = int(primera["favoritos"] or 0)
        crecimiento = fav_ahora - fav_inicio
        velocidad = crecimiento / (horas + 1) if len(apariciones) >= 2 else 0.0

        resultados.append({
            "titulo": ultima["titulo"], "marca": ultima["marca"], "precio": ultima["precio"],
            "moneda": ultima.get("moneda", "EUR"),
            "favoritos": fav_ahora, "crecimiento": crecimiento, "horas": round(horas, 1),
            "velocidad": round(velocidad, 2), "url": ultima["url"], "foto_url": ultima.get("foto_url", ""),
            "num_apariciones": len(apariciones),
        })

    # Primero velocidad (lo que "se mueve" ahora), favoritos totales como desempate.
    resultados.sort(key=lambda r: (r["velocidad"], r["favoritos"]), reverse=True)
    top = resultados[:8]

    enviar_mensaje(
        f"📊 Resumen Vinted — mejores para vender ahora\n\n"
        f"Escaneos analizados: {len(escaneos)}\n"
        f"Anuncios activos ≥{PRECIO_MINIMO}€ y vistos por primera vez hace ≤{EDAD_MAXIMA_DIAS} días: {len(resultados)}",
        chat_id,
    )

    if not top:
        enviar_mensaje(f"No hay anuncios recientes (≤{EDAD_MAXIMA_DIAS} días) de ≥{PRECIO_MINIMO}€ todavía.", chat_id)
        return

    for r in top:
        crecimiento_txt = (
            f"+{r['crecimiento']} favs en {r['horas']}h ({r['velocidad']} favs/h)"
            if r["num_apariciones"] >= 2 else "recién detectado"
        )
        caption = (
            f"{r['titulo']}\nMarca: {r['marca'] or 's/marca'}\nPrecio: {r['precio']}{simbolo_moneda(r.get('moneda'))}\n"
            f"Favoritos ahora: {r['favoritos']} ({crecimiento_txt})\n{r['url']}"
        )
        if r.get("foto_url") and not enviar_foto(r["foto_url"], caption, chat_id):
            enviar_mensaje(caption, chat_id)
        elif not r.get("foto_url"):
            enviar_mensaje(caption, chat_id)

    por_marca = defaultdict(list)
    for r in resultados:
        if r["marca"]:
            por_marca[r["marca"]].append(r["favoritos"])
    ranking = sorted(por_marca.items(), key=lambda kv: sum(kv[1]) / len(kv[1]), reverse=True)[:8]
    if ranking:
        lineas = ["📈 Marcas con más interés:", ""]
        for marca, favs in ranking:
            lineas.append(f"- {marca}: {round(sum(favs)/len(favs), 2)} ({len(favs)} anuncios)")
        enviar_mensaje("\n".join(lineas), chat_id)


def comando_top(chat_id, dias=EDAD_MAXIMA_DIAS):
    filas = cargar_historial()
    if not filas:
        enviar_mensaje("Todavía no hay ningún escaneo guardado.", chat_id)
        return

    limite = datetime.now() - timedelta(days=dias)
    filas_periodo = [f for f in filas if f["fecha_escaneo"] >= limite]

    tasas = obtener_tasas_cambio()
    por_item = defaultdict(list)
    for f in filas_periodo:
        por_item[f["item_id"]].append(f)

    candidatos = []
    for item_id, apariciones in por_item.items():
        apariciones.sort(key=lambda x: x["fecha_escaneo"])
        if len(apariciones) < 2:
            continue
        if not _precio_valido(apariciones[-1]["precio"], apariciones[-1].get("moneda"), tasas):
            continue

        primera, ultima = apariciones[0], apariciones[-1]
        fav_inicio = int(primera["favoritos"] or 0)
        fav_ahora = int(ultima["favoritos"] or 0)
        crecimiento = fav_ahora - fav_inicio
        if crecimiento <= 0:
            continue

        horas = (ultima["fecha_escaneo"] - primera["fecha_escaneo"]).total_seconds() / 3600
        velocidad = crecimiento / (horas + 1)

        candidatos.append({
            "titulo": ultima["titulo"], "marca": ultima["marca"], "precio": ultima["precio"],
            "moneda": ultima.get("moneda", "EUR"),
            "favoritos_inicio": fav_inicio, "favoritos_ahora": fav_ahora, "crecimiento": crecimiento,
            "horas": round(horas, 1), "velocidad": velocidad, "url": ultima["url"],
            "foto_url": ultima.get("foto_url", ""),
        })

    candidatos.sort(key=lambda r: (r["velocidad"], r["crecimiento"]), reverse=True)
    top = candidatos[:10]

    if not top:
        enviar_mensaje(
            f"🚀 Top con más subida de favoritos ({dias} días)\n\n"
            f"Todavía no hay suficientes datos o ningún anuncio ≥{PRECIO_MINIMO}€ ha ganado favoritos. Prueba más tarde.",
            chat_id,
        )
        return

    enviar_mensaje(f"🚀 Top 10 con más subida de favoritos (últimos {dias} días)", chat_id)

    for i, r in enumerate(top, start=1):
        caption = (
            f"#{i} — {r['titulo']}\nMarca: {r['marca'] or 's/marca'}\nPrecio: {r['precio']}{simbolo_moneda(r.get('moneda'))}\n"
            f"Favoritos: {r['favoritos_inicio']} → {r['favoritos_ahora']} (+{r['crecimiento']} en {r['horas']}h)\n{r['url']}"
        )
        if r.get("foto_url") and not enviar_foto(r["foto_url"], caption, chat_id):
            enviar_mensaje(caption, chat_id)
        elif not r.get("foto_url"):
            enviar_mensaje(caption, chat_id)


def comando_modelos(chat_id, dias=EDAD_MAXIMA_DIAS, min_anuncios=3):
    """
    A diferencia de /resumen y /top (anuncios sueltos), agrupa por
    marca+modelo (heurística sobre el título) para ver qué modelo se
    repite con buen interés entre varios vendedores distintos — señal más
    fiable de "esto se vende bien" que un anuncio suelto con suerte.
    """
    filas = cargar_historial()
    if not filas:
        enviar_mensaje("Todavía no hay ningún escaneo guardado.", chat_id)
        return

    limite = datetime.now() - timedelta(days=dias)
    filas_periodo = [f for f in filas if f["fecha_escaneo"] >= limite]

    tasas = obtener_tasas_cambio()
    por_item = defaultdict(list)
    for f in filas_periodo:
        por_item[f["item_id"]].append(f)

    resumen_items = []
    for item_id, apariciones in por_item.items():
        apariciones.sort(key=lambda x: x["fecha_escaneo"])
        primera, ultima = apariciones[0], apariciones[-1]

        precio_eur = _precio_en_eur(ultima["precio"], ultima.get("moneda"), tasas)
        if precio_eur < PRECIO_MINIMO:
            continue

        marca = (ultima.get("marca") or "").strip()
        modelo = extraer_modelo(ultima.get("titulo", ""), marca)
        if not modelo:
            continue

        fav_ahora = int(ultima["favoritos"] or 0)
        fav_inicio = int(primera["favoritos"] or 0)
        horas = (ultima["fecha_escaneo"] - primera["fecha_escaneo"]).total_seconds() / 3600
        velocidad = (fav_ahora - fav_inicio) / (horas + 1) if len(apariciones) >= 2 else 0.0

        resumen_items.append({
            "item_id": item_id, "marca": marca, "modelo": modelo,
            "precio_eur": precio_eur, "favoritos": fav_ahora, "velocidad": velocidad,
            "titulo": ultima.get("titulo", ""), "url": ultima.get("url", ""),
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
            "marca": marca, "modelo": modelo,
            "num_anuncios": len({i["item_id"] for i in items}),
            "velocidad_media": round(velocidad_media, 2),
            "favoritos_media": round(favoritos_media, 1),
            "precio_medio_eur": round(precio_medio, 1),
            "ejemplo_titulo": ejemplo["titulo"], "ejemplo_url": ejemplo["url"],
        })

    tendencias.sort(key=lambda t: (t["velocidad_media"], t["num_anuncios"]), reverse=True)
    tendencias = tendencias[:10]

    if not tendencias:
        enviar_mensaje(
            f"🏆 Modelos en tendencia (últimos {dias} días)\n\n"
            f"Todavía no hay ningún modelo visto en {min_anuncios}+ anuncios distintos de "
            f"≥{PRECIO_MINIMO}€ en este periodo. Prueba más tarde.",
            chat_id,
        )
        return

    enviar_mensaje(
        f"🏆 Modelos en tendencia (últimos {dias} días)\n\n"
        "Marca + modelo que se repite con buen interés entre varios vendedores "
        "distintos (no solo un anuncio suelto con suerte).",
        chat_id,
    )

    for i, t in enumerate(tendencias, start=1):
        caption = (
            f"#{i} — {t['marca'] or 's/marca'} {t['modelo']}\n"
            f"Visto en {t['num_anuncios']} anuncios distintos\n"
            f"Favoritos medios: {t['favoritos_media']} | Ritmo medio: {t['velocidad_media']} favs/h\n"
            f"Precio medio: ~{t['precio_medio_eur']}€\n"
            f"Ejemplo: {t['ejemplo_titulo']}\n{t['ejemplo_url']}"
        )
        enviar_mensaje(caption, chat_id)


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            longitud = int(self.headers.get("Content-Length", 0))
            cuerpo = self.rfile.read(longitud)
            update = json.loads(cuerpo)

            mensaje = update.get("message", {})
            texto = (mensaje.get("text") or "").strip().lower()
            chat_id = mensaje.get("chat", {}).get("id")

            if chat_id:
                if texto in ("/resumen", "resumen", "/start"):
                    comando_resumen(chat_id)
                elif texto in ("/top", "top"):
                    comando_top(chat_id)
                elif texto in ("/modelos", "modelos"):
                    comando_modelos(chat_id)
        except Exception as e:
            print(f"Error procesando update: {e}")

        # Siempre respondemos 200 rápido para que Telegram no reintente.
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")
