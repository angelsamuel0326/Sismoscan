/* Confirmación antes de llamar: intercepta cualquier [data-llamar] y abre el <dialog> #dlg-llamar.
   Sin JavaScript, el enlace tel: sigue funcionando como respaldo. */
(function () {
  "use strict";
  var dlg = document.getElementById("dlg-llamar"); if (!dlg || !dlg.showModal) return;
  var num = dlg.querySelector("[data-llm-num]"), ok = document.getElementById("llm-ok"), tit = document.getElementById("llm-t"), previo = null;
  document.addEventListener("click", function (e) {
    var a = e.target.closest("[data-llamar]"); if (!a) return;
    e.preventDefault(); previo = a;
    var n = String(a.getAttribute("data-llamar")).replace(/[^0-9+]/g, ""), nombre = a.getAttribute("data-llamar-nombre") || "";
    num.textContent = n; ok.setAttribute("href", "tel:" + n);
    tit.firstChild.textContent = n === "123" || !nombre ? "🚨 ¿Llamar a Emergencias (" : "🚨 ¿Llamar a " + nombre + " (";
    dlg.showModal(); ok.focus();
  });
  Array.prototype.forEach.call(dlg.querySelectorAll("[data-llm-cerrar]"), function (b) { b.addEventListener("click", function () { dlg.close(); }); });
  dlg.addEventListener("click", function (e) { if (e.target === dlg) dlg.close(); });
  ok.addEventListener("click", function () { setTimeout(function () { dlg.close(); }, 300); });
  dlg.addEventListener("close", function () { if (previo && previo.focus) previo.focus(); });
})();
