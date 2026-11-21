"""Evalúa SismoScan contra un banco de fotos etiquetadas (tests/banco/banco.csv).

Uso:  python tools/evaluar_banco.py [carpeta_banco]      (por defecto tests/banco)

Mide dos cosas, por separado y con honestidad sobre sus límites:
  A) DETECCIÓN LOCAL (OpenCV) en el PEOR CASO, sin trazo del usuario (en la app solo se usa con trazo):
     ¿encuentra la grieta cuando la hay?, ¿no inventa una cuando no la hay?,
     ¿su orientación (horizontal/vertical/diagonal) coincide con la esperada?
  B) SEMÁFORO: ¿la salida del motor de reglas coincide con la etiqueta esperada (verde/amarillo/rojo)?
     Las medidas x_cm/y_cm del CSV son SUPUESTOS cuando la foto no tiene escala; el contexto (elemento, ancho, señales)
     lo escribe el evaluador. Es una prueba de consistencia de las reglas frente al criterio de quien etiqueta, no una
     validación estructural independiente: las etiquetas deben ser confirmadas por un ingeniero.
Genera resultados.csv y resultados.md en la carpeta del banco.
"""
import csv, json, os, sys, tempfile
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("RATELIMIT_ENABLED", "0")
from sismoscan import create_app                      # noqa: E402
from sismoscan.analysis import images, pipeline        # noqa: E402
from sismoscan.analysis.geometry import orientacion    # noqa: E402
from sismoscan.analysis.vision.opencv_provider import detectar  # noqa: E402

NIVELES = ["verde", "amarillo", "rojo"]
# Controles difíciles: el usuario (o un error) traza SOBRE una línea que no es grieta (un cable, el borde de un marco).
# Coordenadas normalizadas de esa línea en las imágenes sintéticas.
TRAZOS_ENGANO = {"n04.jpg": [[0.089, 0.214], [0.911, 0.600]], "n06.jpg": [[0.278, 0.171], [0.278, 0.743]]}


