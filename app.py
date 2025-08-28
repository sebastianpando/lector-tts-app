import os, io, re, uuid, tempfile, shutil
from datetime import datetime
from flask import Flask, request, Response, render_template, redirect, url_for, abort, send_from_directory, jsonify
from gtts import gTTS

app = Flask(__name__)
ARCHIVE_DIR = os.path.join("static", "archive")
os.makedirs(ARCHIVE_DIR, exist_ok=True)

STREAM_JOBS = {}  # token -> {title, text}
MAX_WORDS = 5000

def slugify(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"[^a-z0-9\-]+", "", s)
    return s[:60] or "lectura"

def split_text(text: str, max_chars: int = 1800):
    text = re.sub(r"\s+", " ", text).strip()
    parts = []
    while text:
        if len(text) <= max_chars:
            parts.append(text); break
        cut = text.rfind(". ", 0, max_chars)
        if cut == -1: cut = text.rfind(" ", 0, max_chars)
        if cut == -1: cut = max_chars
        parts.append(text[:cut+1].strip())
        text = text[cut+1:].strip()
    return parts

@app.route("/", methods=["GET"])
def index():
    items = [f for f in os.listdir(ARCHIVE_DIR) if f.endswith(".mp3")]
    items.sort(reverse=True)
    return render_template("index.html", items=items)

@app.route("/submit", methods=["POST"])
def submit():
    title = (request.form.get("title") or "").strip()
    text  = (request.form.get("text")  or "").strip()
    if not text:
        return redirect(url_for("index"))

    words = len(re.findall(r"\b\w+\b", text))
    if words > MAX_WORDS:
        items = [f for f in os.listdir(ARCHIVE_DIR) if f.endswith(".mp3")]
        items.sort(reverse=True)
        return render_template("index.html", items=items,
                               error=f"Texto supera {MAX_WORDS} palabras ({words}). Córtalo o envíalo en partes.")

    token = str(uuid.uuid4())
    if not title:
        title = text[:40] + ("…" if len(text) > 40 else "")
    STREAM_JOBS[token] = {"title": title, "text": text}
    return redirect(url_for("play", token=token))

@app.route("/play")
def play():
    token = request.args.get("token", "")
    items = [f for f in os.listdir(ARCHIVE_DIR) if f.endswith(".mp3")]
    items.sort(reverse=True)
    title = STREAM_JOBS.get(token, {}).get("title", "")
    return render_template("index.html", items=items, token=token, title=title)

@app.route("/stream")
def stream():
    token = request.args.get("token", "")
    job = STREAM_JOBS.get(token)
    if not job:
        abort(404)
    title = job["title"]; text = job["text"]
    del STREAM_JOBS[token]  # consumir

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".mp3")
    os.close(tmp_fd)

    def generate():
        chunks = split_text(text)
        for chunk in chunks:
            tts = gTTS(chunk, lang="es")
            buf = io.BytesIO()
            tts.write_to_fp(buf)
            data = buf.getvalue()
            with open(tmp_path, "ab") as out:
                out.write(data)
            yield data

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        final_name = f"{stamp}_{slugify(title)}.mp3"
        final_path = os.path.join(ARCHIVE_DIR, final_name)
        shutil.move(tmp_path, final_path)

    return Response(generate(), mimetype="audio/mpeg")

@app.route("/audio/<path:filename>")
def audio(filename):
    return send_from_directory(ARCHIVE_DIR, filename, as_attachment=False)

@app.route("/api/delete", methods=["POST"])
def api_delete():
    fname = request.json.get("filename", "")
    path = os.path.join(ARCHIVE_DIR, fname)
    if os.path.isfile(path):
        os.remove(path); return jsonify(ok=True)
    return jsonify(ok=False), 404

if __name__ == "__main__":
    # Render usará gunicorn, pero esto permite correr localmente:
    app.run(host="0.0.0.0", port=8000, debug=False)

# 1) ARRIBA: cambia el tamaño de chunk a ~2800–3000 chars para menos viajes a gTTS
def split_text(text: str, max_chars: int = 2800):  # antes 1800
    import re
    text = re.sub(r"\s+", " ", text).strip()
    parts = []
    while text:
        if len(text) <= max_chars:
            parts.append(text); break
        cut = text.rfind(". ", 0, max_chars)
        if cut == -1: cut = text.rfind(" ", 0, max_chars)
        if cut == -1: cut = max_chars
        parts.append(text[:cut+1].strip())
        text = text[cut+1:].strip()
    return parts

# 2) NUEVO: endpoint que prepara el stream SIN recargar la página
@app.route("/api/prepare", methods=["POST"])
def api_prepare():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    text  = (data.get("text")  or "").strip()
    if not text:
        return {"ok": False, "error": "Texto vacío."}, 400

    import re
    words = len(re.findall(r"\b\w+\b", text))
    if words > MAX_WORDS:
        return {"ok": False, "error": f"Texto supera {MAX_WORDS} palabras ({words})."}, 400

    token = str(uuid.uuid4())
    if not title:
        title = text[:40] + ("…" if len(text) > 40 else "")
    STREAM_JOBS[token] = {"title": title, "text": text}
    return {"ok": True, "token": token, "title": title}

