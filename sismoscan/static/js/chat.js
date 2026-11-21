/* Chat post-análisis. Los textos se insertan con textContent (nunca innerHTML) para evitar XSS. */
(function () {
  "use strict";
  var caja = document.getElementById("chat"); if (!caja) return;
  var log = document.getElementById("chat-log"), form = document.getElementById("chat-form"), entrada = document.getElementById("chat-in");
  var csrf = (document.querySelector('meta[name="csrf-token"]') || {}).content || "";
  var CLS = {
    user: "rs-b rs-b-user",
    bot: "rs-b rs-b-bot",
    alerta: "rs-b rs-b-alerta",
    error: "rs-b rs-b-error"
  };
  var ocupado = false;

  function bajar() { log.scrollTop = log.scrollHeight; }
  function burbuja(tipo, texto) { var d = document.createElement("div"); d.className = CLS[tipo]; d.textContent = texto; log.appendChild(d); bajar(); return d; }
  function escribiendo() {
    var d = document.createElement("div"); d.className = CLS.bot; d.setAttribute("aria-label", "El asistente está escribiendo");
    for (var i = 0; i < 3; i++) { var p = document.createElement("span"); p.className = "rs-dot"; p.style.animationDelay = i * 0.2 + "s"; d.appendChild(p); }
    log.appendChild(d); bajar(); return d;
  }

  function enviar(texto) {
    texto = (texto || "").trim(); if (!texto || ocupado) return;
    ocupado = true; entrada.value = ""; burbuja("user", texto); var esp = escribiendo();
    var ctl = new AbortController(), t = setTimeout(function () { ctl.abort(); }, 45000);
    fetch(caja.dataset.url, { method: "POST", credentials: "same-origin", signal: ctl.signal,
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf }, body: JSON.stringify({ mensaje: texto }) })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { if (!r.ok) throw new Error(j.error || "No se pudo enviar el mensaje."); return j; }); })
      .then(function (j) {
        esp.remove(); burbuja(j.emergencia ? "alerta" : "bot", j.respuesta);
        if (j.emergencia) { var d = document.getElementById("dlg-emergencia"); if (d && d.showModal && !d.open) d.showModal(); }
      })
      .catch(function (e) { esp.remove(); burbuja("error", e.name === "AbortError" ? "La respuesta tardó demasiado. Inténtalo de nuevo." : (e.message === "Failed to fetch" ? "Sin conexión. Si hay peligro, llama al 123." : e.message)); })
      .finally(function () { clearTimeout(t); ocupado = false; entrada.focus({ preventScroll: true }); });
  }

  form.addEventListener("submit", function (e) { e.preventDefault(); enviar(entrada.value); });
  Array.prototype.forEach.call(document.querySelectorAll("[data-sug]"), function (b) { b.addEventListener("click", function () { enviar(b.textContent); }); });
  bajar();
})();
