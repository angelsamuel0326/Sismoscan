/* Interfaz común: tema, animación de barras/medidor, avisos, confirmaciones, filtros, pestañas, instalación PWA. */
(function () {
  "use strict";
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var reducido = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ---- Tema claro / oscuro
  $$("[data-theme-toggle]").forEach(function (b) {
    b.addEventListener("click", function () {
      var oscuro = document.documentElement.classList.toggle("dark");
      try { localStorage.setItem("ss-tema", oscuro ? "oscuro" : "claro"); } catch (e) {}
      var m = $('meta[name="theme-color"]'); if (m) m.content = oscuro ? "#020617" : "#0f172a";
    });
  });

  // ---- Barras y medidor: parten vacíos y se llenan al aparecer
  function animar() {
    $$("[data-w]").forEach(function (el) { requestAnimationFrame(function () { el.style.width = el.dataset.w + "%"; }); });
    $$("[data-gauge]").forEach(function (p) {
      var fin = p.getAttribute("stroke-dashoffset");
      if (reducido) return;
      p.style.transition = "none"; p.setAttribute("stroke-dashoffset", "282.74");
      requestAnimationFrame(function () { requestAnimationFrame(function () { p.style.transition = ""; p.setAttribute("stroke-dashoffset", fin); }); });
    });
  }
  animar();

  // ---- Avisos (toasts) que se cierran solos
  $$("[data-toast]").forEach(function (t) {
    setTimeout(function () { t.style.transition = "opacity .4s"; t.style.opacity = "0"; setTimeout(function () { t.remove(); }, 450); }, 6000);
  });

  // ---- Mostrar/ocultar contraseña
  $$("[data-toggle-pass]").forEach(function (b) {
    b.addEventListener("click", function () {
      var i = document.getElementById(b.dataset.togglePass); if (!i) return;
      var ver = i.type === "password"; i.type = ver ? "text" : "password";
      b.setAttribute("aria-pressed", ver ? "true" : "false");
    });
  });

  // ---- Confirmación antes de acciones destructivas
  $$("form[data-confirm]").forEach(function (f) {
    f.addEventListener("submit", function (e) { if (!window.confirm(f.dataset.confirm)) e.preventDefault(); });
  });

  // ---- Imprimir
  $$("[data-print]").forEach(function (b) { b.addEventListener("click", function () { window.print(); }); });

  // ---- Historial: semáforo + búsqueda + fechas + comparar
  var filtros = $$("[data-filter]");
  if (filtros.length) {
    var sem = "todos", q = $("#buscar"), d1 = $("#desde"), d2 = $("#hasta");
    var aplicar = function () {
      var n = 0, t = q ? q.value.trim().toLowerCase() : "";
      $$("li[data-sem]").forEach(function (li) {
        var ok = (sem === "todos" || li.dataset.sem === sem) && (!t || li.dataset.texto.indexOf(t) >= 0) &&
          (!d1 || !d1.value || li.dataset.dia >= d1.value) && (!d2 || !d2.value || li.dataset.dia <= d2.value);
        li.hidden = !ok; if (ok) n++;
      });
      var v = $("#sin-resultados"); if (v) v.hidden = n > 0;
    };
    filtros.forEach(function (b) {
      b.addEventListener("click", function () {
        filtros.forEach(function (x) { x.setAttribute("aria-pressed", x === b ? "true" : "false"); });
        sem = b.dataset.filter; aplicar();
      });
    });
    [q, d1, d2].forEach(function (el) { if (el) el.addEventListener("input", aplicar); });

    var marcas = $$("[data-comparar]"), barra = $("#barra-comparar"), enl = $("#comp-enlace"), txt = $("#comp-texto");
    marcas.forEach(function (m) {
      m.addEventListener("change", function () {
        var sel = marcas.filter(function (x) { return x.checked; });
        if (sel.length > 2) { m.checked = false; sel = sel.filter(function (x) { return x !== m; }); }
        barra.hidden = sel.length === 0;
        enl.hidden = sel.length !== 2;
        txt.textContent = sel.length === 2 ? "Listo para comparar." : "Marca un segundo análisis para compararlos.";
        if (sel.length === 2) enl.href = "/comparar?a=" + sel[0].value + "&b=" + sel[1].value;
      });
    });
  }

  // ---- Pestañas Foto / Detección
  $$("[data-tab]").forEach(function (t) {
    t.addEventListener("click", function () {
      $$("[data-tab]").forEach(function (x) { x.setAttribute("aria-selected", x === t ? "true" : "false"); });
      $$("[data-pane]").forEach(function (p) { p.hidden = p.dataset.pane !== t.dataset.tab; });
    });
  });

  // ---- Diálogos (emergencia) y copiar enlace
  $$("[data-open-dialog]").forEach(function (b) { b.addEventListener("click", function () { var d = document.getElementById(b.dataset.openDialog); if (d && d.showModal) d.showModal(); }); });
  $$("[data-close-dialog]").forEach(function (b) { b.addEventListener("click", function () { var d = b.closest("dialog"); if (d) d.close(); }); });
  $$("dialog").forEach(function (d) { d.addEventListener("click", function (e) { if (e.target === d) d.close(); }); });
  $$("[data-copy]").forEach(function (b) {
    b.addEventListener("click", function () {
      var el = document.getElementById(b.dataset.copy), t = el ? (el.value || el.textContent) : "";
      var ok = function () { var o = b.textContent; b.textContent = "¡Copiado!"; setTimeout(function () { b.textContent = o; }, 1800); };
      if (navigator.clipboard) navigator.clipboard.writeText(t).then(ok); else { el.select && el.select(); document.execCommand("copy"); ok(); }
    });
  });
  $$("[data-share]").forEach(function (b) {
    if (!navigator.share) { b.hidden = true; return; }
    b.addEventListener("click", function () { navigator.share({ title: "SismoScan", text: b.dataset.text, url: b.dataset.url }).catch(function () {}); });
  });

  // ---- PWA: registro del service worker y modal de instalación (beforeinstallprompt)
  var evento = null, botones = $$("[data-install]"), dlgI = document.getElementById("dlg-instalar");
  function ocultarInstalar() { botones.forEach(function (b) { b.hidden = true; }); }
  window.addEventListener("beforeinstallprompt", function (e) { e.preventDefault(); evento = e; botones.forEach(function (b) { b.hidden = false; }); });
  botones.forEach(function (b) {
    b.addEventListener("click", function () { if (!evento) return; if (dlgI && dlgI.showModal) dlgI.showModal(); else evento.prompt(); });
  });
  if (dlgI) {
    var okI = document.getElementById("ins-ok");
    okI.addEventListener("click", function () {
      dlgI.close();
      if (!evento) return;
      evento.prompt();
      evento.userChoice.then(function (r) { if (r && r.outcome === "accepted") ocultarInstalar(); }).finally(function () { evento = null; });
    });
    Array.prototype.forEach.call(dlgI.querySelectorAll("[data-ins-cerrar]"), function (b) { b.addEventListener("click", function () { dlgI.close(); }); });
    dlgI.addEventListener("click", function (e) { if (e.target === dlgI) dlgI.close(); });
  }
  window.addEventListener("appinstalled", ocultarInstalar);
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", function () { navigator.serviceWorker.register("/service-worker.js", { scope: "/" }).catch(function () {}); });
  }

  // ---- Opciones seleccionables (chips y segmentos): resaltado con la clase is-checked, sin depender de :has() ----
  function marcarOpciones() {
    $$(".chip, .seg").forEach(function (l) { var i = l.querySelector("input"); if (i) l.classList.toggle("is-checked", i.checked); });
  }
  document.addEventListener("change", function (e) { if (e.target && e.target.matches && e.target.matches(".chip input, .seg input")) marcarOpciones(); });
  window.marcarOpciones = marcarOpciones; marcarOpciones();
})();
