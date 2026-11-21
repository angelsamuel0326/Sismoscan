/* Asistente de análisis: contexto → foto → medidas (canvas) → envío.
 * La foto se reduce en el navegador (≤1600 px) antes de subirla; las coordenadas del trazo son normalizadas (0-1)
 * respecto a la imagen enviada, de modo que no dependen del zoom ni del tamaño en pantalla. */
(function () {
  "use strict";
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var MAX = 1600, ETQ = { horizontal: "Horizontal (eje X)", vertical: "Vertical (eje Y)", diagonal: "Diagonal" };

  var paso = 1, blob = null, bmp = null;
  var ref = [], fase = "ref", zoom = 1;

  var form = $("#form"), lienzo = $("#lienzo"), ctx = lienzo.getContext("2d");
  var csrf = ($('meta[name="csrf-token"]') || {}).content || "";

  // ---------- guía visual de medición (modal del paso 2)
  var guiaVista = false, guiaPrev = null;
  function guia(abrir) {
    var g = $("#guia"); if (!g) return;
    if (abrir) { guiaPrev = document.activeElement; g.hidden = false; document.body.style.overflow = "hidden"; requestAnimationFrame(function () { g.classList.add("is-open"); $("#guia-ok").focus(); }); }
    else { g.classList.remove("is-open"); document.body.style.overflow = ""; setTimeout(function () { g.hidden = true; }, 200); if (guiaPrev && guiaPrev.focus) guiaPrev.focus(); }
  }
  (function () {
    var img = $("#guia-img");
    function ok() { if (img.naturalWidth) { img.hidden = false; var s = document.querySelector(".an-guia-svg"); if (s) s.hidden = true; } }
    if (img) { img.addEventListener("load", ok); if (img.complete) ok(); }
    $("#guia-ok").addEventListener("click", function () { guia(false); });
    $("#guia-abrir").addEventListener("click", function () { guia(true); });
    $("#guia").addEventListener("click", function (e) { if (e.target === this) guia(false); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !$("#guia").hidden) guia(false); });
  })();

  // ---------- modal «¿qué objeto es?» al marcar los dos extremos de la referencia
  var rfm = $("#dlg-ref"), rfmV = "";
  function rfmPintar() {
    $$(".rfm-op", rfm).forEach(function (b) { b.setAttribute("aria-pressed", b.dataset.v === rfmV ? "true" : "false"); });
    $("#rfm-otro").hidden = rfmV !== "otro";
    var cm = parseFloat(($("#rfm-cm").value || "").replace(",", "."));
    $("#rfm-ok").disabled = !rfmV || (rfmV === "otro" && !(cm >= 0.5 && cm <= 500));
  }
  function preguntarRef() {
    if (!rfm || !rfm.showModal || rfm.open) return;
    rfmV = $("#ref-sel").value; $("#rfm-cm").value = rfmV === "otro" ? $("#ref-otro").value : "";
    rfmPintar(); rfm.showModal();
  }
  if (rfm) {
    $$(".rfm-op", rfm).forEach(function (b) { b.addEventListener("click", function () { rfmV = b.dataset.v; rfmPintar(); if (rfmV === "otro") $("#rfm-cm").focus(); }); });
    $("#rfm-cm").addEventListener("input", rfmPintar);
    $("#rfm-ok").addEventListener("click", function () {
      var sel = $("#ref-sel"); sel.value = rfmV;
      if (rfmV === "otro") $("#ref-otro").value = ($("#rfm-cm").value || "").replace(",", ".");
      sel.dispatchEvent(new Event("change")); if (rfmV === "otro") $("#ref-otro").dispatchEvent(new Event("input"));
      rfm.close();
    });
    $$("[data-rfm-cerrar]", rfm).forEach(function (b) { b.addEventListener("click", function () { rfm.close(); }); });
    rfm.addEventListener("click", function (e) { if (e.target === rfm) rfm.close(); });
  }

  // ---------- navegación entre pasos
  function mostrar(n) {
    $("#form").dataset.dir = n >= paso ? "f" : "b";
    paso = n;
    $("#stepper").dataset.paso = n;
    var sb = $("#smart-banner"); if (sb) sb.hidden = n !== 1;
    $$("[data-step]").forEach(function (s) { s.hidden = +s.dataset.step !== n; });
    $$("[data-ind]").forEach(function (i) { var k = +i.dataset.ind; i.dataset.estado = k < n ? "hecho" : k === n ? "activo" : ""; });
    var h = $("#h" + n); if (h) h.focus({ preventScroll: true });
    window.scrollTo({ top: 0, behavior: "smooth" });
    if (n === 2 && !guiaVista) { guiaVista = true; guia(true); }
    if (n === 3) { dibujar(); instruccion(); }
    if (n === 4) resumen();
  }
  function error(n, msg) { $("#err-" + n).textContent = msg || ""; }
  function val(name) { var e = form.querySelector('[name="' + name + '"]:checked'); return e ? e.value : ""; }

  $$('input[name="senales"][value="inclinacion"]').forEach(function (c) {
    c.addEventListener("change", function () {
      if (c.checked && !window.confirm("¿Confirmas que ves la edificación o el elemento claramente inclinado a simple vista? Marcarlo lleva el resultado a ROJO.")) c.checked = false;
    });
  });
  $$("[data-next]").forEach(function (b) { b.addEventListener("click", function () { if (validar(paso)) mostrar(paso + 1); }); });
  $$("[data-prev]").forEach(function (b) { b.addEventListener("click", function () { mostrar(paso - 1); }); });

  function validar(n) {
    error(n, "");
    if (n === 1 && !val("elemento")) { error(1, "Elige el elemento donde está la grieta."); return false; }
    if (n === 1 && !val("ancho_cat")) { error(1, "Elige el ancho aproximado de la grieta (si no sabes, marca «No sé» o compárala con una tarjeta)."); return false; }
    if (n === 2) {
      if (!blob) { error(2, "Agrega una fotografía."); return false; }
      if (fotoBloqueo) { error(2, fotoBloqueo); return false; }
      if (!$("#consentimiento").checked) { error(2, "Debes autorizar el procesamiento de la foto."); return false; }
      if (!val("elemento") || !val("ancho_cat")) { error(2, "Faltan datos del paso 1 (elemento y ancho). Pulsa «Autocompletar» y acepta, o vuelve al paso 1."); return false; }
    }
    if (n === 3) {
      if (modo() === "estimado") {
        if (!val("largo_cat")) { error(3, "Elige qué tan larga se ve la grieta (corta, media o larga)."); return false; }
        if (!val("eje_est")) { error(3, "Elige hacia dónde va la grieta (horizontal, vertical o diagonal)."); return false; }
      } else if (modo() === "manual") {
        var xy = manualXY();
        if (!(xy.x >= 0 && xy.y >= 0 && xy.x <= 2000 && xy.y <= 2000) || (xy.x === 0 && xy.y === 0)) { error(3, "Ingresa la longitud en el eje X, en el eje Y o en ambos (en cm)."); return false; }
      } else {
        if (ref.length < 2) { error(3, "Marca los dos extremos del objeto de referencia (tarjeta o regla junto a la grieta)."); return false; }
        if (!enviarLineas().length) { error(3, "Marca la grieta: toca su inicio y su final (o inicio y «Seguir la grieta»)."); return false; }
        if (!refMm()) { error(3, "Indica la medida real del objeto de referencia."); return false; }
        var avs = avisosRef(), clave = JSON.stringify([ref, refMm()]);
        if (avs.length && clave !== refConfirmada) {                  // referencia improbable: confirmar antes de medir con ella
          if (!window.confirm(avs.join("\n\n").replace(/⚠ /g, "") + "\n\n¿Aun así quieres continuar con esta referencia?")) { error(3, "Corrige la referencia (punto naranja) o su medida real y vuelve a continuar."); return false; }
          refConfirmada = clave;
        }
      }
    }
    return true;
  }

  // ---------- paso 2: foto
  // Control de calidad: mismos umbrales que el servidor (analysis/images.py). Muy mala = hay que repetirla; leve = solo aviso.
  var fotoBloqueo = "";
  function calidadFoto(c) {
    var W = c.width, H = c.height, d = c.getContext("2d").getImageData(0, 0, W, H).data, n = W * H, g = new Float32Array(n), suma = 0, i, x, y;
    for (i = 0; i < n; i++) { g[i] = 0.299 * d[4 * i] + 0.587 * d[4 * i + 1] + 0.114 * d[4 * i + 2]; suma += g[i]; }
    var br = suma / n, sq = 0; for (i = 0; i < n; i++) sq += (g[i] - br) * (g[i] - br);
    var sd = Math.sqrt(sq / n), ls = 0, lq = 0, k = 0;
    for (y = 1; y < H - 1; y++) for (x = 1; x < W - 1; x++) { i = y * W + x; var l = g[i - 1] + g[i + 1] + g[i - W] + g[i + W] - 4 * g[i]; ls += l; lq += l * l; k++; }
    var nit = k ? lq / k - (ls / k) * (ls / k) : 0;
    var q = { nit: nit, br: br, sd: sd, bloqueo: "", aviso: "" };
    if (nit < 12) q.bloqueo = "La foto está muy borrosa. Repítela con el celular quieto, enfocando la grieta (toca la pantalla para enfocar).";
    else if (br < 30) q.bloqueo = "La foto está demasiado oscura. Repítela con más luz (luz natural o una linterna de lado).";
    else if (br > 245) q.bloqueo = "La foto está sobreexpuesta (muy clara). Repítela sin flash directo ni luz fuerte de frente.";
    else if (sd < 5) q.bloqueo = "La foto casi no tiene detalle (muy plana). Acércate a la grieta y repítela con buena luz.";
    else if (nit < 40) q.aviso = "La foto está algo borrosa: si puedes, repítela más nítida.";
    else if (br < 55) q.aviso = "La foto está oscura: si puedes, repítela con más luz.";
    else if (br > 225) q.aviso = "La foto está muy clara: si puedes, repítela con menos luz.";
    return q;
  }
  function revisarCalidad(c) {
    var q; try { q = calidadFoto(c); } catch (e) { return; }
    fotoBloqueo = q.bloqueo; var a = $("#aviso-foto");
    a.hidden = !q.aviso; a.textContent = q.aviso;
    error(2, q.bloqueo);
  }
  function cargar(archivo) {
    if (!archivo) return;
    error(2, "");
    if (!/^image\//.test(archivo.type)) { error(2, "El archivo debe ser una imagen."); return; }
    createImageBitmap(archivo, { imageOrientation: "from-image" }).then(function (b) {
      var esc = Math.min(1, MAX / Math.max(b.width, b.height));
      var c = document.createElement("canvas"); c.width = Math.round(b.width * esc); c.height = Math.round(b.height * esc);
      c.getContext("2d").drawImage(b, 0, 0, c.width, c.height);
      c.toBlob(function (bl) {
        if (!bl) { error(2, "No pudimos procesar esa imagen."); return; }
        blob = bl; bmp = c; mapa = null; reiniciarMarcas(); revisarCalidad(c);
        var url = URL.createObjectURL(bl); $("#foto-img").src = url; $("#ov-img").src = url;
        $("#foto-info").textContent = c.width + " × " + c.height + " px · " + (bl.size / 1024 / 1024).toFixed(2).replace(".", ",") + " MB";
        $("#vista-foto").hidden = false; $("#zona-foto").hidden = true;
        $("#sugerencia").hidden = false; sugReset();
      }, "image/jpeg", 0.9);
    }).catch(function () { error(2, "No pudimos leer esa imagen. Prueba con JPG o PNG."); });
  }

  // ---------- cámara con getUserMedia (HTTPS o localhost); si falla, cae al selector nativo con capture
  var stream = null, facing = "environment", modal = $("#modal-camara"), video = $("#video-camara");
  if (modal && modal.parentNode !== document.body) document.body.appendChild(modal);   // fixed dentro de una tarjeta con efecto vidrio queda recortado
  function camMsg(t) { var m = $("#camara-msg"); m.textContent = t || ""; m.hidden = !t; }
  function camStop() { if (stream) { stream.getTracks().forEach(function (t) { t.stop(); }); stream = null; } video.srcObject = null; }
  function camCerrar() { camStop(); modal.hidden = true; document.body.style.overflow = ""; }
  function camIniciar() {
    camStop(); $("#cam-capturar").disabled = true; camMsg("Iniciando cámara…");
    var pref = { video: { facingMode: { ideal: facing }, width: { ideal: 1920 }, height: { ideal: 1080 } }, audio: false };
    return navigator.mediaDevices.getUserMedia(pref).catch(function () { return navigator.mediaDevices.getUserMedia({ video: true, audio: false }); }).then(function (st) {
      stream = st; video.srcObject = st; return video.play().catch(function () {});
    }).then(function () {
      camMsg(""); $("#cam-capturar").disabled = false;
      navigator.mediaDevices.enumerateDevices().then(function (d) { $("#cam-girar").hidden = d.filter(function (x) { return x.kind === "videoinput"; }).length < 2; }).catch(function () {});
    });
  }
  function camFallback(msg) { camCerrar(); error(2, msg || ""); $("#foto-camara").click(); }
  $("#btn-camara").addEventListener("click", function () {
    error(2, "");
    if (!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia) || !window.isSecureContext) { $("#foto-camara").click(); return; }
    modal.hidden = false; document.body.style.overflow = "hidden";
    camIniciar().catch(function (e) {
      var denegado = e && (e.name === "NotAllowedError" || e.name === "SecurityError");
      camFallback(denegado ? "Permiso de cámara denegado. Puedes habilitarlo en el navegador o elegir una foto del dispositivo." : "No se pudo abrir la cámara; elige una foto del dispositivo.");
    });
  });
  $("#cam-cerrar").addEventListener("click", camCerrar);
  $("#cam-girar").addEventListener("click", function () { facing = facing === "environment" ? "user" : "environment"; camIniciar().catch(function () { camMsg("No se pudo cambiar de cámara."); }); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !modal.hidden) camCerrar(); });
  $("#cam-capturar").addEventListener("click", function () {
    if (!video.videoWidth) return;
    var c = document.createElement("canvas"); c.width = video.videoWidth; c.height = video.videoHeight;
    c.getContext("2d").drawImage(video, 0, 0, c.width, c.height);
    c.toBlob(function (b) { camCerrar(); if (b) cargar(b); else error(2, "No pudimos capturar la imagen."); }, "image/jpeg", 0.92);
  });
  $("#foto-camara").addEventListener("change", function (e) { cargar(e.target.files[0]); e.target.value = ""; });
  $("#foto-archivo").addEventListener("change", function (e) { cargar(e.target.files[0]); e.target.value = ""; });
  $("#foto-cambiar").addEventListener("click", function () { blob = bmp = null; fotoBloqueo = ""; $("#aviso-foto").hidden = true; error(2, ""); $("#vista-foto").hidden = true; $("#zona-foto").hidden = false; });

  // ---------- paso 3: medición
  // Modelo: la grieta se compone de una o varias LÍNEAS. Cada línea tiene «anclas» (los puntos que tocas) y «tramos»
  // (el camino entre dos anclas; con «Ajustar a la grieta» sigue la grieta sola, si no es una recta).
  var COLORES = ["#facc15", "#fb923c", "#a3e635", "#38bdf8", "#f472b6", "#c084fc", "#2dd4bf", "#f87171"];
  var lineas = [], activa = -1, historial = [], mapa = null, MAPA_LADO = 900;
  function modo() { return val("modo") || "trazo"; }
  $$('input[name="modo"]').forEach(function (r) {
    r.addEventListener("change", function () { $("#panel-trazo").hidden = modo() !== "trazo"; $("#panel-manual").hidden = modo() !== "manual"; $("#panel-estimado").hidden = modo() !== "estimado"; if (modo() === "trazo") dibujar(); });
  });
  function refMm() {
    var v = $("#ref-sel").value; if (v === "otro") v = (parseFloat(($("#ref-otro").value || "").replace(",", ".")) * 10);   // el campo se escribe en cm
    var n = parseFloat(v); return n >= 5 && n <= 5000 ? n : 0;
  }
  $("#ref-sel").addEventListener("change", function () { refOrigen = ""; $("#ref-otro").hidden = this.value !== "otro"; lectura(); });
  $("#ref-otro").addEventListener("input", function () { refOrigen = ""; lectura(); });
  // Aviso amable cuando la IA externa falla (cuota, límite de uso, red): el llenado manual sigue funcionando.
  function fallaIA(id, e) {
    var el = $(id), raw = (e && e.message) || "";
    el.textContent = raw === "Failed to fetch"
      ? "Sin conexión: la sugerencia con IA no está disponible. El autocompletado manual sigue funcionando: completa los datos tú mismo y continúa."
      : "La IA no está disponible por ahora (límite de uso o fallo del servicio). El autocompletado manual está disponible y funcional: completa los datos tú mismo y continúa sin interrupciones.";
    el.hidden = false;
  }
  // ---------- autocompletar el formulario con la foto (la IA propone; el usuario acepta o modifica)
  var sugerido = null;
  var NOMBRES = { elemento: "Elemento", material: "Material", ancho_cat: "Ancho", eje: "Dirección de la grieta", patron: "Cruce en X", senales: "Señales" };
  function etiqueta(name, v) {
    var i = form.querySelector('[name="' + name + '"][value="' + v + '"]'); if (!i) return v;
    var l = i.closest("label"); var b = l && l.querySelector("b"); return ((b || l).textContent || v).trim();
  }
  function sugReset() { sugerido = null; $("#sug-lista").hidden = true; $("#sug-acciones").hidden = true; $("#sug-msg").textContent = "Marca la autorización de abajo y pulsa «Autocompletar»: se propone elemento, material, ancho, dirección y señales. Tú decides si aceptas."; }
  function marcar(name, v) { var i = form.querySelector('[name="' + name + '"][value="' + v + '"]'); if (i) { i.checked = true; i.dispatchEvent(new Event("change", { bubbles: true })); } }
  $("#btn-autocompletar").addEventListener("click", function () {
    var btn = this, msg = $("#sug-msg");
    if (!blob) { msg.textContent = "Primero agrega una foto."; return; }
    if (!$("#consentimiento").checked) { msg.textContent = "Marca la autorización para procesar la foto y vuelve a pulsar «Autocompletar»."; return; }
    var fd = new FormData(); fd.append("imagen", blob, "grieta.jpg"); btn.disabled = true; msg.textContent = "Leyendo la foto…"; $("#sug-fallo").hidden = true;
    fetch("/api/v1/autocompletar", { method: "POST", body: fd, headers: { "X-CSRF-Token": csrf }, credentials: "same-origin" })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { if (!r.ok) throw new Error(j.error || "No se pudo leer la foto."); return j; }); })
      .then(function (j) {
        var c = j.campos || {}, lista = $("#sug-lista"); lista.textContent = ""; sugerido = c;
        Object.keys(NOMBRES).forEach(function (k) {
          if (c[k] === undefined) return;
          var txt = k === "senales" ? c[k].map(function (v) { return etiqueta("senales", v); }).join("; ") : k === "patron" ? "Sí, se cruzan" : etiqueta(k === "eje" ? "eje" : k, c[k]);
          var fila = document.createElement("div"); fila.className = "flex justify-between gap-3 p-3";
          var a = document.createElement("dt"); a.className = "text-ink-500 dark:text-ink-400"; a.textContent = NOMBRES[k];
          var b = document.createElement("dd"); b.className = "text-right font-semibold"; b.textContent = txt; fila.append(a, b); lista.append(fila);
        });
        var hay = lista.children.length > 0; lista.hidden = !hay; $("#sug-acciones").hidden = !hay;
        var conf = typeof j.confianza === "number" ? " Confianza: " + Math.round(j.confianza * 100) + " %." : "";
        msg.textContent = (hay ? "Esto es lo que se ve en la foto. Es una sugerencia: revísala." + conf + " " : "No se pudo proponer nada con esta foto. ") + (j.observaciones || "");
        if (c.senales && c.senales.indexOf("inclinacion") >= 0) msg.textContent += " Si ves la inclinación a simple vista, márcala tú en «Señales» (lleva el resultado a ROJO).";
      })
      .catch(function (e) { msg.textContent = "Puedes llenar el formulario a mano."; fallaIA("#sug-fallo", e); })
      .finally(function () { btn.disabled = false; });
  });
  $("#sug-aceptar").addEventListener("click", function () {
    var c = sugerido || {};
    ["elemento", "material", "ancho_cat", "patron"].forEach(function (k) { if (c[k]) marcar(k, c[k]); });
    if (c.eje) { marcar("eje", c.eje); marcar("eje_est", c.eje); }
    (c.senales || []).forEach(function (v) { if (v === "inclinacion") return; var i = form.querySelector('input[name="senales"][value="' + v + '"]'); if (i) { i.checked = true; } });
    if (window.marcarOpciones) window.marcarOpciones();
    $("#sug-acciones").hidden = true; $("#sug-msg").textContent = "Listo: se llenó el formulario con la sugerencia. Puedes cambiar cualquier dato en el paso 1 antes de analizar."; error(2, "");
  });
  $("#sug-modificar").addEventListener("click", function () {
    $("#sug-aceptar").click(); mostrar(1);
  });
  $("#empezar-foto").addEventListener("click", function () { mostrar(2); });

  // Escala con IA: propone un objeto de tamaño típico (puerta, interruptor, bloque, hoja…) y sus extremos; el usuario los revisa.
  if ($("#wizard").dataset.iaEscala === "1") $("#ia-escala").hidden = false;
  $("#btn-ia-escala").addEventListener("click", function () {
    if (!blob) { error(3, "Primero agrega una foto."); return; }
    var btn = this, msg = $("#ia-escala-msg"), fd = new FormData(); btn.disabled = true; msg.textContent = "Buscando un objeto de referencia…"; $("#ia-escala-fallo").hidden = true;
    fd.append("imagen", blob, "grieta.jpg");
    fetch("/api/v1/escala", { method: "POST", body: fd, headers: { "X-CSRF-Token": csrf }, credentials: "same-origin" })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { if (!r.ok) throw new Error(j.error || "No se pudo estimar la escala."); return j; }); })
      .then(function (j) {
        if (!j.encontrado) { msg.textContent = "La IA no encontró un objeto claro y completo. Usa una tarjeta o regla junto a la grieta."; return; }
        guardar(); ref = j.ref.map(function (p) { return [p[0], p[1]]; });
        $("#ref-sel").value = "otro"; $("#ref-otro").hidden = false; $("#ref-otro").value = Math.round(j.mm) / 10; refOrigen = "ia"; setFase("trazo"); redibujar();
        msg.textContent = "La IA sugiere: " + j.nombre + " (" + (j.lado === "largo" ? "lado largo" : "lado corto") + ", " + String(Math.round(j.mm) / 10).replace(".", ",") + " cm, ±" + j.error_pct + " %). Revisa que los dos puntos de la referencia estén en los extremos del objeto; si no, tócalos para corregirlos.";
      })
      .catch(function (e) { msg.textContent = "Marca la referencia a mano: elige un objeto de la lista y toca sus dos extremos en la foto."; fallaIA("#ia-escala-fallo", e); })
      .finally(function () { btn.disabled = false; });
  });

  // --- mapa de «cresta oscura» (la grieta es una línea oscura y delgada): se calcula una vez por foto en el navegador
  function caja(g, W, H, r) {                                  // media local con imagen integral
    var I = new Float64Array((W + 1) * (H + 1)), x, y, o = new Float32Array(W * H);
    for (y = 0; y < H; y++) { var fila = 0; for (x = 0; x < W; x++) { fila += g[y * W + x]; I[(y + 1) * (W + 1) + x + 1] = I[y * (W + 1) + x + 1] + fila; } }
    for (y = 0; y < H; y++) for (x = 0; x < W; x++) {
      var x0 = Math.max(0, x - r), x1 = Math.min(W - 1, x + r), y0 = Math.max(0, y - r), y1 = Math.min(H - 1, y + r);
      o[y * W + x] = (I[(y1 + 1) * (W + 1) + x1 + 1] - I[y0 * (W + 1) + x1 + 1] - I[(y1 + 1) * (W + 1) + x0] + I[y0 * (W + 1) + x0]) / ((x1 - x0 + 1) * (y1 - y0 + 1));
    }
    return o;
  }
  function getMapa() {
    if (mapa || !bmp) return mapa;
    var sc = Math.min(1, MAPA_LADO / Math.max(bmp.width, bmp.height)), W = Math.max(8, Math.round(bmp.width * sc)), H = Math.max(8, Math.round(bmp.height * sc));
    var c = document.createElement("canvas"); c.width = W; c.height = H;
    var x = c.getContext("2d", { willReadFrequently: true }); x.drawImage(bmp, 0, 0, W, H);
    var d = x.getImageData(0, 0, W, H).data, g = new Float32Array(W * H), i;
    for (i = 0; i < W * H; i++) g[i] = 0.299 * d[4 * i] + 0.587 * d[4 * i + 1] + 0.114 * d[4 * i + 2];
    var gs = caja(g, W, H, 1), mu = caja(g, W, H, Math.max(5, Math.round(0.014 * Math.hypot(W, H)))), bh = new Float32Array(W * H), m = [];
    for (i = 0; i < W * H; i++) bh[i] = Math.max(0, mu[i] - gs[i]);
    for (i = 0; i < W * H; i += 7) m.push(bh[i]);
    m.sort(function (a, b) { return a - b; });
    var p97 = Math.max(6, m[Math.floor(m.length * 0.97)] || 6), bn = new Float32Array(W * H), cost = new Float32Array(W * H);
    for (i = 0; i < W * H; i++) { var v = Math.min(1, bh[i] / p97); bn[i] = v; cost[i] = 1 / (0.05 + v); }
    mapa = { W: W, H: H, bn: bn, cost: cost };
    return mapa;
  }
  var gx = function (p) { return Math.min(mapa.W - 1, Math.max(0, Math.round(p[0] * mapa.W - 0.5))); };
  var gy = function (p) { return Math.min(mapa.H - 1, Math.max(0, Math.round(p[1] * mapa.H - 0.5))); };
  var nrm = function (x, y) { return [(x + 0.5) / mapa.W, (y + 0.5) / mapa.H]; };
  function muestra(x, y) { var xi = Math.round(x), yi = Math.round(y); return (xi < 0 || yi < 0 || xi >= mapa.W || yi >= mapa.H) ? 0 : mapa.bn[yi * mapa.W + xi]; }

  function imanPunto(p) {                                       // pega el toque a la cresta más cercana (≤ 7 px)
    if (!$("#ajustar").checked || !getMapa()) return p;
    var cx = gx(p), cy = gy(p), mejor = -1, bx = cx, by = cy;
    for (var dy = -7; dy <= 7; dy++) for (var dx = -7; dx <= 7; dx++) {
      var r = Math.hypot(dx, dy); if (r > 7) continue;
      var v = muestra(cx + dx, cy + dy) - r * 0.02; if (v > mejor) { mejor = v; bx = cx + dx; by = cy + dy; }
    }
    return muestra(bx, by) > 0.35 ? nrm(bx, by) : p;
  }
  var DX = [1, -1, 0, 0, 1, 1, -1, -1], DY = [0, 0, 1, -1, 1, -1, 1, -1], DL = [1, 1, 1, 1, 1.414, 1.414, 1.414, 1.414];
  function suavizar(pts) {
    if (pts.length < 5) return pts;
    return pts.map(function (p, i) {
      if (i === 0 || i === pts.length - 1) return p;
      var a = Math.max(0, i - 2), b = Math.min(pts.length - 1, i + 2), sx = 0, sy = 0, n = 0;
      for (var k = a; k <= b; k++) { sx += pts[k][0]; sy += pts[k][1]; n++; }
      return [sx / n, sy / n];
    });
  }
  function caminoCresta(a, b) {                                 // ruta de menor coste (Dijkstra) entre dos puntos
    var m = getMapa(), ax = gx(a), ay = gy(a), bx = gx(b), by = gy(b), dist = Math.hypot(bx - ax, by - ay);
    if (dist < 3) return [a, b];
    var pad = Math.max(20, Math.min(70, Math.round(dist * 0.18))), ux0 = (bx - ax) / dist, uy0 = (by - ay) / dist, x0 = Math.max(0, Math.min(ax, bx) - pad), x1 = Math.min(m.W - 1, Math.max(ax, bx) + pad),
        y0 = Math.max(0, Math.min(ay, by) - pad), y1 = Math.min(m.H - 1, Math.max(ay, by) + pad), w = x1 - x0 + 1, h = y1 - y0 + 1, n = w * h;
    var D = new Float64Array(n).fill(Infinity), P = new Int32Array(n).fill(-1), hk = [], hv = [];
    function push(k, v) { var i = hk.length; hk.push(k); hv.push(v); while (i > 0) { var j = (i - 1) >> 1; if (hk[j] <= hk[i]) break; var tk = hk[i], tv = hv[i]; hk[i] = hk[j]; hv[i] = hv[j]; hk[j] = tk; hv[j] = tv; i = j; } }
    function pop() {
      var k = hk[0], v = hv[0], lk = hk.pop(), lv = hv.pop();
      if (hk.length) { hk[0] = lk; hv[0] = lv; var i = 0, N = hk.length; for (;;) { var l = 2 * i + 1, r = l + 1, s = i; if (l < N && hk[l] < hk[s]) s = l; if (r < N && hk[r] < hk[s]) s = r; if (s === i) break; var tk = hk[i], tv = hv[i]; hk[i] = hk[s]; hv[i] = hv[s]; hk[s] = tk; hv[s] = tv; i = s; } }
      return [k, v];
    }
    var s0 = (ay - y0) * w + (ax - x0), t0 = (by - y0) * w + (bx - x0); D[s0] = 0; push(0, s0);
    while (hk.length) {
      var e = pop(), d0 = e[0], u = e[1]; if (d0 > D[u]) continue; if (u === t0) break;
      var ux = u % w, uy = (u / w) | 0;
      for (var k = 0; k < 8; k++) {
        var vx = ux + DX[k], vy = uy + DY[k]; if (vx < 0 || vy < 0 || vx >= w || vy >= h) continue;
        var rx = vx + x0 - ax, ry = vy + y0 - ay, along = rx * ux0 + ry * uy0;                 // corredor alrededor de la recta a→b
        if (Math.abs(rx * uy0 - ry * ux0) > pad || along < -pad || along > dist + pad) continue;
        var vi = vy * w + vx, nd = d0 + m.cost[(vy + y0) * m.W + vx + x0] * DL[k];
        if (nd < D[vi]) { D[vi] = nd; P[vi] = u; push(nd, vi); }
      }
    }
    if (!isFinite(D[t0])) return [a, b];
    var ruta = [], c = t0; while (c !== -1) { ruta.push([c % w + x0, ((c / w) | 0) + y0]); c = P[c]; }
    ruta.reverse();
    var largo = 0; for (var i = 1; i < ruta.length; i++) largo += Math.hypot(ruta[i][0] - ruta[i - 1][0], ruta[i][1] - ruta[i - 1][1]);
    if (largo > 2.6 * dist + 12) return [a, b];                 // rodeo absurdo: mejor la recta
    var pts = suavizar(ruta.map(function (q) { return nrm(q[0], q[1]); }));
    pts[0] = a; pts[pts.length - 1] = b; return pts;
  }
  function tramo(a, b) { return $("#ajustar").checked && getMapa() ? caminoCresta(a, b) : [a, b]; }

  // --- «Seguir la grieta»: avanza por la cresta desde el último punto hasta que se desvanece
  function mejorDireccion(x, y) {
    var mejor = -1, ang = 0;
    for (var k = 0; k < 24; k++) {
      var a = k * Math.PI / 12, s = 0; for (var j = 1; j <= 6; j++) s += muestra(x + Math.cos(a) * 3 * j, y + Math.sin(a) * 3 * j);
      if (s > mejor) { mejor = s; ang = a; }
    }
    return ang;
  }
  function seguirDesde(x, y, dir) {
    var paso = 3, pts = [], hist = [], visto = {}, max = Math.round(3 * Math.max(mapa.W, mapa.H) / paso);
    for (var k = 0; k < max; k++) {
      var mejor = -9, mA = dir;
      for (var da = -40; da <= 40; da += 10) {
        var a = dir + da * Math.PI / 180, sc = 0; for (var j = 1; j <= 3; j++) sc += muestra(x + Math.cos(a) * paso * 2 * j, y + Math.sin(a) * paso * 2 * j);
        sc = sc / 3 - 0.12 * Math.abs(da) / 40; if (sc > mejor) { mejor = sc; mA = a; }
      }
      dir = Math.atan2(0.55 * Math.sin(dir) + 0.45 * Math.sin(mA), 0.55 * Math.cos(dir) + 0.45 * Math.cos(mA));
      x += Math.cos(dir) * paso; y += Math.sin(dir) * paso;
      if (x < 2 || y < 2 || x > mapa.W - 3 || y > mapa.H - 3) break;
      var px = -Math.sin(dir), py = Math.cos(dir), bo = -1, bd = 0;
      for (var o = -2; o <= 2; o++) { var v = muestra(x + px * o, y + py * o); if (v > bo) { bo = v; bd = o; } }
      x += px * bd * 0.5; y += py * bd * 0.5;
      var key = ((x / 3) | 0) + "," + ((y / 3) | 0); if (visto[key] !== undefined && k - visto[key] > 8) break; visto[key] = k;
      hist.push(muestra(x, y)); pts.push([x, y]);
      if (hist.length >= 10) { var sm = 0; for (var q = hist.length - 10; q < hist.length; q++) sm += hist[q]; if (sm / 10 < 0.2) break; }
    }
    while (pts.length && hist[pts.length - 1] < 0.25) { pts.pop(); hist.pop(); }
    return pts;
  }
  function seguir() {
    error(3, ""); var L = lineas[activa];
    if (!bmp || !L || !L.anclas.length) { error(3, "Toca primero un punto sobre la grieta y luego pulsa «Seguir la grieta»."); return; }
    getMapa(); var antes = foto(), a = L.anclas[L.anclas.length - 1], x = gx(a), y = gy(a), conv = function (q) { return nrm(q[0], q[1]); };
    var largoMin = 8;
    if (L.anclas.length === 1) {                                // un solo punto: sigue en los dos sentidos
      var d = mejorDireccion(x, y), f = seguirDesde(x, y, d), r = seguirDesde(x, y, d + Math.PI);
      if (f.length < largoMin && r.length < largoMin) { error(3, "No encontré más grieta desde ese punto. Marca los puntos a mano."); return; }
      var ini = a, tr = [];
      if (r.length >= largoMin) { var rr = r.map(conv).reverse(); L.anclas = [rr[0], a]; tr.push(suavizar([rr[0]].concat(rr.slice(1), [a]))); } else L.anclas = [a];
      if (f.length >= largoMin) { var ff = f.map(conv); L.anclas.push(ff[ff.length - 1]); tr.push(suavizar([a].concat(ff))); }
      L.tramos = tr;
    } else {
      var ult = L.tramos[L.tramos.length - 1], k2 = Math.max(0, ult.length - 8), u0 = ult[k2], u1 = ult[ult.length - 1];
      var dir = Math.atan2((u1[1] - u0[1]) * mapa.H, (u1[0] - u0[0]) * mapa.W), f2 = seguirDesde(x, y, dir);
      if (f2.length < largoMin) { error(3, "No encontré más grieta en esa dirección. Marca los puntos a mano."); return; }
      var g2 = f2.map(conv); L.anclas.push(g2[g2.length - 1]); L.tramos.push(suavizar([a].concat(g2)));
    }
    historial.push(antes); redibujar();
  }

  // --- estado, historial (instantáneas) y edición
  function foto() { return JSON.stringify({ ref: ref, lineas: lineas, activa: activa, fase: fase }); }
  function restaurar(js) { var o = JSON.parse(js); ref = o.ref; lineas = o.lineas; activa = o.activa; setFase(o.fase); }
  var refOrigen = "", refConfirmada = "";
  function reiniciarMarcas() { refOrigen = ""; ref = []; lineas = []; activa = -1; historial = []; setFase("ref"); }
  function guardar() { historial.push(foto()); if (historial.length > 200) historial.shift(); }
  function asegurarLinea() { if (activa < 0 || !lineas[activa]) { lineas.push({ anclas: [], tramos: [] }); activa = lineas.length - 1; } return lineas[activa]; }
  function agregarAncla(p) {
    var L = asegurarLinea(); if (L.anclas.length >= 80) return;
    p = imanPunto(p); if (L.anclas.length) L.tramos.push(tramo(L.anclas[L.anclas.length - 1], p)); L.anclas.push(p);
  }
  function quitarAncla(L, i) {
    L.anclas.splice(i, 1); L.tramos = [];
    for (var k = 1; k < L.anclas.length; k++) L.tramos.push(tramo(L.anclas[k - 1], L.anclas[k]));
    if (!L.anclas.length && lineas.length > 1) { var j = lineas.indexOf(L); lineas.splice(j, 1); activa = Math.min(activa, lineas.length - 1); }
  }
  function setFase(f) {
    fase = f;
    $$("[data-fase]").forEach(function (b) { b.setAttribute("aria-pressed", b.dataset.fase === f ? "true" : "false"); });
    instruccion();
  }
  $$("[data-fase]").forEach(function (b) { b.addEventListener("click", function () { setFase(b.dataset.fase); }); });
  function nAnclas() { return lineas.reduce(function (n, L) { return n + L.anclas.length; }, 0); }
  // la instrucción flotante se puede ocultar con la X y volver con el botón «Ayuda»
  function hintVer(v) { var h = $("#instruccion"), b = $("#instr-ver"); if (h) h.hidden = !v; if (b) b.hidden = v; }
  if ($("#instr-x")) { $("#instr-x").addEventListener("click", function () { hintVer(false); }); $("#instr-ver").addEventListener("click", function () { hintVer(true); }); }
  function instruccion() {
    var t;
    if (fase === "ref") t = ref.length < 2
      ? "Paso 1 · Referencia: toca los DOS EXTREMOS de un objeto de medida conocida (tarjeta, regla, moneda) que pusiste junto a la grieta (" + (ref.length + 1) + " de 2). No marques la grieta aquí."
      : "Referencia lista. Ahora marca la grieta (paso 2) o toca un extremo para corregirlo.";
    else if (!nAnclas()) t = "Paso 2 · Grieta: toca el INICIO de la grieta. Después toca el final y la app seguirá la grieta sola, o pulsa «Seguir la grieta» para que rellene todo el recorrido.";
    else t = "Toca más puntos, o pulsa «Seguir la grieta» para completar el recorrido. Toca un punto para borrarlo. Si hay otra rama, usa «+ Nueva línea». (" + nAnclas() + " puntos en " + lineas.length + (lineas.length === 1 ? " línea)." : " líneas).");
    var it = $("#instruccion-t"); if (it) it.textContent = t; else $("#instruccion").textContent = t;
    var av = avisosRef(), el = $("#aviso-ref"); el.hidden = !av.length; el.textContent = av.join(" ");
    chips();
  }
  function chips() {
    var c = $("#lineas-chips"); if (!c) return;
    c.innerHTML = lineas.map(function (L, i) {
      return '<button type="button" data-linea="' + i + '" class="chip !min-h-9 !px-3 !py-1 text-xs" aria-pressed="' + (i === activa) + '"><span class="inline-block h-2.5 w-2.5 shrink-0 rounded-full" style="background:' + COLORES[i % 8] + '"></span>Línea ' + (i + 1) + " · " + L.anclas.length + " pts</button>";
    }).join("");
    $$("[data-linea]", c).forEach(function (b) { b.addEventListener("click", function () { activa = +b.dataset.linea; setFase("trazo"); dibujar(); }); });
  }

  // --- geometría (misma fórmula que el servidor: longitud total, caja X/Y y eje principal)
  function enviarLineas() {
    return lineas.map(function (L) {
      var pts = L.anclas.length ? [L.anclas[0]] : []; L.tramos.forEach(function (t) { pts = pts.concat(t.slice(1)); });
      var eps = 0.0006; var s = rdp(pts, eps); while (s.length > 380 && eps < 0.02) { eps *= 1.6; s = rdp(pts, eps); }
      return s;
    }).filter(function (p) { return p.length >= 2; });
  }
  function rdp(pts, eps) {
    if (pts.length < 3) return pts;
    var a = pts[0], b = pts[pts.length - 1], mx = -1, im = 0, W = bmp ? bmp.width : 1, H = bmp ? bmp.height : 1;
    var dx = (b[0] - a[0]) * W, dy = (b[1] - a[1]) * H, L = Math.hypot(dx, dy);
    for (var i = 1; i < pts.length - 1; i++) {
      var d = L ? Math.abs(dy * (pts[i][0] - a[0]) * W - dx * (pts[i][1] - a[1]) * H) / L : Math.hypot((pts[i][0] - a[0]) * W, (pts[i][1] - a[1]) * H);
      if (d > mx) { mx = d; im = i; }
    }
    if (mx / Math.max(W, H) <= eps) return [a, b];
    return rdp(pts.slice(0, im + 1), eps).slice(0, -1).concat(rdp(pts.slice(im), eps));
  }
  function ejePrincipal(lin) {
    var pts = []; lin.forEach(function (L) { for (var i = 1; i < L.length; i++) { var a = L[i - 1], b = L[i], n = Math.max(1, Math.floor(Math.hypot(b[0] - a[0], b[1] - a[1]) / 2)); for (var k = 0; k <= n; k++) pts.push([a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n]); } });
    if (pts.length < 2) return 0;
    var mx = 0, my = 0; pts.forEach(function (p) { mx += p[0]; my += p[1]; }); mx /= pts.length; my /= pts.length;
    var sxx = 0, syy = 0, sxy = 0; pts.forEach(function (p) { sxx += Math.pow(p[0] - mx, 2); syy += Math.pow(p[1] - my, 2); sxy += (p[0] - mx) * (p[1] - my); });
    return Math.abs(0.5 * Math.atan2(2 * sxy, sxx - syy) * 180 / Math.PI);
  }
  function avisosRef() {
    if (ref.length < 2 || !bmp) return [];
    var W = bmp.width, H = bmp.height, lado = Math.max(W, H), out = [], d = Math.hypot((ref[0][0] - ref[1][0]) * W, (ref[0][1] - ref[1][1]) * H);
    var mmR = refMm();
    if (d > 0.4 * lado && mmR && mmR <= 300) out.push("⚠ La referencia ocupa el " + Math.round(d / lado * 100) + " % de la foto pero indicaste que mide solo " + String(mmR / 10).replace(".", ",") + " cm. ¿Seguro que es una tarjeta o una regla? Si marcaste algo más grande (una puerta, un marco), escribe su medida real o usa un objeto pequeño pegado junto a la grieta.");
    if (d > 0.6 * lado) out.push("⚠ La referencia ocupa el " + Math.round(d / lado * 100) + " % de la foto: es muy grande para una tarjeta o regla. ¿Marcaste la grieta o una pared en vez del objeto?");
    var pts = []; lineas.forEach(function (L) { L.tramos.forEach(function (t) { pts = pts.concat(t); }); L.anclas.forEach(function (p) { pts.push(p); }); });
    if (pts.length && ref.every(function (r) { return pts.some(function (q) { return Math.hypot((r[0] - q[0]) * W, (r[1] - q[1]) * H) < 0.03 * lado; }); }))
      out.push("⚠ Los puntos de la referencia están sobre la grieta. La referencia debe ser un objeto de medida conocida junto a la grieta, no la grieta misma.");
    return out;
  }

  function dibujar() {
    if (!bmp) return;
    var cj = $("#lienzo-caja"), w = Math.max(280, cj.clientWidth) * zoom;
    lienzo.style.width = w + "px"; lienzo.style.height = (w * bmp.height / bmp.width) + "px";
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    lienzo.width = Math.round(w * dpr); lienzo.height = Math.round(w * bmp.height / bmp.width * dpr);
    ctx.drawImage(bmp, 0, 0, lienzo.width, lienzo.height);
    var P = function (p) { return [p[0] * lienzo.width, p[1] * lienzo.height]; }, r = Math.max(5, 6 * dpr);
    function linea(pts, col, ancho) {
      if (pts.length < 2) return;
      ctx.beginPath(); pts.map(P).forEach(function (p, i) { i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]); });
      ctx.lineWidth = ancho * dpr; ctx.strokeStyle = col; ctx.lineJoin = ctx.lineCap = "round"; ctx.stroke();
    }
    function puntos(pts, col, rad) {
      pts.map(P).forEach(function (p) { ctx.beginPath(); ctx.arc(p[0], p[1], rad, 0, 7); ctx.fillStyle = col; ctx.fill(); ctx.lineWidth = 2 * dpr; ctx.strokeStyle = "#111"; ctx.stroke(); });
    }
    ctx.setLineDash([]); linea(ref, "#f59e0b", 3); puntos(ref, "#f59e0b", r);
    lineas.forEach(function (L, i) {
      var col = COLORES[i % 8], ruta = []; ctx.globalAlpha = i === activa ? 1 : 0.7;
      L.tramos.forEach(function (t) { linea(t, "rgba(0,0,0,.55)", 5); });
      L.tramos.forEach(function (t) { linea(t, col, 2.6); });
      puntos(L.anclas, col, i === activa ? r : r * 0.8); ctx.globalAlpha = 1;
    });
    lectura();
  }
  var refFirma = "";
  function revisarRef() {
    var f = ref.length === 2 ? ref.map(function (q) { return q[0].toFixed(4) + "," + q[1].toFixed(4); }).join("|") : "";
    if (f && f !== refFirma) { refFirma = f; preguntarRef(); }
    else if (!f) refFirma = "";
  }
  function redibujar() { dibujar(); instruccion(); revisarRef(); }

  // Un toque (sin arrastre) agrega un punto; tocar un punto ya marcado lo elimina. Si el dedo se mueve, es desplazamiento.
  var down = null, HIT = 14;
  lienzo.addEventListener("pointerdown", function (e) { if (bmp && e.isPrimary !== false) down = { x: e.clientX, y: e.clientY, id: e.pointerId }; });
  lienzo.addEventListener("pointercancel", function () { down = null; });
  lienzo.addEventListener("pointerup", function (e) {
    if (!bmp || !down || down.id !== e.pointerId) return;
    var moved = Math.hypot(e.clientX - down.x, e.clientY - down.y); down = null;
    if (moved > 8) return;
    var b = lienzo.getBoundingClientRect(), p = [Math.min(1, Math.max(0, (e.clientX - b.left) / b.width)), Math.min(1, Math.max(0, (e.clientY - b.top) / b.height))];
    var cerca = function (q) { return Math.hypot((q[0] - p[0]) * b.width, (q[1] - p[1]) * b.height) <= HIT; };
    error(3, "");
    if (fase === "ref") {
      for (var i = ref.length - 1; i >= 0; i--) if (cerca(ref[i])) { guardar(); ref.splice(i, 1); redibujar(); return; }
      guardar(); if (ref.length >= 2) ref = []; ref.push(p); if (ref.length === 2) setFase("trazo"); redibujar(); return;
    }
    for (var li = lineas.length - 1; li >= 0; li--) for (var k = lineas[li].anclas.length - 1; k >= 0; k--) {
      if (cerca(lineas[li].anclas[k])) { guardar(); activa = li; quitarAncla(lineas[li], k); redibujar(); return; }
    }
    if (nAnclas() >= 400) return;
    guardar(); agregarAncla(p); redibujar();
  });
  // Deshacer: vuelve al estado anterior (cualquier fase). Limpiar fase / todo: también se pueden deshacer.
  function deshacer() { var h = historial.pop(); if (!h) return; restaurar(h); if (ref.length < 2) setFase("ref"); redibujar(); }
  function limpiarFase() { guardar(); if (fase === "ref") ref = []; else { lineas = []; activa = -1; } redibujar(); }
  function limpiarTodo() { guardar(); ref = []; lineas = []; activa = -1; setFase("ref"); redibujar(); }
  function nuevaLinea() {
    error(3, ""); if (activa >= 0 && lineas[activa] && !lineas[activa].anclas.length) return;
    if (lineas.length >= 8) { error(3, "Máximo 8 líneas."); return; }
    guardar(); lineas.push({ anclas: [], tramos: [] }); activa = lineas.length - 1; setFase("trazo"); redibujar();
  }
  $("#deshacer").addEventListener("click", deshacer);
  $("#limpiar").addEventListener("click", limpiarFase);
  $("#limpiar-todo").addEventListener("click", limpiarTodo);
  $("#nueva-linea").addEventListener("click", nuevaLinea);
  $("#seguir").addEventListener("click", seguir);
  $("#ajustar").addEventListener("change", function () {
    // al cambiar el modo se recalculan los tramos con el criterio nuevo
    guardar(); lineas.forEach(function (L) { L.tramos = []; for (var k = 1; k < L.anclas.length; k++) L.tramos.push(tramo(L.anclas[k - 1], L.anclas[k])); }); redibujar();
  });
  $("#zoom").addEventListener("input", function () { zoom = +this.value; dibujar(); });
  window.addEventListener("resize", function () { if (paso === 3) dibujar(); });

  // Cálculo local solo para mostrar una vista previa; el valor oficial lo calcula el servidor.
  function calcular() {
    var mm = refMm(), lin = enviarLineas(); if (ref.length < 2 || !lin.length || !mm || !bmp) return null;
    var W = bmp.width, H = bmp.height, d = function (a, b) { return Math.hypot((a[0] - b[0]) * W, (a[1] - b[1]) * H); };
    var k = d(ref[0], ref[1]) / mm; if (k <= 0) return null;
    var L = 0, xs = [], ys = []; lin.forEach(function (t) { for (var i = 0; i < t.length; i++) { xs.push(t[i][0] * W); ys.push(t[i][1] * H); if (i) L += d(t[i - 1], t[i]); } });
    var ex = Math.max.apply(null, xs) - Math.min.apply(null, xs), ey = Math.max.apply(null, ys) - Math.min.apply(null, ys);
    var ang = ejePrincipal(lin.map(function (t) { return t.map(function (p) { return [p[0] * W / k, p[1] * H / k]; }); }));
    return { largo: L / k / 10, ex: ex / k / 10, ey: ey / k / 10, ang: ang, ori: orient(ang), n: lin.length };
  }
  function orient(ang) { return ang <= 15 ? "horizontal" : ang >= 75 ? "vertical" : "diagonal"; }
  function manualXY() {
    var g = function (id) { var v = parseFloat(($(id).value || "").replace(",", ".")); return isNaN(v) ? 0 : v; };
    return { x: g("#x-cm"), y: g("#y-cm") };
  }
  function item(t, v) { return '<div class="an-meter"><dt>' + t + '</dt><dd>' + v + "</dd></div>"; }
  function lecturaManual() {
    var xy = manualXY(), el = $("#lectura-manual"), ok = xy.x + xy.y > 0, lg = Math.hypot(xy.x, xy.y), an = Math.atan2(xy.y, xy.x) * 180 / Math.PI;
    el.innerHTML = item("Longitud total", ok ? f1(lg) + " cm" : "—") + item("Ángulo (eje X)", ok ? f1(an) + "°" : "—");
    $$('input[name="eje"]').forEach(function (r) { r.checked = ok && r.value === orient(an); });
  }
  $("#x-cm").addEventListener("input", lecturaManual); $("#y-cm").addEventListener("input", lecturaManual); lecturaManual();
  function f1(n) { return n.toFixed(1).replace(".", ","); }
  function lectura() {
    var c = calcular(), el = $("#lectura"); if (!el) return;
    el.innerHTML = c ? item("Longitud total", f1(c.largo) + " cm") + item("Ángulo (eje X)", f1(c.ang) + "°") + item("Orientación", ETQ[c.ori].split(" ")[0]) + item("Extensión X", f1(c.ex) + " cm") + item("Extensión Y", f1(c.ey) + " cm") + item("Líneas", c.n)
                     : item("Longitud total", "—") + item("Ángulo (eje X)", "—") + item("Orientación", "—") + item("Puntos marcados", nAnclas());
  }

  // ---------- paso 4: resumen y envío
  function textoSeleccion(name) { var e = form.querySelector('[name="' + name + '"]:checked'); return e ? e.parentElement.textContent.trim().split("\n")[0].trim() : "—"; }
  function resumen() {
    var filas = [["Elemento", textoSeleccion("elemento")], ["Material", textoSeleccion("material")], ["Ancho aproximado", textoSeleccion("ancho_cat").split(/\s{2,}|(?<=[a-z])(?=[<>0-9])/)[0]],
      ["Sismo reciente", val("sismo") === "1" ? "Sí" : "No"], ["Señales de peligro", $$('input[name="senales"]:checked').map(function (x) { return x.parentElement.textContent.trim(); }).join(", ") || "Ninguna"],
      ["Patrón", val("patron") === "cruzada" ? "Grietas cruzadas en X" : "Grieta simple"]];
    if (modo() === "estimado") {
      filas.push(["Medición", "Sin referencia (tamaño aproximado)"], ["Tamaño de la grieta", { corta: "Corta (menos de 30 cm)", media: "Media (30 cm a 1 m)", larga: "Larga (más de 1 m)" }[val("largo_cat")]], ["Orientación", ETQ[val("eje_est")]],
        ["Aviso", "Sin referencia el resultado tendrá confianza baja."]);
    } else if (modo() === "manual") {
      var xy = manualXY(), lg = Math.hypot(xy.x, xy.y), an = Math.atan2(xy.y, xy.x) * 180 / Math.PI;
      filas.push(["Medición", "Ingresada a mano"], ["Longitud en eje X", f1(xy.x) + " cm"], ["Longitud en eje Y", f1(xy.y) + " cm"], ["Longitud total", f1(lg) + " cm"], ["Orientación", ETQ[orient(an)]]);
    } else {
      var c = calcular(); filas.push(["Medición", "Trazo calibrado sobre la foto"]);
      if (c) filas.push(["Longitud estimada", f1(c.largo) + " cm"], ["Orientación estimada", ETQ[c.ori] + " · " + f1(c.ang) + "°"], ["Líneas marcadas", c.n]);
      avisosRef().forEach(function (t) { filas.push(["Aviso", t]); });
    }
    $("#resumen").innerHTML = filas.map(function (f) { var ancho = f[0] === "Aviso" || f[0] === "Señales de peligro"; return '<div class="an-row' + (ancho ? " an-row-wide" : "") + '"><dt>' + esc(f[0]) + '</dt><dd class="mono">' + esc(f[1]) + "</dd></div>"; }).join("");
  }
  function esc(s) { return String(s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }

  function datos() {
    var d = { elemento: val("elemento"), material: val("material") || "nosabe", ancho_cat: val("ancho_cat") || "nosabe", sismo_reciente: val("sismo") === "1",
      senales: $$('input[name="senales"]:checked').map(function (x) { return x.value; }), patron: val("patron") || "simple",
      grupo_uso: $("#grupo_uso").value, anio: $("#anio").value, consentimiento: $("#consentimiento").checked };
    d.ubicacion = $("#ubicacion").value;
    if (modo() === "estimado") d.medicion = { modo: "estimado", largo_cat: val("largo_cat"), eje: val("eje_est") };
    else if (modo() === "manual") {
      var xy = manualXY(); d.medicion = { modo: "manual", x_cm: xy.x, y_cm: xy.y };
    } else d.medicion = { modo: "trazo", trazos: enviarLineas(), ref: ref, ref_mm: refMm(), ref_origen: refOrigen || undefined };
    if (previo) d[previo.modo === "remedir" ? "remedir_de" : "otra_de"] = previo.id;
    return d;
  }

  // Consola de escaneo: la secuencia es visual; la redirección real ocurre cuando responde el servidor.
  var ovTimers = [], ovT0 = 0;
  var OV_LOG = [[100, "Inicializando motor de visión por computador (OpenCV)...", 12], [400, "Cargando matriz de calibración espacial y objeto de referencia...", 30],
    [800, "Extrayendo contornos de fisura en ejes X/Y...", 52], [1300, "Cruzando datos métricos con normativa NSR-10 / ACI 274R...", 72], [1900, "Generando dictamen preliminar y asignando semáforo de riesgo...", 90]];
  function ovTiempo() { var t = (Date.now() - ovT0) / 1000; return "[" + (t < 10 ? "0" : "") + t.toFixed(1) + "s]"; }
  function ovLinea(txt, ok) {
    var term = $("#ov-term"), d = document.createElement("p"); d.textContent = "> " + ovTiempo() + " " + txt; if (ok) d.className = "ok";
    term.appendChild(d); while (term.children.length > 7) term.removeChild(term.firstChild);
  }
  function ovProgreso(n) { $("#ov-bar").style.width = n + "%"; $("#ov-pct").textContent = Math.round(n) + "%"; }
  function ovLimpiar() { ovTimers.forEach(clearTimeout); ovTimers = []; }
  function overlay(on) {
    var o = $("#overlay"); o.hidden = !on; document.body.style.overflow = on ? "hidden" : "";
    ovLimpiar(); $("#ov-term").textContent = ""; ovProgreso(0);
    if (!on) return;
    ovT0 = Date.now();
    OV_LOG.forEach(function (f) { ovTimers.push(setTimeout(function () { ovLinea(f[1]); ovProgreso(f[2]); }, f[0])); });
  }
  function overlayFin(cb) {   // el servidor respondió: completa la barra y redirige sin saltos
    ovLimpiar(); ovLinea("¡Análisis completado con éxito. Redirigiendo a resultados...", true); ovProgreso(100);
    setTimeout(cb, 650);
  }

  $("#enviar").addEventListener("click", function () {
    var b = this; error(4, ""); b.disabled = true; overlay(true);
    if (navigator.onLine === false) { guardarSinConexion(b); return; }
    var fd = new FormData(); fd.append("imagen", blob, "grieta.jpg"); fd.append("datos", JSON.stringify(datos()));
    var minimo = new Promise(function (r) { setTimeout(r, 2200); });   // deja ver la animación aunque la respuesta sea rápida
    var ctl = new AbortController(), t = setTimeout(function () { ctl.abort(); }, 60000);
    var req = fetch("/api/v1/analyses", { method: "POST", body: fd, headers: { "X-CSRF-Token": csrf }, credentials: "same-origin", signal: ctl.signal })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok) { var er = new Error(j.error || (r.status === 429 ? "Demasiados intentos. Espera unos minutos." : r.status === 401 ? "Tu sesión expiró. Vuelve a ingresar." : "No se pudo completar el análisis.")); er.repetir = !!j.repetir_foto; throw er; }
        return j; }); });
    Promise.all([req, minimo]).then(function (x) { overlayFin(function () { window.location.href = x[0].url; }); })
      .catch(function (e) {
        if (e.name !== "AbortError" && e.message === "Failed to fetch") { guardarSinConexion(b); return; }
        overlay(false); b.disabled = false;
        if (e.repetir) { mostrar(2); error(2, e.message); fotoBloqueo = ""; return; }      // foto inservible: a repetirla
        error(4, e.name === "AbortError" ? "El análisis tardó demasiado. Intenta de nuevo." : e.message);
      })
      .finally(function () { clearTimeout(t); });
  });

  // ---------- «Medir de nuevo» / «Otra grieta del mismo caso»: se cargan los datos del análisis anterior
  var previo = null;
  try { previo = $("#wizard").dataset.previo ? JSON.parse($("#wizard").dataset.previo) : null; } catch (e) { previo = null; }
  if (previo && previo.entrada) {
    var pe = previo.entrada, marcar = function (n, v) { var i = form.querySelector('[name="' + n + '"][value="' + CSS.escape(String(v)) + '"]'); if (i) i.checked = true; };
    ["elemento", "material", "ancho_cat", "patron"].forEach(function (n) { if (pe[n]) marcar(n, pe[n]); });
    marcar("sismo", pe.sismo_reciente ? "1" : "0");
    (pe.senales || []).forEach(function (v) { marcar("senales", v); });
    if (window.marcarOpciones) window.marcarOpciones();
    if (pe.grupo_uso) $("#grupo_uso").value = pe.grupo_uso; if (pe.anio) $("#anio").value = pe.anio; if (pe.ubicacion) $("#ubicacion").value = pe.ubicacion;
  }

  // ---------- sin conexión
  function avisoConexion() { $("#aviso-offline").hidden = navigator.onLine !== false; }
  window.addEventListener("online", avisoConexion); window.addEventListener("offline", avisoConexion); avisoConexion();
  function guardarSinConexion(b) {
    if (!window.SismoOffline) { overlay(false); b.disabled = false; error(4, "Sin conexión. Revisa tu internet e intenta de nuevo."); return; }
    window.SismoOffline.guardar(datos(), blob).then(function () {
      overlay(false); b.hidden = true; $$("[data-prev]", $('[data-step="4"]')).forEach(function (x) { x.hidden = true; });
      var ok = $("#ok-4"); ok.hidden = false;
    }).catch(function () { overlay(false); b.disabled = false; error(4, "No se pudo guardar en este dispositivo. Revisa tu internet e intenta de nuevo."); });
  }

  mostrar(1);
})();
