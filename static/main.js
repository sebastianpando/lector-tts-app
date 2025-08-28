(() => {
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  const form = $("#tts-form");
  const textarea = $("#text");
  const langSel = $("#lang");
  const errBox = $("#form-error");

  const spinner = $("#spinner");
  const statusLabel = $("#status-label");
  const progressWrap = $("#progress-wrap");
  const progressBar = $("#progress-bar");

  const player = $("#player");
  const btnPlay = $("#play");
  const btnPause = $("#pause");
  const btnStop = $("#stop");
  const speedBtns = $$(".speed-btn");
  const speedCurrent = $("#speed-current");

  const archiveList = $("#archive-list");
  const noArchive = $("#no-archive");

  let lastObjectUrl = null;
  let fakeProgressTimer = null;

  function setStatus(text) {
    statusLabel.textContent = text;
  }

  function showSpinner(show) {
    spinner.style.display = show ? "inline-block" : "none";
  }

  function resetProgress() {
    progressBar.style.width = "0%";
  }

  function showProgress(show) {
    progressWrap.style.display = show ? "block" : "none";
  }

  function startFakeProgress() {
    // Progreso “indefinido” si no hay Content-Length
    let w = 0;
    clearInterval(fakeProgressTimer);
    fakeProgressTimer = setInterval(() => {
      w = Math.min(90, w + Math.random() * 5 + 1);
      progressBar.style.width = w.toFixed(0) + "%";
    }, 120);
  }

  function stopFakeProgress() {
    clearInterval(fakeProgressTimer);
    fakeProgressTimer = null;
  }

  function clearError() {
    errBox.style.display = "none";
    errBox.textContent = "";
  }

  function showError(msg) {
    errBox.textContent = "⚠️ " + msg;
    errBox.style.display = "block";
  }

  function revokeLastUrl() {
    if (lastObjectUrl) {
      URL.revokeObjectURL(lastObjectUrl);
      lastObjectUrl = null;
    }
  }

  function setPlaybackRate(rate) {
    player.playbackRate = rate;
    speedBtns.forEach(b => b.classList.toggle("active", b.dataset.rate === String(rate)));
    speedCurrent.textContent = `(${rate.toFixed(1)}×)`;
  }

  function addArchiveItem(filename) {
    if (!filename) return;
    if (noArchive && noArchive.style.display !== "none") {
      noArchive.style.display = "none";
      archiveList.style.display = "";
    }
    const li = document.createElement("li");
    li.innerHTML = `
      <button class="play" data-file="${filename}">▶</button>
      <a href="/audio/${filename}">${filename}</a>
      <button class="del" data-file="${filename}">🗑</button>
    `;
    // Insertar arriba (más reciente primero)
    if (archiveList.firstChild) archiveList.prepend(li);
    else archiveList.appendChild(li);
  }

  async function fetchAndPlay(text, lang) {
    clearError();
    setStatus("Generando audio…");
    showSpinner(true);
    showProgress(true);
    resetProgress();

    let body = JSON.stringify({ text, lang });

    let res;
    try {
      res = await fetch("/api/tts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
      });
    } catch (e) {
      showSpinner(false);
      showProgress(false);
      return showError("No se pudo conectar con el servidor.");
    }

    if (!res.ok) {
      // intentar extraer JSON de error
      let msg = "Error al generar audio.";
      try {
        const j = await res.json();
        if (j && j.error) msg = j.error;
      } catch {}
      showSpinner(false);
      showProgress(false);
      return showError(msg);
    }

    const total = parseInt(res.headers.get("Content-Length") || "0", 10);
    const filename = res.headers.get("X-Filename") || "";

    const reader = res.body.getReader();
    const chunks = [];
    let received = 0;

    if (!total) startFakeProgress();

    try {
      // Leer flujo y actualizar progreso
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        chunks.push(value);
        received += value.length;
        if (total) {
          const pct = Math.max(1, Math.min(100, Math.floor((received / total) * 100)));
          progressBar.style.width = pct + "%";
        }
      }
    } catch (e) {
      stopFakeProgress();
      showSpinner(false);
      setStatus("Error en la descarga.");
      return showError("Se interrumpió la descarga del audio.");
    }

    stopFakeProgress();
    progressBar.style.width = "100%";
    setStatus("Listo ✓");
    showSpinner(false);

    const blob = new Blob(chunks, { type: "audio/mpeg" });
    revokeLastUrl();
    const url = URL.createObjectURL(blob);
    lastObjectUrl = url;
    player.src = url;

    // Auto-ajustar velocidad por idioma si quieres (ej.: ES un poco más rápido)
    if ((lang || "").startsWith("es")) {
      setPlaybackRate(1.2);
    } else {
      setPlaybackRate(1.0);
    }

    try {
      await player.play();
    } catch {
      // El usuario quizás requiere interacción previa
    }

    // Añadir al archivo local (UI)
    if (filename) addArchiveItem(filename);

    // Ocultar barra tras un momento
    setTimeout(() => showProgress(false), 600);
  }

  // Eventos UI
  form?.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = (textarea.value || "").trim();
    const lang = langSel.value || "es";
    if (!text) {
      return showError("Por favor, pega algún texto.");
    }
    fetchAndPlay(text, lang);
  });

  btnPlay?.addEventListener("click", () => {
    player.play().catch(() => {});
  });
  btnPause?.addEventListener("click", () => player.pause());
  btnStop?.addEventListener("click", () => {
    player.pause();
    player.currentTime = 0;
  });

  speedBtns.forEach((b) => {
    b.addEventListener("click", () => {
      const rate = parseFloat(b.dataset.rate || "1");
      setPlaybackRate(rate);
    });
  });

  // Delegación para botones de archivo (play/delete)
  archiveList?.addEventListener("click", async (e) => {
    const target = e.target.closest("button");
    if (!target) return;

    const file = target.getAttribute("data-file");
    if (!file) return;

    if (target.classList.contains("play")) {
      revokeLastUrl();
      player.src = `/audio/${encodeURIComponent(file)}`;
      player.play().catch(() => {});
    } else if (target.classList.contains("del")) {
      if (!confirm("¿Eliminar este audio?")) return;
      try {
        const res = await fetch("/api/delete", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ file }),
        });
        const j = await res.json();
        if (!j.ok) throw new Error(j.error || "No se pudo eliminar.");
        // quitar del DOM
        target.closest("li")?.remove();
        if (!archiveList.querySelector("li")) {
          if (noArchive) {
            noArchive.style.display = "";
            archiveList.style.display = "none";
          }
        }
      } catch (err) {
        showError(err.message || "No se pudo eliminar el archivo.");
      }
    }
  });

  // Estado inicial
  setPlaybackRate(1.0);
  clearError();
  setStatus("Listo");
})();
