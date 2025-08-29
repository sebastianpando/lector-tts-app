import os
import uuid
<<<<<<< HEAD
import re
from datetime import datetime
from flask import Flask, request, send_from_directory, jsonify, render_template, make_response
=======
import shutil
import secrets
from datetime import datetime
from typing import List, Generator, Dict, Deque
from collections import deque

from flask import (
    Flask, render_template, request, Response, send_from_directory,
    jsonify, abort, make_response
)
>>>>>>> 423cd10 (Fix iOS playback + playbackRate; prebuffer; no-store; CSRF; RL; workers=1)
from gtts import gTTS

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
AUDIO_DIR = os.path.join(APP_ROOT, "audio")
os.makedirs(AUDIO_DIR, exist_ok=True)

<<<<<<< HEAD
# Sesiones en memoria: { session_id: {"lang": "es", "chunks": [str, ...]} }
SESSIONS = {}
=======
# Máximo de archivos a conservar en el archivo local (y mostrar en UI)
ARCHIVE_MAX = 3

# Límites y rate limit (anti abuso)
MAX_TEXT_CHARS = 15000
RL_WINDOW_SECONDS = 60
RL_MAX_REQUESTS = 10

# Cache temporal en memoria para /stream/<token>
# (con --workers 1, esto es seguro)
CACHE: Dict[str, Dict[str, object]] = {}

# Rate limit por IP (en memoria)
RATE_LIMIT: Dict[str, Deque[float]] = {}

# CSRF
CSRF_COOKIE_NAME = "csrf_token"
>>>>>>> 423cd10 (Fix iOS playback + playbackRate; prebuffer; no-store; CSRF; RL; workers=1)

app = Flask(__name__, static_url_path="/static", static_folder="static", template_folder="templates")

# ---------- Utilidades ----------

<<<<<<< HEAD
def split_text_for_tts(txt: str, max_chars=240):
    """
    Divide el texto en segmentos amigables para TTS.
    Preferimos cortar por punto/fin de oración; si no, por longitud.
    """
    txt = txt.strip()
    if not txt:
        return []

    # Primero intenta dividir por oraciones
    parts = re.split(r'(?<=[\.\!\?])\s+', txt)
    chunks = []
=======
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
    """Divide el texto en trozos aptos para gTTS."""
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []

    raw_parts = re.split(r"(?<=[\.\!\?\;…])\s+", text)
    chunks: List[str] = []
>>>>>>> 423cd10 (Fix iOS playback + playbackRate; prebuffer; no-store; CSRF; RL; workers=1)
    buf = ""

    for p in parts:
        if not p:
            continue
        candidate = (buf + " " + p).strip() if buf else p
        if len(candidate) <= max_chars:
            buf = candidate
        else:
            if buf:
                chunks.append(buf)
<<<<<<< HEAD
            # si p es muy largo, lo troceamos duro
            while len(p) > max_chars:
                cut = p[:max_chars]
                # evita cortar palabras largas si se puede
                last_space = cut.rfind(" ")
                if last_space > 60:
                    cut = cut[:last_space]
                chunks.append(cut.strip())
                p = p[len(cut):].strip()
            if p:
                buf = p
=======
            while len(part) > max_len:
                cut = part.rfind(" ", 0, max_len)
                if cut == -1:
                    cut = max_len
                chunks.append(part[:cut].strip())
                part = part[cut:].strip()
            if part:
                buf = part
>>>>>>> 423cd10 (Fix iOS playback + playbackRate; prebuffer; no-store; CSRF; RL; workers=1)
            else:
                buf = ""
    if buf:
        chunks.append(buf.strip())

    # Garantiza que no haya vacíos
    return [c for c in chunks if c]

<<<<<<< HEAD
def tts_to_file(text: str, lang: str, out_path: str):
    tts = gTTS(text=text, lang=lang, slow=False)
    tts.save(out_path)

def list_audio_files(limit=3):
    try:
        files = [f for f in os.listdir(AUDIO_DIR) if f.lower().endswith(".mp3")]
    except FileNotFoundError:
        return []
    files.sort(key=lambda f: os.path.getmtime(os.path.join(AUDIO_DIR, f)), reverse=True)
    return files[:limit]
=======
def _yield_gtts_mp3_chunks(text: str, lang: str) -> Generator[bytes, None, None]:
    """Genera MP3 por trozos con gTTS y los emite."""
    chunks = _split_text(text)
    if not chunks:
        return
    for piece in chunks:
        mp3_buf = io.BytesIO()
        tts = gTTS(text=piece, lang=lang, slow=False)
        tts.write_to_fp(mp3_buf)
        mp3_buf.seek(0)
        yield mp3_buf.read()


