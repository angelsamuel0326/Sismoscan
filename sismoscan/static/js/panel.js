(function () {
  var pill = document.querySelector('[data-pill-verif]');
  if (!pill) return;
  try { if (sessionStorage.getItem('pill-verif') === '1') pill.hidden = true; } catch (e) {}
  var x = pill.querySelector('[data-pill-cerrar]');
  if (x) x.addEventListener('click', function () {
    pill.hidden = true;
    try { sessionStorage.setItem('pill-verif', '1'); } catch (e) {}
  });
})();

// Zoom de la evidencia (resultado): toca para ampliar y mueve el cursor para recorrer la imagen.
(function () {
  var z = document.querySelector("[data-zoom]"); if (!z) return;
  z.addEventListener("click", function () { z.classList.toggle("is-zoom"); });
  z.addEventListener("mousemove", function (e) {
    if (!z.classList.contains("is-zoom")) return;
    var r = z.getBoundingClientRect();
    Array.prototype.forEach.call(z.querySelectorAll("img"), function (im) { im.style.transformOrigin = ((e.clientX - r.left) / r.width * 100) + "% " + ((e.clientY - r.top) / r.height * 100) + "%"; });
  });
})();
