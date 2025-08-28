import os
import re
import io
import time
import uuid
import shutil
from datetime import datetime
from typing import List, Generator

from flask import Flask, render_template, request, Response, send_from_directory, jsonify, abort

from gtts import gTTS

# --- Config ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIO_DIR = os.path.join(BASE_DIR, "audio")
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

os.makedirs(AUDIO_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(TEMPLATES_DIR, exist_ok=True)

# Máximo de archivos a conservar en el archivo local (y mostrar en UI)
ARCHIVE_MAX = 3

# Cache temporal en memoria para poder hacer GET de /stream/<token>
CACHE = {}  # token -> {"text": str, "lang": "es|en", "ts": float}

app = Flask(__name__, static_url_path="/static", static_folder="static", template_folder="templates")


# --------- Utilidades ---------
def _sanitize_filename(name: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    return name[:120]


def _list_audio_sorted() -> List[str]:
    files = [f for f in os.listdir(AUDIO_DIR) if f.lower().endswith(".mp3")]
    files.sort(key=lambda fn: os.path.getmtime(os.path.join(AUDIO_DIR, fn)), reverse=True)
    return files


def _enforce_archive_limit():
    files = _list_audio_sorted()
    for f in files[ARCHIVE_MAX:]:
        try:
            os.remove(os.path.join(AUDIO_DIR, f))
        except Exception:
            pass


def _split_text(text: str, max_len: int = 220) -> List[str]:
    """
    Partimos el texto en trozos aptos para gTTS, priorizando límites por oraciones,
    pero asegurando un largo acotado. Así podemos 'streamear' concatenando MP3.
    """
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []

    # Primero, cortar por oraciones “suaves”
    raw_parts = re.split(r"(?<=[\.\!\?\;…])\s+", text)
    chunks: List[str] = []
    buf = ""
    for part in raw_parts:
        if not part:
            continue
        candidate = (buf + " " + part).strip() if buf else part
        if len(candidate) <= max_len:
            buf = candidate
        else:
            if buf:
                chunks.append(buf)
            # si el part es muy largo, forzamos subcortes duros
            while len(part) > max_len:
                # cortar en espacio más cercano antes de max_len
                cut = part.rfind(" ", 0, max_len)
                if cut == -1:
                    cut = max_len
                chunks.append(part[:cut].strip())
                part = part[cut:].strip()
            if part:
                buf = part
            else:
                buf = ""
    if buf:
        chunks.append(buf)
    return chunks


def _yield_gtts_mp3_chunks(text: str, lang: str) -> Generator[bytes, None, None]:
    """
    Genera MP3s trozo a trozo con gTTS y los va emitiendo.
    Concatenar MP3 es válido: el navegador lo reproduce como un continuo.
    """
    chunks = _split_text(text)
    total = len(chunks)
    if total == 0:
        return

    for idx, piece in enumerate(chunks, start=1):
        # gTTS genera un MP3 por trozo
        mp3_buf = io.BytesIO()
        tts = gTTS(text=piece, lang=lang, slow=False)
        tts.write_to_fp(mp3_buf)
        mp3_buf.seek(0)
        data = mp3_buf.read()
        yield data  # Enviamos inmediatamente este bloque


# --------- Rutas ---------
@app.route("/")
def index():
    files = _list_audio_sorted()[:ARCHIVE_MAX]
    return render_template("index.html", items=files)


@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(STATIC_DIR, filename)


@app.route("/audio/<path:filename>")
def audio_files(filename):
    safe = _sanitize_filename(filename)
    path = os.path.join(AUDIO_DIR, safe)
    if not os.path.isfile(path):
        abort(404)
    return send_from_directory(AUDIO_DIR, safe, mimetype="audio/mpeg", as_attachment=False)


@app.route("/api/cache-text", methods=["POST"])
def api_cache_text():
    """
    Recibe {text, lang} y retorna un token para que el <audio> haga GET /stream/<token>.
    Esto evita URLs gigantes y permite streaming GET.
    """
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    lang = (data.get("lang") or "es").lower()
    if lang not in ("es", "en"):
        lang = "es"

    if not text:
        return jsonify({"ok": False, "error": "Texto vacío."}), 400

    token = uuid.uuid4().hex
    CACHE[token] = {"text": text, "lang": lang, "ts": time.time()}
    # limpieza básica del cache (5 min)
    now = time.time()
    for k, v in list(CACHE.items()):
        if now - v.get("ts", now) > 300:
            CACHE.pop(k, None)

    return jsonify({"ok": True, "token": token})


@app.route("/stream/<token>")
def stream_audio(token):
    """
    Stream de audio/mpeg por chunks gTTS.
    Mientras streameamos, también vamos acumulando en un archivo final
    y al terminar lo agregamos al archivo local (limitado a ARCHIVE_MAX).
    """
    info = CACHE.pop(token, None)
    if not info:
        return abort(404)

    text = info["text"]
    lang = info["lang"]

    # generamos un nombre destino con timestamp
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    safe_prefix = _sanitize_filename(text[:40]) or f"tts_{ts}"
    filename = f"{safe_prefix}_{ts}.mp3"
    tmp_path = os.path.join(AUDIO_DIR, f".tmp_{uuid.uuid4().hex}.mp3")
    final_path = os.path.join(AUDIO_DIR, filename)

    def generate():
        # Vamos teendo los bytes al archivo mientras también los emitimos
        with open(tmp_path, "wb") as out:
            for block in _yield_gtts_mp3_chunks(text, lang):
                out.write(block)
                out.flush()
                yield block

        # Terminado el stream, movemos a final y limpiamos archivo viejo si sobra
        try:
            shutil.move(tmp_path, final_path)
        except Exception:
            # como fallback, intentamos copiar y borrar
            try:
                shutil.copyfile(tmp_path, final_path)
            finally:
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

        # Enforce to 3 últimos
        _enforce_archive_limit()

    # Importante: no usar Content-Length para permitir chunked
    return Response(generate(), mimetype="audio/mpeg", direct_passthrough=True)


@app.route("/api/delete", methods=["POST"])
def api_delete():
    data = request.get_json(silent=True) or {}
    fname = _sanitize_filename((data.get("file") or "").strip())
    if not fname:
        return jsonify({"ok": False, "error": "Archivo inválido."}), 400
    fpath = os.path.join(AUDIO_DIR, fname)
    if os.path.isfile(fpath):
        try:
            os.remove(fpath)
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "No existe."}), 404


if __name__ == "__main__":
    # Para correr local: python app.py
    app.run(host="0.0.0.0", port=5000, debug=True)