def _client_ip() -> str:
    fwd = request.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.remote_addr or "0.0.0.0"


def _rate_limited(ip: str) -> bool:
    now = time.time()
    dq = RATE_LIMIT.setdefault(ip, deque())
    while dq and (now - dq[0]) > RL_WINDOW_SECONDS:
        dq.popleft()
    if len(dq) >= RL_MAX_REQUESTS:
        return True
    dq.append(now)
    return False


def _ensure_csrf_cookie(resp: Response):
    token = request.cookies.get(CSRF_COOKIE_NAME)
    if not token:
        token = secrets.token_urlsafe(32)
        resp.set_cookie(
            CSRF_COOKIE_NAME,
            token,
            secure=True,
            httponly=False,  # necesario para double-submit cookie
            samesite="Lax",
            max_age=60 * 60 * 24 * 7
        )
    return resp


def _check_csrf():
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME, "")
    header_token = request.headers.get("X-CSRF-Token", "")
    if not cookie_token or not header_token or cookie_token != header_token:
        abort(403, description="CSRF token inválido")


# --------- Headers globales de seguridad ---------
@app.after_request
def add_security_headers(resp: Response):
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data:; media-src 'self'; "
        "script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'"
    )
    resp.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains; preload")
    return resp
>>>>>>> 423cd10 (Fix iOS playback + playbackRate; prebuffer; no-store; CSRF; RL; workers=1)

