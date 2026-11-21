/* Service worker de SismoScan.
 * - Precarga el "app shell" estático (CSS, JS, iconos, página sin conexión).
 * - Archivos estáticos: caché primero, con actualización en segundo plano.
 * - Navegaciones: red primero; si no hay conexión, página /offline.
 * - NUNCA cachea /api/ ni páginas con datos del usuario. Única excepción: el formulario /analizar (sin fotos ni resultados),
 *   para poder prepararlo sin conexión; se borra al cerrar sesión. */
self.addEventListener("message", (e) => { if (e.data === "limpiar-paginas") caches.keys().then((ks) => ks.filter((k) => k.startsWith("sismoscan-paginas-")).forEach((k) => caches.delete(k))); });
const VERSION = "v18zoc";
const CACHE = "sismoscan-" + VERSION;
const PAGINAS = "sismoscan-paginas-" + VERSION;      // solo el formulario /analizar (sin fotos ni resultados)
const SHELL = ["/offline", "/static/css/app.css", "/static/css/auth.css", "/static/css/panel.css", "/static/css/analizar.css", "/static/css/resultado.css", "/static/css/historial.css", "/static/css/metodologia.css", "/static/css/marca.css", "/static/css/chatbot.css", "/static/js/chatbot.js", "/static/js/panel.js", "/static/js/theme-init.js", "/static/js/ui.js", "/static/js/emergencia.js", "/static/js/analizar.js", "/static/js/chat.js", "/static/js/offline.js",
  "/static/img/isotipo.svg", "/static/img/logo.svg", "/static/icons/icon-192.png", "/static/icons/icon-512.png", "/static/icons/apple-touch-icon.png", "/manifest.json"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => Promise.all(SHELL.map((u) => c.add(u).catch(() => {})))).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k.startsWith("sismoscan-") && k !== CACHE && k !== PAGINAS).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const req = e.request, url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/imagenes/") || url.pathname.startsWith("/c/") || url.pathname.endsWith(".pdf")) return;   // datos privados: siempre red

  if (req.mode === "navigate" && url.pathname === "/analizar") {
    // Red primero; si no hay conexión se abre la última copia del formulario para poder preparar el análisis y guardarlo en el celular.
    e.respondWith(fetch(req).then((r) => {
      if (r.ok && !r.redirected) { const copia = r.clone(); caches.open(PAGINAS).then((c) => c.put("/analizar", copia)); }
      return r;
    }).catch(async () => (await caches.match("/analizar")) || caches.match("/offline")));
    return;
  }
  if (req.mode === "navigate") {
    e.respondWith(fetch(req).catch(() => caches.match("/offline")));
    return;
  }
  if (url.pathname.startsWith("/static/") || url.pathname === "/manifest.json") {
    e.respondWith(caches.open(CACHE).then(async (c) => {
      const hit = await c.match(req);
      const red = fetch(req).then((r) => { if (r.ok) c.put(req, r.clone()); return r; }).catch(() => hit);
      return hit || red;
    }));
  }
});
