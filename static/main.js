(() => {
  const form = document.getElementById("tts-form");
  const textEl = document.getElementById("text");
  const langEl = document.getElementById("lang");
  const player = document.getElementById("player");
  const playerSection = document.getElementById("player-section");
  const statusEl = document.getElementById("status");
  const btn = document.getElementById("btn-generate");

  const setStatus = (msg) => {
    statusEl.textContent = msg || "";
  };

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const txt = (textEl.value || "").trim();
    const lang = (langEl.value || "es").trim();

    if (!txt) {
      alert("Escribe algún texto primero.");
      return;
    }
    btn.disabled = true;
    setStatus("Generando audio...");

    try {
      // Añadimos un cache-buster para evitar 304 con audio viejo
      const url = `/tts?text=${encodeURIComponent(txt)}&lang=${encodeURIComponent(lang)}&t=${Date.now()}`;
      const res = await fetch(url, { cache: "no-store" });

      if (!res.ok) {
        const reason = await res.text();
        throw new Error(`HTTP ${res.status} - ${reason}`);
      }

      const blob = await res.blob();
      if (blob.size === 0) {
        throw new Error("El audio retornó 0 bytes.");
      }

      const objectURL = URL.createObjectURL(blob);
      player.src = objectURL;
      playerSection.classList.remove("hidden");
      player.play().catch(() => {/* Autoplay puede fallar por permisos */});
      setStatus("Listo ✅");
    } catch (err) {
      console.error(err);
      setStatus(`Error: ${err.message}`);
      alert(`No se pudo generar el audio:\n${err.message}`);
    } finally {
      btn.disabled = false;
    }
  });
})();
