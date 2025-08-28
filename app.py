import os
import io
import re
import uuid
import tempfile
import shutil
from datetime import datetime
from flask import (
    Flask, request, Response, render_template, abort,
    send_from_directory, jsonify
)
from gtts import gTTS
from pydub import AudioSegment

app = Flask(__name__)

ARCHIVE_DIR = os.path.join("static", "archive")
os.makedirs(ARCHIVE_DIR, exist_ok=True)

# Trabajo en memoria: token -> dict(title, text, lang, chunks, sent, done, first_chunk_done)
JOBS = {}
MAX_WORDS = 5000
SPEED_SUGGESTED = {"es": 1.20, "en": 1.00}


def slugify(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"[^a-z0-9\-]+", "", s)
    return s[:60] or "lectura"


def smart_split(text: str, first_max: int = 900, next_max: int = 3200):
    """
    Split 'fluido': primer chunk chico para arrancar rápido,
    luego chunks grandes para throughput.
    """
    def split_with_limit(t: str, max_chars: int):
        t = re.sub(r"\s+", " ", t).strip()
        parts = []
        while t:
            if len(t) <= max_chars:
                parts.append(t)
                break
            cut = -1
            for sep in [". ", "… ", "?! ", "!? ", "; ", ": ", ", "]:
                cut = t.rfind(sep, 0, max_chars)
                if cut != -1:
                    cut += len(sep)
                    break
            if cut == -1:
                cut = max_chars
            parts.append(t[:cut].strip())
            t = t[cut:].strip()
        return parts

    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []

    # Primer tramo
    if len(text) <= first_max:
        return [text]

    first = split_with_limit(text[:first_max], first_max)[0]
    rest = text[len(first):].strip()
    rest_parts = split_with_limit(rest, next_max)
    return [first] + rest_parts


@app.route("/", methods=["GET"])
def index():
    items = [f for f in os.listdir(ARCHIVE_DIR) if f.endswith(".mp3")]
    items.sort(reverse=True)
    return render_template("index.html", items=items)


@app.route("/api/prepare", methods=["POST"])
def api_prepare():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    lang = (data.get("lang") or "es").strip().lower()
    if not text:
        return {"ok": False, "error": "Texto vacío."}, 400

    words = len(re.findall(r"\b\w+\b", text))
    if words > MAX_WORDS:
        return {"ok": False, "error": f"Texto supera {MAX_WORDS} palabras ({words})."}, 400

    if lang not in ("es", "en"):
        lang = "es"

    token = str(uuid.uuid4())
    title = text[:40] + ("…" if len(text) > 40 else "")

    chunks = smart_split(text, first_max=900, next_max=3200)
    JOBS[token] = {
        "title": title,
        "text": text,
        "lang": lang,
        "chunks": chunks,
        "sent": 0,
        "done": False,
        "first_chunk_done": False
    }

    return {
        "ok": True,
        "token": token,
        "title": title,
        "lang": lang,
        "speed_suggested": SPEED_SUGGESTED.get(lang, 1.0),
        "total_chunks": len(chunks)
    }


@app.route("/api/progress")
def api_progress():
    token = request.args.get("token", "")
    job = JOBS.get(token)
    if not job:
        return jsonify(ok=False, error="token no encontrado"), 404
    total = max(1, len(job["chunks"]))
    sent = job["sent"]
    done = job["done"]
    return jsonify(ok=True, sent=sent, total=total, done=done)


@app.route("/stream")
def stream():
    token = request.args.get("token", "")
    job = JOBS.get(token)
    if not job:
        abort(404)

    title = job["title"]
    lang = job["lang"]
    chunks = job["chunks"]

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".mp3")
    os.close(tmp_fd)

    def generate():
        # 0) Preámbulo: 300ms de silencio para que el player arranque al tiro
        silence = AudioSegment.silent(duration=300)  # ms
        head = io.BytesIO()
        silence.export(head, format="mp3", bitrate="128k")
        data = head.getvalue()
        with open(tmp_path, "ab") as out:
            out.write(data)
        yield data

        # 1) Emitimos chunks TTS
        total = len(chunks)
        for i, chunk in enumerate(chunks, start=1):
            tts = gTTS(chunk, lang=lang)
            buf = io.BytesIO()
            tts.write_to_fp(buf)
            mp3_bytes = buf.getvalue()

            # Acumular para archivo final
            with open(tmp_path, "ab") as out:
                out.write(mp3_bytes)

            # Progreso
            job["sent"] = i
            job["first_chunk_done"] = True

            # Emitir al cliente
            yield mp3_bytes

        # 2) Archivar
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        final_name = f"{stamp}_{slugify(title)}.mp3"
        final_path = os.path.join(ARCHIVE_DIR, final_name)
        shutil.move(tmp_path, final_path)
        job["done"] = True

    resp = Response(generate(), mimetype="audio/mpeg", direct_passthrough=True)
    # Intento de evitar buffering por proxy intermedio
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Accel-Buffering"] = "no"
    return resp


@app.route("/audio/<path:filename>")
def audio(filename):
    return send_from_directory(ARCHIVE_DIR, filename, as_attachment=False)


@app.route("/api/delete", methods=["POST"])
def api_delete():
    fname = (request.json or {}).get("filename", "")
    path = os.path.join(ARCHIVE_DIR, fname)
    if os.path.isfile(path):
        os.remove(path)
        return jsonify(ok=True)
    return jsonify(ok=False), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
