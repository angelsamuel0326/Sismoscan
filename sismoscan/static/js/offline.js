/* Modo sin conexión: guarda los análisis preparados en el celular (IndexedDB) y los envía solos cuando vuelve internet.
 * El análisis lo calcula el servidor, así que sin internet solo se puede capturar y encolar. Cada pendiente guarda el id del
 * usuario: otra cuenta en el mismo dispositivo nunca los envía. Conserva la hora real de la foto (capturado_en). */
(function () {
  "use strict";
  var DB = "sismoscan", STORE = "pendientes";
  var uid = (document.querySelector('meta[name="user-id"]') || {}).content || "";
  var csrf = (document.querySelector('meta[name="csrf-token"]') || {}).content || "";
  var enviando = false;

  function abrir() {
    return new Promise(function (ok, no) {
      if (!window.indexedDB) { no(new Error("sin IndexedDB")); return; }
      var r = indexedDB.open(DB, 1);
      r.onupgradeneeded = function () { r.result.createObjectStore(STORE, { keyPath: "id", autoIncrement: true }); };
      r.onsuccess = function () { ok(r.result); }; r.onerror = function () { no(r.error); };
    });
  }
  function tx(modo, fn) {
    return abrir().then(function (db) {
      return new Promise(function (ok, no) {
        var t = db.transaction(STORE, modo), st = t.objectStore(STORE), res = fn(st);
        t.oncomplete = function () { db.close(); ok(res && res.result !== undefined ? res.result : undefined); };
        t.onerror = t.onabort = function () { db.close(); no(t.error); };
      });
    });
  }
  function propios() { return tx("readonly", function (st) { return st.getAll(); }).then(function (l) { return (l || []).filter(function (x) { return x.uid === uid; }); }); }

  function guardar(datos, blob) {
    var d = JSON.parse(JSON.stringify(datos)); d.capturado_en = new Date().toISOString();
    return tx("readwrite", function (st) { return st.add({ uid: uid, datos: d, blob: blob, creado: Date.now(), error: "" }); }).then(pintar);
  }
  function quitar(id) { return tx("readwrite", function (st) { st.delete(id); }); }
  function marcar(it, msg) { it.error = msg; return tx("readwrite", function (st) { st.put(it); }); }

  function enviarTodos() {
    if (enviando || !uid || navigator.onLine === false) return Promise.resolve(0);
    enviando = true; var enviados = 0;
    return propios().then(function (lista) {
      return lista.filter(function (x) { return !x.error; }).reduce(function (p, it) {
        return p.then(function (seguir) {
          if (!seguir) return false;
          var fd = new FormData(); fd.append("imagen", it.blob, "grieta.jpg"); fd.append("datos", JSON.stringify(it.datos));
          return fetch("/api/v1/analyses", { method: "POST", body: fd, headers: { "X-CSRF-Token": csrf }, credentials: "same-origin" }).then(function (r) {
            if (r.ok) { enviados++; return quitar(it.id).then(function () { return true; }); }
            if (r.status === 400 || r.status === 422) return r.json().catch(function () { return {}; }).then(function (j) { return marcar(it, j.error || "El servidor lo rechazó.").then(function () { return true; }); });
            return false;                                   // sesión vencida (401), límite (429) o error del servidor: se reintenta luego
          }).catch(function () { return false; });
        });
      }, Promise.resolve(true));
    }).then(function () { enviando = false; return pintar().then(function () { return enviados; }); })
      .catch(function () { enviando = false; return 0; });
  }

  function pintar() {
    var caja = document.getElementById("pendientes"); if (!caja || !uid) return Promise.resolve();
    return propios().then(function (l) {
      var ok = l.filter(function (x) { return !x.error; }), mal = l.filter(function (x) { return x.error; });
      caja.hidden = !l.length; if (!l.length) return;
      var t = caja.querySelector("[data-pend-texto]");
      t.textContent = (ok.length ? ok.length + " análisis guardado" + (ok.length > 1 ? "s" : "") + " en este dispositivo, pendiente" + (ok.length > 1 ? "s" : "") + " de enviar. " : "") +
        (mal.length ? mal.length + " con problema: " + mal[0].error + " " : "");
      caja.querySelector("[data-pend-enviar]").hidden = !ok.length;
      caja.querySelector("[data-pend-descartar]").hidden = !mal.length;
    }).catch(function () {});
  }

  window.SismoOffline = { guardar: guardar, enviarTodos: enviarTodos, pendientes: propios };

  document.addEventListener("DOMContentLoaded", function () {
    var caja = document.getElementById("pendientes");
    if (caja) {
      caja.querySelector("[data-pend-enviar]").addEventListener("click", function () { enviarTodos().then(avisarEnviados); });
      caja.querySelector("[data-pend-descartar]").addEventListener("click", function () {
        propios().then(function (l) { return Promise.all(l.filter(function (x) { return x.error; }).map(function (x) { return quitar(x.id); })); }).then(pintar);
      });
    }
    pintar(); enviarTodos().then(avisarEnviados);
  });
  window.addEventListener("online", function () { enviarTodos().then(avisarEnviados); });
  document.addEventListener("submit", function (e) {            // cerrar sesión: no dejar la copia del formulario en el dispositivo
    if (e.target && e.target.getAttribute && /\/salir$/.test(e.target.getAttribute("action") || "")) {
      try { if (navigator.serviceWorker && navigator.serviceWorker.controller) navigator.serviceWorker.controller.postMessage("limpiar-paginas"); } catch (x) {}
    }
  });
  function avisarEnviados(n) {
    if (!n) return;
    var caja = document.getElementById("pendientes"); if (!caja) return;
    caja.hidden = false; caja.querySelector("[data-pend-texto]").innerHTML = "Se enviaron " + n + " análisis. <a class=\"font-semibold underline\" href=\"/historial\">Ver historial</a>";
    caja.querySelector("[data-pend-enviar]").hidden = true; caja.querySelector("[data-pend-descartar]").hidden = true;
  }
})();
