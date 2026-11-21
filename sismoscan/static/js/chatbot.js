/* Asistente flotante «Sisma» con historial de consultas (se guarda en el navegador, por usuario).
   Los textos se insertan con textContent (nunca innerHTML). */
(function () {
  "use strict";
  var fab = document.getElementById("cb-fab"), panel = document.getElementById("cb-panel"); if (!fab || !panel) return;
  var log = document.getElementById("cb-log"), form = document.getElementById("cb-form"), entrada = document.getElementById("cb-in"), enviarBtn = form.querySelector("button");
  var vChat = document.getElementById("cb-vista-chat"), vHist = document.getElementById("cb-vista-hist"), btnHist = document.getElementById("cb-hist-btn");
  var lista = document.getElementById("cb-lista"), vacio = document.getElementById("cb-vacio"), sug = document.getElementById("cb-sug");
  var csrf = (document.querySelector('meta[name="csrf-token"]') || {}).content || "";
  var KEY = "sisma:hilos:" + (panel.dataset.uid || "0"), MAX_HILOS = 30, MAX_MSG = 60;
  var hilos = cargar(), actual = null, ocupado = false;

  // ---- almacenamiento (puede fallar en modo privado: la app sigue funcionando sin historial)
  function cargar() { try { var v = JSON.parse(localStorage.getItem(KEY) || "[]"); return Array.isArray(v) ? v : []; } catch (e) { return []; } }
  function guardar() { try { localStorage.setItem(KEY, JSON.stringify(hilos.slice(0, MAX_HILOS))); } catch (e) { /* sin almacenamiento */ } }

  // ---- chat
  function bajar() { log.scrollTop = log.scrollHeight; }
  function burbuja(clase, texto) { var d = document.createElement("div"); d.className = "cb-m " + clase; d.textContent = texto; log.appendChild(d); bajar(); return d; }
  function escribiendo() {
    var d = document.createElement("div"); d.className = "cb-m cb-bot"; d.setAttribute("aria-label", "Sisma está escribiendo");
    for (var i = 0; i < 3; i++) { var p = document.createElement("span"); p.className = "cb-dot"; p.style.animationDelay = i * 0.15 + "s"; d.appendChild(p); }
    log.appendChild(d); bajar(); return d;
  }
  function pintar() {
    log.textContent = ""; burbuja("cb-bot", panel.dataset.bienvenida);
    var ms = actual ? actual.mensajes : [];
    ms.forEach(function (m) { burbuja(m.tipo === "alerta" ? "cb-alerta" : (m.rol === "user" ? "cb-user" : "cb-bot"), m.texto); });
    sug.hidden = ms.length > 0; bajar();
  }

  // ---- vistas
  function vista(h) {
    vHist.hidden = !h; vChat.hidden = h; btnHist.setAttribute("aria-pressed", h ? "true" : "false");
    if (h) pintarLista(); else setTimeout(function () { entrada.focus({ preventScroll: true }); }, 30);
  }
  function fecha(t) { try { return new Date(t).toLocaleString("es-CO", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }).replace(",", " ·"); } catch (e) { return ""; } }
  function pintarLista() {
    lista.textContent = ""; vacio.hidden = hilos.length > 0;
    hilos.forEach(function (h) {
      var li = document.createElement("li"); li.className = "cb-fila" + (actual && actual.id === h.id ? " cb-actual" : "");
      var it = document.createElement("button"); it.type = "button"; it.className = "cb-it"; it.setAttribute("aria-label", "Retomar: " + h.titulo);
      var t = document.createElement("b"); t.textContent = h.titulo; var f = document.createElement("span"); f.textContent = fecha(h.actualizado);
      it.appendChild(t); it.appendChild(f); it.addEventListener("click", function () { retomar(h.id); });
      var del = document.createElement("button"); del.type = "button"; del.className = "cb-del"; del.setAttribute("aria-label", "Eliminar: " + h.titulo); del.title = "Eliminar";
      var ico = document.getElementById("cb-ico-borrar"); if (ico) del.appendChild(ico.content.cloneNode(true));   // icono SVG del servidor
      del.addEventListener("click", function () { borrar(h.id); });
      li.appendChild(it); li.appendChild(del); lista.appendChild(li);
    });
  }
  function retomar(id) { actual = hilos.filter(function (h) { return h.id === id; })[0] || null; pintar(); vista(false); }
  function borrar(id) {
    hilos = hilos.filter(function (h) { return h.id !== id; }); guardar();
    if (actual && actual.id === id) { actual = null; pintar(); }
    pintarLista();
  }
  function nuevo() { actual = null; pintar(); vista(false); }

  // ---- abrir / cerrar
  function abrir(si) {
    panel.hidden = !si; fab.setAttribute("aria-expanded", si ? "true" : "false"); fab.setAttribute("aria-label", si ? "Cerrar el asistente" : "Abrir el asistente de IA"); fab.dataset.visto = "1";
    if (si) { if (!log.children.length) pintar(); vista(false); }
  }
  fab.addEventListener("click", function () { abrir(panel.hidden); });
  document.getElementById("cb-cerrar").addEventListener("click", function () { abrir(false); fab.focus(); });
  btnHist.addEventListener("click", function () { vista(vHist.hidden); });
  document.getElementById("cb-nuevo").addEventListener("click", nuevo);
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape" || panel.hidden) return;
    if (!vHist.hidden) vista(false); else { abrir(false); fab.focus(); }
  });

  // ---- envío (misma API del servidor)
  function enviar(texto) {
    texto = (texto || "").trim(); if (!texto || ocupado) return;
    ocupado = true; enviarBtn.disabled = true; entrada.value = ""; sug.hidden = true;
    if (!actual) { actual = { id: Date.now().toString(36), titulo: texto.length > 48 ? texto.slice(0, 47) + "…" : texto, creado: Date.now(), actualizado: Date.now(), mensajes: [] }; hilos.unshift(actual); }
    burbuja("cb-user", texto);
    var previo = actual.mensajes.slice(-8).map(function (m) { return { rol: m.rol, texto: m.texto }; });
    actual.mensajes.push({ rol: "user", texto: texto }); actual.actualizado = Date.now(); guardar();
    var esp = escribiendo(), ctl = new AbortController(), t = setTimeout(function () { ctl.abort(); }, 45000);
    fetch(panel.dataset.url, { method: "POST", credentials: "same-origin", signal: ctl.signal,
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf }, body: JSON.stringify({ mensaje: texto, historial: previo, analisis_id: panel.dataset.aid ? parseInt(panel.dataset.aid, 10) : undefined }) })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { if (!r.ok) throw new Error(j.error || "No se pudo enviar el mensaje."); return j; }); })
      .then(function (j) {
        esp.remove(); burbuja(j.emergencia ? "cb-alerta" : "cb-bot", j.respuesta);
        if (j.motivo) burbuja("cb-error", "La IA no respondió: " + j.motivo + " Usé el modo básico.");
        actual.mensajes.push({ rol: "assistant", texto: j.respuesta, tipo: j.emergencia ? "alerta" : "" });
        if (actual.mensajes.length > MAX_MSG) actual.mensajes = actual.mensajes.slice(-MAX_MSG);
        actual.actualizado = Date.now(); guardar();
        if (j.emergencia) { var d = document.getElementById("dlg-emergencia"); if (d && d.showModal && !d.open) d.showModal(); }
      })
      .catch(function (e) { esp.remove(); burbuja("cb-error", e.name === "AbortError" ? "La respuesta tardó demasiado. Inténtalo de nuevo." : (e.message === "Failed to fetch" ? "Sin conexión. Si hay peligro, llama al 123." : e.message)); })
      .finally(function () { clearTimeout(t); ocupado = false; enviarBtn.disabled = false; entrada.focus({ preventScroll: true }); });
  }
  form.addEventListener("submit", function (e) { e.preventDefault(); enviar(entrada.value); });
  Array.prototype.forEach.call(panel.querySelectorAll("[data-sug]"), function (b) { b.addEventListener("click", function () { enviar(b.textContent); }); });
})();
