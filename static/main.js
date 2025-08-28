(() => {
  const form = document.getElementById("tts-form");
  const textEl = document.getElementById("text");
  const langEl = document.getElementById("lang");
  const errorEl = document.getElementById("form-error");

  const spinner = document.getElementById("spinner");
  const statusLabel = document.getElementById("status-label");
  const progressWrap = document.getElementById("progress-wrap");
  const progressBar = document.getElementById("progress-bar");

  const audioTag = document.getElementById("player");
  const playBtn = document.getElementById("play");
  const pauseBtn = document.getElementById("pause");
  const stopBtn = document.getElementById("stop");
  const speedBtns = document.querySelectorAll(".speed-btn");
  const speedCurrent = document.getElementById("speed-current");

  // --- Estado de reproducción segmentada ---
  let AC = null;                 // AudioContext
  let masterGain = null;         // GainNode para controlar volumen / rate emulado si quisieras
  let queue = [];                // [{buffer: AudioBuffer, duration: number}, ...]
  let isPlaying = false;
  let startTime = 0;             // AC.currentTime cuando comienza la cola actual
  let scheduledTime = 0;         // segundos ya planificados en la cola
  let fetchController = null;    // abort para peticiones en curso
  let sessionId = null;          // id de la sesión /api/manifest
  let chunkCount = 0;            // cantidad de segmentos
  let playedSeconds = 0;         // progreso simple

  // iOS requiere activar el AudioContext tras un gesto del usuario
  function ensureAudioContext() {
    if (!AC) {
      AC = new (window.AudioContext || window.webkitAudioContext)();
      masterGain = AC.createGain();
      masterGain.connect(AC.destination);
    }
    if (AC.state === "suspended") {
      return AC.resume();
    }
    return Promise.resolve();
  }

  function uiLoading(on) {
    spinner.style.display = on ? "inline-block" : "none";
    statusLabel.textContent = on ? "Buffering…" : "Listo";
    progressWrap.style.display = on ? "block" : "none";
  }

  function setProgress(percent) {
    progressBar.style.width = `${Math.max(0, Math.min(100, percent))}%`;
  }

  // Limpia la cola y cancela descargas
  function resetPlayback(hard = false) {
    if (fetchController) {
      fetchController.abort();
      fetchController = null;
    }
    queue = [];
    scheduledTime = 0;
    startTime = 0;
    isPlaying = false;
    playedSeconds = 0;
    setProgress(0);
    if (hard && AC) {
      // cierra contexto si quieres liberar
      // AC.close(); AC = null; masterGain = null;
    }
  }

  // Programa un AudioBuffer para que suene en AC
  function scheduleBuffer(buffer) {
    const src = AC.createBufferSource();
    src.buffer = buffer;
    src.connect(masterGain);
    const when = (startTime || AC.currentTime) + scheduledTime;
    src.start(when);
    scheduledTime += buffer.duration;
    // Al terminar el último buffer planificado, si no hay más, marcamos fin
    src.onended = () => {
      // onended se dispara por cada buffer. Solo cuando todo lo planificado pasó:
      const elapsed = AC.currentTime - (startTime || AC.currentTime);
      if (elapsed >= (scheduledTime - 0.05)) {
        isPlaying = false;
        uiLoading(false);
        statusLabel.textContent = "Finalizado";
      }
    };
  }

  // Descarga + decodifica un chunk y lo añade a la cola
  async function fetchAndQueueChunk(idx) {
    const url = `/api/chunk/${sessionId}/${idx}`;
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) throw new Error(`Chunk ${idx} HTTP ${res.status}`);
    const ab = await res.arrayBuffer();
    const buffer = await AC.decodeAudioData(ab);
    queue.push({ buffer, duration: buffer.duration });
    scheduleBuffer(buffer);
    // Progreso aproximado: chunks descargados / total
    const pct = Math.round(((idx + 1) / chunkCount) * 100);
    setProgress(pct);
  }

  async function startStreamingPlayback(text, lang) {
    resetPlayback();

    await ensureAudioContext();

    // 1) Pide el manifiesto (divide texto en el servidor)
    fetchController = new AbortController();
    const res = await fetch("/api/manifest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, lang }),
      signal: fetchController.signal
    });
    if (!res.ok) {
      const msg = await res.text();
      throw new Error(`Manifiesto: ${msg || res.status}`);
    }
    const manifest = await res.json();
    sessionId = manifest.session;
    chunkCount = manifest.count;

    // 2) Descarga el primer chunk, lo reproduce ASAP
    uiLoading(true);
    statusLabel.textContent = "Preparando primer segmento…";
    await fetchAndQueueChunk(0);

    // Primer audio ya planificado, arranca el reloj
    startTime = AC.currentTime;
    isPlaying = true;
    uiLoading(true);
    statusLabel.textContent = "Reproduciendo…";

    // 3) Descarga del resto en segundo plano
    for (let i = 1; i < chunkCount; i++) {
      if (!fetchController) break;
      await fetchAndQueueChunk(i);
    }

    // 4) Export opcional (archivo completo) — cuando todo estuvo OK
    try {
      await fetch("/api/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, lang })
      });
    } catch (_) { /* silencioso */ }

    uiLoading(false);
  }

  // --- Eventos UI ---

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    errorEl.style.display = "none";
    const text = (textEl.value || "").trim();
    const lang = langEl.value || "es";
    if (!text) {
      errorEl.textContent = "Por favor pega algún texto.";
      errorEl.style.display = "block";
      return;
    }

    try {
      await ensureAudioContext(); // gesto del usuario
      await startStreamingPlayback(text, lang);
    } catch (err) {
      console.error(err);
      errorEl.textContent = "No se pudo iniciar la reproducción (iOS/Safari pueden requerir un toque adicional).";
      errorEl.style.display = "block";
      uiLoading(false);
    }
  });

  playBtn.addEventListener("click", async () => {
    await ensureAudioContext();
    if (AC && AC.state === "suspended") await AC.resume();
    // No “reiniciamos” la cola; si ya hay buffers programados, continuará.
    isPlaying = true;
    statusLabel.textContent = "Reproduciendo…";
  });

  pauseBtn.addEventListener("click", async () => {
    if (AC && AC.state === "running") {
      await AC.suspend();
      statusLabel.textContent = "Pausado";
    }
  });

  stopBtn.addEventListener("click", async () => {
    resetPlayback();
    if (AC && AC.state !== "closed") {
      try { await AC.close(); } catch(_) {}
    }
    AC = null; masterGain = null;
    statusLabel.textContent = "Detenido";
    uiLoading(false);
  });

  // Velocidad (nota: con WebAudio nativo no hay playbackRate global para varios buffers ya programados;
  // si necesitas rate real, deberías ajustar start/stop y recrear scheduling. Aquí mantenemos el UI.)
  speedBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      speedBtns.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      const rate = parseFloat(btn.dataset.rate);
      speedCurrent.textContent = `(${rate.toFixed(1)}×)`;
      // Dejamos el rate como visual; para una implementación completa,
      // podrías usar playbackRate en cada BufferSource *antes* de start().
    });
  });

  // Reproducir un archivo del archivo (los 3 últimos)
  document.querySelectorAll(".archive .play").forEach(b => {
    b.addEventListener("click", async () => {
      const file = b.getAttribute("data-file");
      if (!file) return;
      // En iOS: usar la etiqueta <audio> con src directo para archivos ya completos
      resetPlayback(true);
      audioTag.src = `/audio/${file}`;
      audioTag.currentTime = 0;
      try {
        await audioTag.play();
        statusLabel.textContent = "Reproduciendo archivo…";
      } catch (err) {
        console.error(err);
        statusLabel.textContent = "No se pudo reproducir el archivo.";
      }
    });
  });
})();
