/* Medidor de fuerza de contraseña (registro y restablecer). Solo orienta; el servidor valida las reglas. */
(function () {
  "use strict";
  var i = document.getElementById("clave"), barra = document.getElementById("fuerza-barra"), texto = document.getElementById("fuerza-texto");
  if (!i || !barra) return;
  var NIVELES = [["Muy débil", "#ef4444", 15], ["Débil", "#f97316", 35], ["Aceptable", "#eab308", 60], ["Buena", "#22c55e", 80], ["Excelente", "#14b8a6", 100]];
  function puntaje(v) {
    if (!v) return -1;
    var p = 0;
    if (v.length >= 8) p++; if (v.length >= 12) p++;
    if (/[a-z]/.test(v) && /[A-Z]/.test(v)) p++;
    if (/\d/.test(v)) p++;
    if (/[^A-Za-z0-9]/.test(v)) p++;
    if (/^(.)\1+$/.test(v) || /^(0123|1234|abcd|qwer|pass)/i.test(v)) p = Math.min(p, 1);
    return Math.min(4, Math.max(0, p - (v.length < 8 ? 1 : 0)));
  }
  function pintar() {
    var n = puntaje(i.value);
    if (n < 0) { barra.style.width = "0"; texto.textContent = "—"; return; }
    barra.style.width = NIVELES[n][2] + "%"; barra.style.background = NIVELES[n][1]; texto.textContent = NIVELES[n][0];
  }
  i.addEventListener("input", pintar); pintar();
})();
