const audio = document.getElementById('player');

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
  audio.pause(); audio.currentTime = 0;
});

// lista: reproducir / borrar
document.addEventListener('click', async (e) => {
  const btn = e.target.closest('button');
  if (!btn) return;

  if (btn.classList.contains('play')) {
    const file = btn.dataset.file;
    audio.src = `/audio/${file}`;
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

// Media Session (controles con pantalla bloqueada / auriculares)
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

audio?.addEventListener('loadedmetadata', () => {
  const label = audio.src.split('/').pop() || 'Lectura';
  setMediaSession(decodeURIComponent(label));
});
