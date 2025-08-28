// main.js
(() => {
  const form = document.getElementById('tts-form');
  const txt = document.getElementById('text');
  const langSel = document.getElementById('lang');
  const player = document.getElementById('player');
  const spinner = document.getElementById('spinner');
  const statusLabel = document.getElementById('status-label');
  const formError = document.getElementById('form-error');
  const submitBtn = document.getElementById('submit-btn');

  const btnPlay = document.getElementById('play');
  const btnPause = document.getElementById('pause');
  const btnStop = document.getElementById('stop');

  const speedButtons = Array.from(document.querySelectorAll('.speed-btn'));
  const speedCurrent = document.getElementById('speed-current');

  let currentSrcIsStreaming = false;
  let lockedSrc = null; // Para no “resetear” el audio en mitad de la reproducción

  function setStatus(msg, spinning = false) {
    statusLabel.textContent = msg;
    spinner.style.display = spinning ? 'inline-block' : 'none';
  }

  function showError(msg) {
    formError.textContent = msg;
    formError.style.display = 'block';
  }
  function clearError() {
    formError.textContent = '';
    formError.style.display = 'none';
  }

  function lockAndPlay(src) {
    // Evitar reinicios: seteamos src UNA sola vez por ciclo
    if (lockedSrc === src) return;
    lockedSrc = src;
    player.src = src;
    currentSrcIsStreaming = src.startsWith('/stream/');
    player.play().catch(() => {});
  }

  // ---- Form submit: cache text y apuntar <audio> al stream
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    clearError();

    const text = (txt.value || '').trim();
    const lang = langSel.value || 'es';
    if (!text) {
      showError('Por favor, pega algún texto.');
      return;
    }

    setStatus('Preparando stream…', true);
    submitBtn.disabled = true;

    try {
      const res = await fetch('/api/cache-text', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ text, lang })
      });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        throw new Error(data.error || 'Error preparando el streaming.');
      }

      const token = data.token;
      const streamUrl = `/stream/${token}`;

      // Importante: seteamos src una SOLA vez y reproducimos (stream empieza al tiro)
      lockAndPlay(streamUrl);
      setStatus('Cargando audio…', true);

    } catch (err) {
      console.error(err);
      showError(err.message || 'Error inesperado.');
      setStatus('Listo', false);
    } finally {
      submitBtn.disabled = false;
    }
  });

  // ---- Controles de player
  btnPlay.addEventListener('click', () => {
    player.play().catch(() => {});
  });
  btnPause.addEventListener('click', () => {
    player.pause();
  });
  btnStop.addEventListener('click', () => {
    player.pause();
    player.currentTime = 0;
  });

  // ---- Velocidad
  function setRate(rate) {
    player.playbackRate = rate;
    speedCurrent.textContent = `(${rate.toFixed(1)}×)`;
    speedButtons.forEach(b => b.classList.toggle('active', b.dataset.rate === String(rate)));
  }
  speedButtons.forEach(b => {
    b.addEventListener('click', () => setRate(parseFloat(b.dataset.rate)));
  });
  setRate(1.0);

  // ---- Eventos del audio para estados suaves
  player.addEventListener('waiting', () => {
    setStatus('Buffering…', true);
  });
  player.addEventListener('canplay', () => {
    setStatus('Reproduciendo…', false);
  });
  player.addEventListener('play', () => {
    setStatus('Reproduciendo…', false);
  });
  player.addEventListener('ended', () => {
    setStatus('Listo', false);
    // Cuando era streaming, al terminar ya existe el archivo final en /audio,
    // pero no recargamos la página para no interrumpir.
    currentSrcIsStreaming = false;
    lockedSrc = null;
  });
  player.addEventListener('error', () => {
    setStatus('Error de reproducción', false);
  });

  // ---- Archivo: play / delete
  document.querySelectorAll('.archive .play').forEach(btn => {
    btn.addEventListener('click', () => {
      const fname = btn.dataset.file;
      if (!fname) return;
      clearError();
      const url = `/audio/${encodeURIComponent(fname)}`;
      lockAndPlay(url); // archivo completo local, no streaming
    });
  });
  document.querySelectorAll('.archive .del').forEach(btn => {
    btn.addEventListener('click', async () => {
      const fname = btn.dataset.file;
      if (!fname) return;
      if (!confirm('¿Eliminar este archivo?')) return;
      try {
        const res = await fetch('/api/delete', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ file: fname })
        });
        const data = await res.json();
        if (!data.ok) throw new Error(data.error || 'No se pudo eliminar');
        // Quitar de la UI sin recargar
        btn.closest('li')?.remove();
      } catch (err) {
        showError(err.message || 'Error eliminando archivo');
      }
    });
  });
})();
