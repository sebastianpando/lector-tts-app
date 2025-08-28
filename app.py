from flask import Flask, request, render_template, make_response, abort
from io import BytesIO
from gtts import gTTS

# Configuración correcta de rutas de estáticos y plantillas
app = Flask(
    __name__,
    static_url_path="/static",
    static_folder="static",
    template_folder="templates"
)

@app.after_request
def add_secure_headers(resp):
    # Un par de cabeceras útiles
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp

def sanitize_text(s: str) -> str:
    s = (s or "").strip()
    # Recorta a 5000 chars para evitar abusos/errores
    return s[:5000]

@app.route("/", methods=["GET"])
def index():
    text = request.args.get("text", "")
    lang = request.args.get("lang", "es")
    return render_template("index.html", text=text, lang=lang)

@app.route("/tts", methods=["GET"])
def tts():
    text = sanitize_text(request.args.get("text", ""))
    lang = (request.args.get("lang", "es") or "es").strip()

    if not text:
        abort(400, description="Parámetro 'text' requerido")

    try:
        # gTTS genera un MP3 en memoria
        tts_obj = gTTS(text=text, lang=lang)
        buf = BytesIO()
        tts_obj.write_to_fp(buf)
        buf.seek(0)

        audio_bytes = buf.read()
        resp = make_response(audio_bytes)
        resp.headers["Content-Type"] = "audio/mpeg"
        # Evita cachear audios por defecto (opcional)
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        return resp
    except Exception as e:
        abort(500, description=f"Error generando TTS: {e}")

# Punto de entrada local (Render usará gunicorn vía Procfile)
if __name__ == "__main__":
    # Para pruebas locales:
    #   pip install -r requirements.txt
    #   python app.py
    app.run(host="0.0.0.0", port=5000, debug=True)