def main(carpeta):
    app = create_app({"DATABASE_PATH": tempfile.mktemp(), "TESTING": True, "RATELIMIT_ENABLED": False, "VISION_PROVIDER": "local"})
    filas = [f for f in csv.DictReader(open(os.path.join(carpeta, "banco.csv"), encoding="utf-8")) if f["incluir"] == "si"]
    out = []
    for f in filas:
        datos_img = open(os.path.join(carpeta, f["archivo"]), "rb").read()
        r = {"archivo": f["archivo"], "esperado": f["esperado"], "hay_grieta": f["hay_grieta"], "orient_esperada": f["orient_esperada"]}
        # A) detección local directa sobre la imagen
        img = images.preparar(datos_img, app.config["MAX_IMAGE_SIDE"], app.config["THUMB_SIDE"])
        d = detectar(img.bgr, None, None, None)
        r["detectada"] = "si" if d.get("detectada") else "no"
        ang = d.get("angulo_deg")
        r["angulo_detectado"] = "" if ang is None or not d.get("detectada") else round(ang, 1)
        r["orient_detectada"] = orientacion(ang) if (d.get("detectada") and ang is not None) else ""
        # B) semáforo con el pipeline completo
        if f["esperado"] in NIVELES:
            datos = {"elemento": f["elemento"], "material": f["material"], "ancho_cat": f["ancho_cat"], "patron": f["patron"],
                     "sismo_reciente": f["sismo_reciente"] == "si", "senales": [s for s in f["senales"].split(",") if s],
                     "grupo_uso": "I", "anio": "nosabe", "consentimiento": True,
                     "medicion": {"modo": "manual", "x_cm": float(f["x_cm"]), "y_cm": float(f["y_cm"])}}
            with app.app_context():
                res = pipeline.analizar(app.config, datos, datos_img)["resultado"]
            r.update(obtenido=res["semaforo"], indice=res["indice"], puntos=res["puntos"], criticas="; ".join(res["criticas"]))
        else:
            r.update(obtenido="", indice="", puntos="", criticas="")
        out.append(r)

    # ---------- métricas ----------
    sem = [r for r in out if r["esperado"] in NIVELES]
    exactos = sum(r["obtenido"] == r["esperado"] for r in sem)
    cerca = sum(abs(NIVELES.index(r["obtenido"]) - NIVELES.index(r["esperado"])) <= 1 for r in sem)
    subest = [r for r in sem if NIVELES.index(r["obtenido"]) < NIVELES.index(r["esperado"])]
    sub_graves = [r for r in subest if r["esperado"] == "rojo"]
    sobre = [r for r in sem if NIVELES.index(r["obtenido"]) > NIVELES.index(r["esperado"])]
    conf = {(e, o): 0 for e in NIVELES for o in NIVELES}
    for r in sem:
        conf[(r["esperado"], r["obtenido"])] += 1

    con = [r for r in out if r["hay_grieta"] == "si"]
    sin = [r for r in out if r["hay_grieta"] == "no" and r["esperado"] == "sin_grieta"]
    det_ok = sum(r["detectada"] == "si" for r in con)
    falsos = [r for r in sin if r["detectada"] == "si"]
    oc = [r for r in con if r["orient_esperada"] in ("horizontal", "vertical", "diagonal") and r["detectada"] == "si"]
    ori_ok = sum(r["orient_detectada"] == r["orient_esperada"] for r in oc)

    # C) trazo del usuario sobre una línea que NO es grieta: ¿la detección local la «confirma»?
    enganos = []
    for r in out:
        if r["archivo"] in TRAZOS_ENGANO:
            img = images.preparar(open(os.path.join(carpeta, r["archivo"]), "rb").read(), 1600, 640)
            d = detectar(img.bgr, [TRAZOS_ENGANO[r["archivo"]]], [[0.1, 0.9], [0.2, 0.9]], 5.0)
            enganos.append((r["archivo"], bool(d.get("detectada"))))
    L = []
    p = L.append
    p("# Resultados de la evaluación con banco de imágenes\n")
    p(f"Imágenes evaluadas: {len(out)} (semáforo: {len(sem)} · con grieta: {len(con)} · controles sin grieta: {len(sin)}).\n")
    p("## A. Detección local (OpenCV) · peor caso: foto libre, sin trazo del usuario\n")
    p(f"- Grietas detectadas: {det_ok}/{len(con)} ({100*det_ok/max(1,len(con)):.0f} %).")
    p(f"- Falsos positivos en controles sin grieta: {len(falsos)}/{len(sin)}" + (f" ({', '.join(r['archivo'] for r in falsos)})." if falsos else "."))
    p(f"- Orientación correcta (entre las detectadas con orientación esperada definida): {ori_ok}/{len(oc)} ({100*ori_ok/max(1,len(oc)):.0f} %).\n")
    p("## A2. Trazo del usuario sobre algo que NO es grieta (cable, marco)\n")
    p(f"- La detección local «confirma» una falsa grieta en {sum(d for _, d in enganos)}/{len(enganos)} casos ({', '.join(a for a, d in enganos if d) or 'ninguno'})."
      " Límite conocido: no distingue una grieta de otra línea oscura; por eso la app exige que el usuario marque la grieta y confirme el resultado.\n")
    p("## B. Semáforo (motor de reglas)\n")
    p(f"- Coincidencia exacta: {exactos}/{len(sem)} ({100*exactos/max(1,len(sem)):.0f} %).")
    p(f"- Dentro de ±1 nivel: {cerca}/{len(sem)} ({100*cerca/max(1,len(sem)):.0f} %).")
    p(f"- Subestimaciones (resultado menos grave que el esperado): {len(subest)}; de ellas, casos esperados en rojo: {len(sub_graves)}.")
    p(f"- Sobreestimaciones (más grave que el esperado): {len(sobre)}.\n")
    p("Matriz de confusión (filas = esperado, columnas = obtenido):\n")
    p("| Esperado \\ Obtenido | Verde | Amarillo | Rojo |\n|---|---|---|---|")
    for e in NIVELES:
        p(f"| {e.capitalize()} | " + " | ".join(str(conf[(e, o)]) for o in NIVELES) + " |")
    p("\n## Detalle por imagen\n")
    p("| Img | Esperado | Obtenido | Índice | Detectada | Orient. esperada | Orient. detectada |\n|---|---|---|---|---|---|---|")
    for r in out:
        p(f"| {r['archivo']} | {r['esperado']} | {r['obtenido'] or '—'} | {r['indice'] if r['indice'] != '' else '—'} | {r['detectada']} | {r['orient_esperada']} | {r['orient_detectada'] or '—'} |")
    p("\n> Las etiquetas esperadas son un criterio visual preliminar y las medidas sin escala son supuestos: los porcentajes indican consistencia, no exactitud estructural. Deben validarse con un ingeniero civil o estructural.")
    texto = "\n".join(L)
    open(os.path.join(carpeta, "resultados.md"), "w", encoding="utf-8").write(texto)
    with open(os.path.join(carpeta, "resultados.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)
    resumen = {"imagenes": len(out), "con_grieta": len(con), "controles_sin_grieta": len(sin),
               "deteccion": {"detectadas": det_ok, "de": len(con), "falsos_positivos": len(falsos), "controles": len(sin),
                             "orientacion_ok": ori_ok, "orientacion_de": len(oc)},
               "trazo_sobre_no_grieta": {"confirmadas": sum(d for _, d in enganos), "de": len(enganos)},
               "semaforo": {"exacto": exactos, "dentro_1": cerca, "de": len(sem), "subestimaciones": len(subest),
                            "subestimaciones_graves": len(sub_graves), "sobreestimaciones": len(sobre),
                            "matriz": {e: {o: conf[(e, o)] for o in NIVELES} for e in NIVELES}},
               "nota": "Etiquetas de criterio visual preliminar; sin validar por un ingeniero. Controles negativos: 2 fotos reales + 6 sintéticas."}
    import json as _json
    open(os.path.join(carpeta, "resultados.json"), "w", encoding="utf-8").write(_json.dumps(resumen, ensure_ascii=False, indent=1))
    print(texto)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "tests", "banco"))
