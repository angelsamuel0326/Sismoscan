"""Prueba de navegador (Playwright) de los flujos nuevos: calidad de foto, sin referencia, medir de nuevo + gráfica y modo sin conexión.
Uso: python tests/e2e_flujos.py [carpeta_capturas]"""
import os, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path
import cv2
from playwright.sync_api import sync_playwright

RAIZ = Path(__file__).resolve().parent.parent
SHOTS = Path(sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp()); SHOTS.mkdir(parents=True, exist_ok=True)
PORT = 50878; BASE = f"http://127.0.0.1:{PORT}"
TMP = Path(tempfile.mkdtemp())
cv2.imwrite(str(TMP / "borrosa.jpg"), cv2.GaussianBlur(cv2.imread(str(RAIZ / "tests" / "pared.jpg")), (0, 0), 25))
BUENA = str(RAIZ / "tests" / "pared.jpg")
env = dict(os.environ, DATABASE_PATH=str(TMP / "e2e.db"), RATELIMIT_ENABLED="0", VISION_PROVIDER="local")
srv = subprocess.Popen([sys.executable, "-c", f"from sismoscan import create_app; create_app().run(port={PORT})"], cwd=RAIZ, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
errores = []


def paso1(pg):
    pg.check("input[name=elemento][value=muro]", force=True); pg.check("input[name=ancho_cat][value=media]", force=True)
    pg.fill("#ubicacion", "Calle 5 #10-20, Cali"); pg.click('[data-step="1"] [data-next]')


def foto(pg, ruta, consent=True):
    pg.set_input_files("#foto-archivo", ruta); pg.wait_for_selector("#vista-foto:not([hidden])"); pg.wait_for_selector("#sugerencia:not([hidden])"); pg.wait_for_timeout(400)
    if consent and not pg.is_checked("#consentimiento"): pg.check("#consentimiento", force=True)


try:
    for _ in range(60):
        try: urllib.request.urlopen(BASE + "/healthz"); break
        except Exception: time.sleep(.2)
    with sync_playwright() as p:
        b = p.chromium.launch(); cx = b.new_context(viewport={"width": 1100, "height": 900}); cx.route("**/fonts.*/**", lambda r: r.abort())
        pg = cx.new_page()
        pg.on("console", lambda m: errores.append(m.text) if m.type == "error" and "ERR_" not in m.text and "fonts" not in m.text and "Failed to load resource" not in m.text else None)
        pg.on("pageerror", lambda e: errores.append(str(e)))
        pg.goto(BASE + "/registro"); pg.fill("#nombre", "Ana E2E"); pg.fill("#correo", "e2e@test.co"); pg.fill("#clave", "Tx9#mQv27pLw"); pg.fill("#clave2", "Tx9#mQv27pLw")
        pg.check("[name=acepto]"); pg.click("button.btn-primary"); pg.wait_for_url("**/panel")

        # 1) foto borrosa: se bloquea con mensaje claro
        pg.goto(BASE + "/analizar"); paso1(pg); foto(pg, str(TMP / "borrosa.jpg"))
        assert "borrosa" in pg.inner_text("#err-2"), pg.inner_text("#err-2")
        pg.click('[data-step="2"] [data-next]'); assert pg.is_visible('[data-step="2"]'), "no debía avanzar con foto borrosa"
        pg.screenshot(path=SHOTS / "1_foto_borrosa.png")
        foto(pg, BUENA); pg.click("#foto-cambiar"); foto(pg, BUENA); assert pg.inner_text("#err-2") == ""
        assert not pg.is_visible("#ia-escala"), "la IA de escala no debe verse sin clave"

        # 2) modo «sin referencia»
        pg.click('[data-step="2"] [data-next]'); pg.wait_for_selector('[data-step="3"]:not([hidden])', timeout=5000); pg.wait_for_timeout(800); pg.check("input[name=modo][value=estimado]", force=True)
        assert pg.is_visible("#panel-estimado") and not pg.is_visible("#panel-trazo")
        pg.click('[data-step="3"] [data-next]'); assert "larga" in pg.inner_text("#err-3")
        pg.check("input[name=largo_cat][value=media]", force=True); pg.check("input[name=eje_est][value=vertical]", force=True)
        pg.screenshot(path=SHOTS / "2_sin_referencia.png", full_page=True)
        pg.click('[data-step="3"] [data-next]'); pg.click("#enviar"); pg.wait_for_url("**/resultados/1")
        assert "categoría aproximada" in pg.content()

        # 3) medir de nuevo -> se precargan los datos; después aparece la gráfica de evolución
        pg.click("text=Medir de nuevo esta grieta"); pg.wait_for_url("**/analizar?remedir=1")
        assert pg.is_checked("input[name=elemento][value=muro]") and pg.input_value("#ubicacion") == "Calle 5 #10-20, Cali"
        pg.click('[data-step="1"] [data-next]'); foto(pg, BUENA); pg.click('[data-step="2"] [data-next]')
        pg.check("input[name=modo][value=manual]", force=True); pg.fill("#x-cm", "5"); pg.fill("#y-cm", "75")
        pg.click('[data-step="3"] [data-next]'); pg.click("#enviar"); pg.wait_for_url("**/resultados/2")
        assert pg.is_visible("#evolucion") and pg.locator("#evolucion polyline").count() == 2
        pg.locator("#evolucion").scroll_into_view_if_needed(); pg.screenshot(path=SHOTS / "3_evolucion.png")
        pg.goto(BASE + "/caso/1"); assert "Grieta 1" in pg.content(); pg.screenshot(path=SHOTS / "3b_caso.png", full_page=True)

        # 4) sin conexión: se guarda en el celular y se envía al volver internet
        pg.goto(BASE + "/analizar"); paso1(pg); foto(pg, BUENA); pg.click('[data-step="2"] [data-next]')
        pg.check("input[name=modo][value=estimado]", force=True); pg.check("input[name=largo_cat][value=larga]", force=True); pg.check("input[name=eje_est][value=diagonal]", force=True)
        pg.click('[data-step="3"] [data-next]')
        cx.set_offline(True); pg.evaluate("window.dispatchEvent(new Event('offline'))")
        pg.click("#enviar"); pg.wait_for_selector("#ok-4:not([hidden])", timeout=8000)
        n = pg.evaluate("window.SismoOffline.pendientes().then(l => l.length)"); assert n == 1, n
        pg.screenshot(path=SHOTS / "4_offline_guardado.png")
        cx.set_offline(False); pg.evaluate("window.dispatchEvent(new Event('online'))")
        for _ in range(40):
            if pg.evaluate("window.SismoOffline.pendientes().then(l => l.length)") == 0: break
            time.sleep(.25)
        assert pg.evaluate("window.SismoOffline.pendientes().then(l => l.length)") == 0, "el pendiente no se envió"
        pg.goto(BASE + "/historial"); assert pg.locator("li[data-sem]").count() == 3, pg.locator("li[data-sem]").count()
        pg.screenshot(path=SHOTS / "5_historial.png", full_page=True)
        b.close()
finally:
    srv.terminate()
assert not errores, errores
print("E2E FLUJOS OK", SHOTS)
