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
from datetime import datetime, timedelta
from collections import defaultdict
from http.server import BaseHTTPRequestHandler

import requests

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
DOMINIO_TELEGRAM = "https://api.telegram.org/bot" + TELEGRAM_TOKEN

ARCHIVO_HISTORIAL = os.path.join(os.path.dirname(__file__), "..", "data", "historial.csv")
PRECIO_MINIMO = 60


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


def _precio_valido(precio_str):
    try:
        return float(precio_str) >= PRECIO_MINIMO
    except (TypeError, ValueError):
        return False


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
    por_item = defaultdict(list)
    for f in filas:
        por_item[f["item_id"]].append(f)

    resultados = []
    for item_id, apariciones in por_item.items():
        apariciones.sort(key=lambda x: x["fecha_escaneo"])
        if apariciones[-1]["fecha_escaneo"] != ultimo:
            continue
        if not _precio_valido(apariciones[-1]["precio"]):
            continue

        primera, ultima = apariciones[0], apariciones[-1]
        horas = (ultima["fecha_escaneo"] - primera["fecha_escaneo"]).total_seconds() / 3600
        fav_ahora = int(ultima["favoritos"] or 0)
        fav_inicio = int(primera["favoritos"] or 0)
        crecimiento = fav_ahora - fav_inicio
        velocidad = crecimiento / (horas + 1) if len(apariciones) >= 2 else 0.0

        resultados.append({
            "titulo": ultima["titulo"], "marca": ultima["marca"], "precio": ultima["precio"],
            "favoritos": fav_ahora, "crecimiento": crecimiento, "horas": round(horas, 1),
            "velocidad": velocidad, "url": ultima["url"], "foto_url": ultima.get("foto_url", ""),
            "num_apariciones": len(apariciones),
        })

    resultados.sort(key=lambda r: (r["favoritos"], r["velocidad"]), reverse=True)
    top = resultados[:8]

    enviar_mensaje(
        f"📊 Resumen Vinted\n\nEscaneos analizados: {len(escaneos)}\nAnuncios activos ≥{PRECIO_MINIMO}€: {len(resultados)}",
        chat_id,
    )

    if not top:
        enviar_mensaje(f"No hay anuncios activos de ≥{PRECIO_MINIMO}€ todavía.", chat_id)
        return

    for r in top:
        crecimiento_txt = f"+{r['crecimiento']} favs en {r['horas']}h" if r["num_apariciones"] >= 2 else "recién detectado"
        caption = (
            f"{r['titulo']}\nMarca: {r['marca'] or 's/marca'}\nPrecio: {r['precio']}€\n"
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


def comando_top(chat_id, dias=5):
    filas = cargar_historial()
    if not filas:
        enviar_mensaje("Todavía no hay ningún escaneo guardado.", chat_id)
        return

    limite = datetime.now() - timedelta(days=dias)
    filas_periodo = [f for f in filas if f["fecha_escaneo"] >= limite]

    por_item = defaultdict(list)
    for f in filas_periodo:
        por_item[f["item_id"]].append(f)

    candidatos = []
    for item_id, apariciones in por_item.items():
        apariciones.sort(key=lambda x: x["fecha_escaneo"])
        if len(apariciones) < 2:
            continue
        if not _precio_valido(apariciones[-1]["precio"]):
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
            "favoritos_inicio": fav_inicio, "favoritos_ahora": fav_ahora, "crecimiento": crecimiento,
            "horas": round(horas, 1), "velocidad": velocidad, "url": ultima["url"],
            "foto_url": ultima.get("foto_url", ""),
        })

    candidatos.sort(key=lambda r: (r["velocidad"], r["crecimiento"]), reverse=True)
    top = candidatos[:5]

    if not top:
        enviar_mensaje(
            f"🚀 Top con más subida de favoritos ({dias} días)\n\n"
            f"Todavía no hay suficientes datos o ningún anuncio ≥{PRECIO_MINIMO}€ ha ganado favoritos. Prueba más tarde.",
            chat_id,
        )
        return

    enviar_mensaje(f"🚀 Top 5 con más subida de favoritos (últimos {dias} días)", chat_id)

    for i, r in enumerate(top, start=1):
        caption = (
            f"#{i} — {r['titulo']}\nMarca: {r['marca'] or 's/marca'}\nPrecio: {r['precio']}€\n"
            f"Favoritos: {r['favoritos_inicio']} → {r['favoritos_ahora']} (+{r['crecimiento']} en {r['horas']}h)\n{r['url']}"
        )
        if r.get("foto_url") and not enviar_foto(r["foto_url"], caption, chat_id):
            enviar_mensaje(caption, chat_id)
        elif not r.get("foto_url"):
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
        except Exception as e:
            print(f"Error procesando update: {e}")

        # Siempre respondemos 200 rápido para que Telegram no reintente.
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")

