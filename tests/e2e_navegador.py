"""Prueba de navegador (Playwright). Uso: python tests/e2e_navegador.py [carpeta_capturas]
Levanta la app, recorre registro → panel → cuenta → historial/comparar y falla si hay errores de consola/CSP."""
import os, re, subprocess, sys, tempfile, time
from pathlib import Path
from playwright.sync_api import sync_playwright

RAIZ = Path(__file__).resolve().parent.parent; SHOTS = Path(sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp()); SHOTS.mkdir(exist_ok=True, parents=True)
PORT = 50877; BASE = f"http://127.0.0.1:{PORT}"
env = dict(os.environ, DATABASE_PATH=tempfile.mktemp(), RATELIMIT_ENABLED="0", VISION_PROVIDER="local", PORT=str(PORT))
srv = subprocess.Popen([sys.executable, "-c", f"from sismoscan import create_app; create_app().run(port={PORT})"], cwd=RAIZ, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
errores = []
try:
    for _ in range(50):
        try: import urllib.request; urllib.request.urlopen(BASE + "/healthz"); break
        except Exception: time.sleep(.2)
    with sync_playwright() as p:
        b = p.chromium.launch(); cx = b.new_context(viewport={"width": 1280, "height": 900}); cx.route("**/fonts.*/**", lambda r: r.abort())
        pg = cx.new_page()
        pg.on("console", lambda m: errores.append(m.text) if m.type == "error" and "ERR_FAILED" not in m.text and "fonts" not in m.text else None)
        pg.on("pageerror", lambda e: errores.append(str(e)))
        pg.goto(BASE + "/registro"); pg.fill("#clave", "Tx9#mQv27pLw"); pg.wait_for_function("document.getElementById('fuerza-texto').textContent !== '—'")
        fuerza = pg.inner_text("#fuerza-texto"); assert fuerza in ("Buena", "Excelente"), fuerza
        pg.fill("#nombre", "Ana Test"); pg.fill("#correo", "ana@test.co"); pg.fill("#clave2", "Tx9#mQv27pLw"); pg.check("[name=acepto]"); pg.screenshot(path=SHOTS / "registro.png")
        pg.click("button.btn-primary"); pg.wait_for_url("**/panel")
        assert "Verifica tu correo" in pg.content()
        pg.screenshot(path=SHOTS / "panel.png", full_page=True)
        for ruta in ("/cuenta", "/acerca", "/ayuda", "/privacidad", "/terminos", "/historial"):
            pg.goto(BASE + ruta); assert pg.locator("footer").count() == 1; pg.screenshot(path=SHOTS / (ruta.strip("/") + ".png"), full_page=True)
        pg.set_viewport_size({"width": 390, "height": 800}); pg.goto(BASE + "/cuenta"); pg.screenshot(path=SHOTS / "cuenta_movil.png", full_page=True)
        assert pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), "scroll horizontal en móvil"
        b.close()
finally:
    srv.terminate()
assert not errores, errores
print("E2E OK", SHOTS)