def corsify(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp

# ---------- Rutas ----------

@app.route("/")
def index():
<<<<<<< HEAD
    items = list_audio_files(limit=3)
    return render_template("index.html", items=items)
=======
    files = _list_audio_sorted()[:ARCHIVE_MAX]
    resp = make_response(render_template("index.html", items=files))
    return _ensure_csrf_cookie(resp)


@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(STATIC_DIR, filename)

>>>>>>> 423cd10 (Fix iOS playback + playbackRate; prebuffer; no-store; CSRF; RL; workers=1)

@app.route("/audio/<path:filename>")
def audio_file(filename):
    # Archivos exportados completos (no los segmentados)
    resp = make_response(send_from_directory(AUDIO_DIR, filename, mimetype="audio/mpeg", as_attachment=False))
    resp.headers["Accept-Ranges"] = "bytes"
    resp.headers["Content-Type"] = "audio/mpeg"
    resp.headers["Cache-Control"] = "public, max-age=31536000, no-transform"
    return corsify(resp)

@app.route("/api/manifest", methods=["POST", "OPTIONS"])
def api_manifest():
    if request.method == "OPTIONS":
        return corsify(make_response(("", 204)))

<<<<<<< HEAD
=======
@app.route("/api/cache-text", methods=["POST"])
def api_cache_text():
    ip = _client_ip()
    if _rate_limited(ip):
        return jsonify({"ok": False, "error": "Demasiadas solicitudes. Intenta de nuevo en un momento."}), 429

>>>>>>> 423cd10 (Fix iOS playback + playbackRate; prebuffer; no-store; CSRF; RL; workers=1)
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    lang = data.get("lang") or "es"
    if not text:
        return corsify(make_response(jsonify({"error": "Texto vacío"}), 400))

<<<<<<< HEAD
    chunks = split_text_for_tts(text, max_chars=240)
    if not chunks:
        return corsify(make_response(jsonify({"error": "No hay contenido utilizable"}), 400))
=======
    if len(text) > MAX_TEXT_CHARS:
        return jsonify({"ok": False, "error": f"Texto demasiado largo. Máximo permitido: {MAX_TEXT_CHARS} caracteres."}), 413

    token = uuid.uuid4().hex
    CACHE[token] = {"text": text, "lang": lang, "ts": time.time()}

    # limpieza simple (5 min)
    now = time.time()
    for k, v in list(CACHE.items()):
        if now - v.get("ts", now) > 300:
            CACHE.pop(k, None)
>>>>>>> 423cd10 (Fix iOS playback + playbackRate; prebuffer; no-store; CSRF; RL; workers=1)

    session_id = uuid.uuid4().hex
    SESSIONS[session_id] = {"lang": lang, "chunks": chunks}

    # Devolvemos la cola de reproducción (referencias por índice)
    manifest = {
        "session": session_id,
        "count": len(chunks),
        "lang": lang,
        "chunks": list(range(len(chunks)))
    }
    return corsify(make_response(jsonify(manifest), 200))

<<<<<<< HEAD
@app.route("/api/chunk/<session_id>/<int:idx>")
def api_chunk(session_id, idx):
    info = SESSIONS.get(session_id)
=======
@app.route("/stream/<token>")
def stream_audio(token):
    """
    Stream con:
    - prebuffer (~256KB) antes de emitir (iOS mejora)
    - headers anti-cache/anti-buffering
    """
    info = CACHE.pop(token, None)
>>>>>>> 423cd10 (Fix iOS playback + playbackRate; prebuffer; no-store; CSRF; RL; workers=1)
    if not info:
        return corsify(make_response(jsonify({"error": "Sesión no encontrada"}), 404))
    chunks = info["chunks"]
    lang = info["lang"]

<<<<<<< HEAD
    if idx < 0 or idx >= len(chunks):
        return corsify(make_response(jsonify({"error": "Índice fuera de rango"}), 400))

    # Genera el mp3 del segmento a demanda (cache simple en disco por si se repite)
    safe_name = f"{session_id}_{idx}.mp3"
    out_path = os.path.join(AUDIO_DIR, safe_name)
    if not os.path.exists(out_path):
        try:
            tts_to_file(chunks[idx], lang, out_path)
=======
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    safe_prefix = _sanitize_filename(text[:40]) or f"tts_{ts}"
    filename = f"{safe_prefix}_{ts}.mp3"
    tmp_path = os.path.join(AUDIO_DIR, f".tmp_{uuid.uuid4().hex}.mp3")
    final_path = os.path.join(AUDIO_DIR, filename)

    PREBUFFER_BYTES = 256 * 1024  # ~256 KB

    def generate():
        started = False
        prebuf = bytearray()

        with open(tmp_path, "wb") as out:
            for block in _yield_gtts_mp3_chunks(text, lang):
                out.write(block)
                out.flush()

                if not started:
                    prebuf.extend(block)
                    if len(prebuf) >= PREBUFFER_BYTES:
                        yield bytes(prebuf)
                        started = True
                else:
                    yield block

        if not started and prebuf:
            yield bytes(prebuf)

        try:
            shutil.move(tmp_path, final_path)
        except Exception:
            try:
                shutil.copyfile(tmp_path, final_path)
            finally:
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

        _enforce_archive_limit()

    resp = Response(generate(), mimetype="audio/mpeg", direct_passthrough=True)
    # headers anti-cache/anti-buffering
    resp.headers["X-Accel-Buffering"] = "no"
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@app.route("/api/delete", methods=["POST"])
def api_delete():
    _check_csrf()
    data = request.get_json(silent=True) or {}
    fname = _sanitize_filename((data.get("file") or "").strip())
    if not fname:
        return jsonify({"ok": False, "error": "Archivo inválido."}), 400
    fpath = os.path.join(AUDIO_DIR, fname)
    if os.path.isfile(fpath):
        try:
            os.remove(fpath)
>>>>>>> 423cd10 (Fix iOS playback + playbackRate; prebuffer; no-store; CSRF; RL; workers=1)
        except Exception as e:
            return corsify(make_response(jsonify({"error": f"Fallo TTS: {e}"}), 500))

    resp = make_response(send_from_directory(AUDIO_DIR, safe_name, mimetype="audio/mpeg", as_attachment=False))
    resp.headers["Accept-Ranges"] = "bytes"
    resp.headers["Content-Type"] = "audio/mpeg"
    resp.headers["Cache-Control"] = "no-store"
    return corsify(resp)

@app.route("/api/export", methods=["POST", "OPTIONS"])
def api_export():
    """
    Exporta TODO el texto en un solo MP3, útil para descargar/archivar cuando se terminó de escuchar.
    """
    if request.method == "OPTIONS":
        return corsify(make_response(("", 204)))

    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    lang = data.get("lang") or "es"
    if not text:
        return corsify(make_response(jsonify({"error": "Texto vacío"}), 400))

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    fname = f"tts_{lang}_{ts}.mp3"
    out_path = os.path.join(AUDIO_DIR, fname)

    try:
        tts_to_file(text, lang, out_path)
    except Exception as e:
        return corsify(make_response(jsonify({"error": f"Fallo TTS: {e}"}), 500))

    return corsify(make_response(jsonify({"file": fname, "url": f"/audio/{fname}"}), 200))

# Ping CORS
@app.after_request
def add_cors(resp):
    return corsify(resp)

if __name__ == "__main__":
    # Desarrollo local
    app.run(host="0.0.0.0", port=5000, debug=True)
