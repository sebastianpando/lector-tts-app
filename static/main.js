const audio = document.getElementById('player');
const form = document.getElementById('tts-form');
const statusLabel = document.getElementById('status-label');
const formError = document.getElementById('form-error');

function setStatus(msg, muted=true){
  if (!statusLabel) return;
  statusLabel.textContent = msg;
  statusLabel.className = muted ? 'muted' : '';
}

// ---- Controles del player
document.getElementById('back30')?.addEventListener('click', () => {
  if (!audio?.duration) return;
  audio.currentTime = Math.max(0, audio.currentTime - 30);
});
document.getElementById('fwd30')?.addEventListener('click', () => {
  if (!audio?.duration) return;
  audio.currentTime = Math.min(audio.duration, audio.currentTime + 30);
});
document.getElementById('stop')?.addEventListener('click', () => {
  if (!audio) return;
  // “Detener” = pausa y vuelve al inicio; NO cambia el SRC ni archiva
  audio.pause();
  audio.currentTime = 0;
  setStatus('Detenido.', true);
});
document.getElementById('play')?.addEventListener('click', async () => {
  if (!audio?.src) return;
  await audio.play().catch(()=>{});
});
document.getElementById('pause')?.addEventListener('click', () => {
  audio?.pause();
});

// ---- Estados para “Buffereando!”
audio?.addEventListener('waiting', () => setStatus('Buffereando!', false));
audio?.addEventListener('stalled', () => setStatus('Buffereando!', false));
audio?.addEventListener('playing', () => setStatus('Reproduciendo…', true));
audio?.addEventListener('canplay', () => setStatus('Listo', true));
audio?.addEventListener('canplaythrough', () => setStatus('Listo', true));
audio?.addEventListener('pause', () => setStatus('Pausado.', true));
audio?.addEventListener('ended', () => setStatus('Finalizado. Archivado en “Leídos”.', true));

// Media Session (opcional)
function setMediaSession(title='Lectura') {
  if (!('mediaSession' in navigator) || !audio) return;
  navigator.mediaSession.metadata = new MediaMetadata({
    title, artist: 'Lector TTS', album: 'Lecturas'
  });
  navigator.mediaSession.setActionHandler('play', () => audio.play());
  navigator.mediaSession.setActionHandler('pause', () => audio.pause());
  navigator.mediaSession.setActionHandler('seekbackward', (e) => {
    const s = e.seekOffset || 10; audio.currentTime = Math.max(0, audio.currentTime - s);
  });
  navigator.mediaSession.setActionHandler('seekforward', (e) => {
    const s = e.seekOffset || 10; audio.currentTime = Math.min(audio.duration, audio.currentTime + s);
  });
  navigator.mediaSession.setActionHandler('stop', () => { audio.pause(); audio.currentTime = 0; });
}

// ---- Envío del formulario SIN recargar
form?.addEventListener('submit', async (e) => {
  e.preventDefault();
  formError.style.display = 'none';
  const title = document.getElementById('title')?.value || '';
  const text  = document.getElementById('text')?.value || '';

  if (!text.trim()) {
    formError.textContent = 'Texto vacío.';
    formError.style.display = 'block';
    return;
  }

  // prepara stream
  setStatus('Preparando…', false);
  try {
    const resp = await fetch('/api/prepare', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, text })
    });
    const data = await resp.json();
    if (!data.ok) {
      formError.textContent = data.error || 'Error preparando TTS.';
      formError.style.display = 'block';
      setStatus('Error', true);
      return;
    }
    const token = data.token;
    const safeTitle = data.title || 'Lectura';

    // no recargamos: apuntamos el <audio> directamente al stream
    audio.src = `/stream?token=${encodeURIComponent(token)}`;
    setMediaSession(safeTitle);
    // reproducir
    setStatus('Buffereando!', false);
    await audio.play().catch(()=>{});
  } catch (err) {
    formError.textContent = 'No se pudo iniciar el stream.';
    formError.style.display = 'block';
    setStatus('Error', true);
  }
});

// ---- Reproducir elementos del archivo (si mantienes la lista)
document.addEventListener('click', async (e) => {
  const btn = e.target.closest('button');
  if (!btn) return;

  if (btn.classList.contains('play')) {
    const file = btn.dataset.file;
    audio.src = `/audio/${file}`;
    setStatus('Buffereando!', false);
    await audio.play().catch(()=>{});
    setMediaSession(file);
  }
  if (btn.classList.contains('del')) {
    const file = btn.dataset.file;
    if (confirm(`¿Eliminar "${file}"?`)) {
      await fetch('/api/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: file })
      });
      location.reload();
    }
  }
});
