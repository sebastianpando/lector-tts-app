const audio = document.getElementById('player');
const form = document.getElementById('tts-form');
const statusLabel = document.getElementById('status-label');
const formError = document.getElementById('form-error');
const spinner = document.getElementById('spinner');
const progressWrap = document.getElementById('progress-wrap');
const progressBar = document.getElementById('progress-bar');

const speedBtns = Array.from(document.querySelectorAll('.speed-btn'));
const speedCurrent = document.getElementById('speed-current');

const SPEED_KEY = 'pando.playbackRate';
let currentToken = null;
let progressTimer = null;

function setStatus(msg, muted = true) {
  if (!statusLabel) return;
  statusLabel.textContent = msg;
  statusLabel.className = muted ? 'muted' : '';
}
function setSpinner(on) { if (spinner) spinner.style.display = on ? 'inline-block' : 'none'; }
function setProgress(percent) {
  if (!progressWrap || !progressBar) return;
  progressWrap.style.display = percent >= 0 && percent < 100 ? 'block' : 'none';
  progressBar.style.width = `${Math.max(0, Math.min(100, percent))}%`;
}
function setActiveSpeed(rate) {
  speedBtns.forEach(b => b.classList.toggle('active', Number(b.dataset.rate) === Number(rate)));
  if (speedCurrent) speedCurrent.textContent = `(${Number(rate).toFixed(1)}×)`;
}

function initSpeed() {
  const saved = Number(localStorage.getItem(SPEED_KEY) || 'NaN');
  if (audio && isFinite(saved) && saved > 0) {
    audio.playbackRate = saved;
    setActiveSpeed(saved);
  } else {
    setActiveSpeed(1.0);
  }
}
initSpeed();

speedBtns.forEach(btn => {
  btn.addEventListener('click', () => {
    const rate = Number(btn.dataset.rate);
    if (!audio || !isFinite(rate) || rate <= 0) return;
    audio.playbackRate = rate;
    localStorage.setItem(SPEED_KEY, String(rate));
    setActiveSpeed(rate);
  });
});

// Controles
document.getElementById('play')?.addEventListener('click', async () => {
  if (!audio?.src) return;
  await audio.play().catch(() => {});
  setStatus('Reproduciendo…', true);
});
document.getElementById('pause')?.addEventListener('click', () => {
  if (!audio) return;
  audio.pause();
  setStatus('Pausado.', true);
});
document.getElementById('stop')?.addEventListener('click', () => {
  if (!audio) return;
  audio.pause();
  audio.currentTime = 0;
  setStatus('Detenido.', true);
});

// Estados nativos
audio?.addEventListener('waiting', () => { setStatus('Buffereando…', false); setSpinner(true); });
audio?.addEventListener('stalled', () => { setStatus('Buffereando…', false); setSpinner(true); });
audio?.addEventListener
