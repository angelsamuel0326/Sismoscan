/* Aplica el tema antes de pintar para evitar el parpadeo. Archivo externo por la CSP (sin scripts en línea). */
(function () {
  try {
    var t = localStorage.getItem("ss-tema");
    var oscuro = t ? t === "oscuro" : true; /* modo oscuro por defecto */
    document.documentElement.classList.toggle("dark", oscuro);
  } catch (e) {}
})();
