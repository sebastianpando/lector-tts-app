import os
import uuid
import re
from datetime import datetime
from flask import Flask, request, send_from_directory, jsonify, render_template, make_response
from gtts import gTTS

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
AUDIO_DIR = os.path.join(APP_ROOT, "audio")
os.makedirs(AUDIO_DIR, exist_ok=True)

# Sesiones en memoria: { session_id: {"lang": "es", "chunks": [str, ...]} }
SESSIONS = {}

app = Flask(__name__, static_url_path="/static", static_folder="static", template_folder="templates")

# ---------- Utilidades ----------

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
            else:
                buf = ""
    if buf:
        chunks.append(buf.strip())

    # Garantiza que no haya vacíos
    return [c for c in chunks if c]

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

def corsify(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp

# ---------- Rutas ----------

@app.route("/")
def index():
    items = list_audio_files(limit=3)
    return render_template("index.html", items=items)

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

    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    lang = data.get("lang") or "es"
    if not text:
        return corsify(make_response(jsonify({"error": "Texto vacío"}), 400))

    chunks = split_text_for_tts(text, max_chars=240)
    if not chunks:
        return corsify(make_response(jsonify({"error": "No hay contenido utilizable"}), 400))

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

@app.route("/api/chunk/<session_id>/<int:idx>")
def api_chunk(session_id, idx):
    info = SESSIONS.get(session_id)
    if not info:
        return corsify(make_response(jsonify({"error": "Sesión no encontrada"}), 404))
    chunks = info["chunks"]
    lang = info["lang"]

    if idx < 0 or idx >= len(chunks):
        return corsify(make_response(jsonify({"error": "Índice fuera de rango"}), 400))

    # Genera el mp3 del segmento a demanda (cache simple en disco por si se repite)
    safe_name = f"{session_id}_{idx}.mp3"
    out_path = os.path.join(AUDIO_DIR, safe_name)
    if not os.path.exists(out_path):
        try:
            tts_to_file(chunks[idx], lang, out_path)
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
