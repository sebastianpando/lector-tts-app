import io
import os
import re
import time
import unicodedata
from pathlib import Path
from flask import (
    Flask, request, render_template, send_from_directory,
    send_file, jsonify, Response, abort
)
from gtts import gTTS

BASE_DIR = Path(__file__).resolve().parent
AUDIO_DIR = BASE_DIR / "audio"
AUDIO_DIR.mkdir(exist_ok=True)

app = Flask(
    __name__,
    static_url_path="/static",
    static_folder="static",
    template_folder="templates",
)

# Cache razonable para estáticos
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 3600


def slugify(value: str) -> str:
    value = str(value or "").strip()
    value = unicodedata.normalize("NFKC", value)
    value = re.sub(r"[^\w\s-]", "", value.lower())
    value = re.sub(r"[-\s]+", "-", value).strip("-_")
    return value or "audio"


def synth_gtts(text: str, lang: str) -> bytes:
    """Genera MP3 con gTTS y devuelve bytes."""
    t = gTTS(text=text, lang=(lang or "es"))
    buf = io.BytesIO()
    t.write_to_fp(buf)
    return buf.getvalue()


@app.route("/")
def index():
    """
    Render de la UI. Si viene ?text=... hacemos *fallback* sin JS:
    devolvemos directamente el MP3 para no dejar al usuario sin respuesta.
    """
    items = sorted((p.name for p in AUDIO_DIR.glob("*.mp3")), reverse=True)

    q_text = request.args.get("text")
    if q_text:
        lang = (request.args.get("lang") or "es").split("-")[0]
        try:
            mp3 = synth_gtts(q_text, lang)
        except Exception as e:
            # Si falla TTS, volvemos al index mostrando el error
            return render_template("index.html", items=items, error=str(e)), 500

        filename = f"{int(time.time())}-{slugify(q_text[:40])}.mp3"
        (AUDIO_DIR / filename).write_bytes(mp3)
        return send_file(
            io.BytesIO(mp3),
            mimetype="audio/mpeg",
            as_attachment=False,
            download_name=filename,
        )

    return render_template("index.html", items=items)


@app.post("/api/tts")
def api_tts():
    """
    Endpoint principal para el front. Devuelve AUDIO (audio/mpeg).
    Incluye Content-Length para permitir progreso en el cliente.
    También guarda el archivo en /audio y retorna X-Filename.
    """
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or request.form.get("text") or "").strip()
    lang = (data.get("lang") or request.form.get("lang") or "es").split("-")[0]

    if not text:
        return jsonify({"error": "El campo 'text' es obligatorio."}), 400

    try:
        mp3 = synth_gtts(text, lang)
    except Exception as e:
        return jsonify({"error": f"No se pudo sintetizar audio: {e}"}), 500

    filename = f"{int(time.time())}-{slugify(text[:40])}.mp3"
    (AUDIO_DIR / filename).write_bytes(mp3)

    return Response(
        mp3,
        mimetype="audio/mpeg",
        headers={
            "Content-Length": str(len(mp3)),
            "X-Filename": filename,
            # Desactivar caches agresivos intermedios
            "Cache-Control": "no-cache, no-store, must-revalidate",
        },
    )


@app.get("/api/archive")
def api_archive():
    items = sorted((p.name for p in AUDIO_DIR.glob("*.mp3")), reverse=True)
    return jsonify({"items": items})


@app.post("/api/delete")
def api_delete():
    payload = request.get_json(silent=True) or {}
    filename = payload.get("file") or request.form.get("file")
    if not filename:
        return jsonify({"ok": False, "error": "Parámetro 'file' requerido."}), 400

    # Sanitizar nombre
    if "/" in filename or "\\" in filename or ".." in filename:
        return jsonify({"ok": False, "error": "Nombre inválido."}), 400

    path = AUDIO_DIR / filename
    if not (path.exists() and path.is_file() and path.suffix.lower() == ".mp3"):
        return jsonify({"ok": False, "error": "Archivo no encontrado."}), 404

    try:
        path.unlink()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.get("/audio/<path:filename>")
def audio_file(filename: str):
    if "/" in filename or "\\" in filename or ".." in filename:
        abort(400)
    return send_from_directory(AUDIO_DIR, filename, mimetype="audio/mpeg", as_attachment=False)


if __name__ == "__main__":
    # Modo dev local
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
