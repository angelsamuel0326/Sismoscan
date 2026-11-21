"""Hoja de validación del semáforo con 50 escenarios escritos (sin fotos).
  python tools/validacion_escenarios.py generar [carpeta]      -> hoja_docente.xlsx (a ciegas) y clave_app.csv (lo que responde la app)
  python tools/validacion_escenarios.py comparar hoja_llena.xlsx -> compara la respuesta del docente con la app
  Agregue --hoja=2 para la segunda hoja (otros 50 escenarios).
El docente marca VERDE / AMARILLO / ROJO en cada fila sin ver la respuesta de la app."""
import csv, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from sismoscan.analysis import rules                      # noqa: E402
from sismoscan.analysis.geometry import desde_manual      # noqa: E402

ANCHO_TXT = {"fina": "fina, como un cabello (< 0,3 mm)", "media": "media (0,3 a 1 mm)", "ancha": "ancha (1 a 3 mm)", "muyancha": "muy ancha (> 3 mm)"}
EL_TXT = {"muro": "Muro", "columna": "Columna", "viga": "Viga", "losa": "Losa o techo"}
MAT_TXT = {"concreto": "concreto reforzado", "mamposteria": "mampostería"}
SEN_TXT = {"inclinacion": "elemento visiblemente inclinado", "concreto_desprendido": "se desprende concreto o revoque", "varilla_expuesta": "se ve la varilla",
           "ruidos": "se oyen crujidos", "puertas_atascadas": "puertas atascadas"}
ORI_TXT = {"horizontal": "horizontal", "vertical": "vertical", "diagonal": "diagonal"}

# (elemento, material, ancho, largo_cm, orientación, sismo reciente, señales, cruzada)
E = [
    # --- anclas claras (para calibrar al docente) ---
    ("muro", "mamposteria", "fina", 8, "vertical", 0, [], 0), ("muro", "concreto", "fina", 15, "horizontal", 0, [], 0),
    ("losa", "concreto", "fina", 10, "horizontal", 0, [], 0), ("columna", "concreto", "muyancha", 80, "vertical", 1, ["varilla_expuesta"], 0),
    ("viga", "concreto", "muyancha", 60, "diagonal", 1, ["concreto_desprendido"], 0), ("muro", "mamposteria", "ancha", 150, "diagonal", 1, ["inclinacion"], 0),
    # --- ancho ---
    ("muro", "mamposteria", "media", 20, "vertical", 0, [], 0), ("muro", "mamposteria", "ancha", 20, "vertical", 0, [], 0),
    ("muro", "concreto", "muyancha", 20, "vertical", 0, [], 0), ("losa", "concreto", "media", 30, "horizontal", 0, [], 0),
    ("losa", "concreto", "ancha", 30, "horizontal", 0, [], 0), ("viga", "concreto", "fina", 30, "horizontal", 0, [], 0),
    ("viga", "concreto", "media", 30, "horizontal", 0, [], 0), ("viga", "concreto", "ancha", 30, "vertical", 0, [], 0),
    # --- largo (la misma grieta fina, cada vez más larga) ---
    ("muro", "mamposteria", "fina", 25, "vertical", 0, [], 0), ("muro", "mamposteria", "fina", 35, "vertical", 0, [], 0),
    ("muro", "mamposteria", "fina", 60, "vertical", 0, [], 0), ("muro", "mamposteria", "fina", 120, "vertical", 0, [], 0),
    ("muro", "mamposteria", "fina", 200, "horizontal", 0, [], 0), ("muro", "mamposteria", "media", 60, "horizontal", 0, [], 0),
    ("muro", "mamposteria", "media", 120, "vertical", 0, [], 0), ("muro", "mamposteria", "media", 250, "horizontal", 0, [], 0),
    # --- orientación (diagonal y en X) ---
    ("muro", "mamposteria", "fina", 30, "diagonal", 0, [], 0), ("muro", "mamposteria", "media", 30, "diagonal", 0, [], 0),
    ("muro", "mamposteria", "ancha", 30, "diagonal", 0, [], 0), ("muro", "mamposteria", "fina", 40, "diagonal", 1, [], 0),
    ("muro", "mamposteria", "media", 40, "diagonal", 1, [], 0), ("muro", "mamposteria", "fina", 40, "vertical", 0, [], 1),
    ("muro", "mamposteria", "media", 40, "vertical", 0, [], 1), ("columna", "concreto", "fina", 30, "diagonal", 0, [], 0),
    ("columna", "concreto", "media", 30, "diagonal", 0, [], 0), ("viga", "concreto", "fina", 30, "diagonal", 0, [], 0),
    ("viga", "concreto", "media", 40, "diagonal", 0, [], 1),
    # --- elemento (misma grieta en distintos elementos) ---
    ("columna", "concreto", "fina", 25, "vertical", 0, [], 0), ("columna", "concreto", "media", 25, "vertical", 0, [], 0),
    ("columna", "concreto", "ancha", 25, "vertical", 0, [], 0), ("losa", "concreto", "fina", 60, "diagonal", 0, [], 0),
    ("losa", "concreto", "media", 60, "diagonal", 0, [], 0),
    # --- sismo reciente y señales ---
    ("muro", "mamposteria", "fina", 20, "vertical", 1, [], 0), ("muro", "mamposteria", "media", 20, "vertical", 1, [], 0),
    ("muro", "mamposteria", "fina", 20, "vertical", 0, ["ruidos"], 0), ("muro", "mamposteria", "fina", 20, "vertical", 0, ["puertas_atascadas"], 0),
    ("muro", "mamposteria", "media", 20, "vertical", 0, ["ruidos", "puertas_atascadas"], 0), ("muro", "mamposteria", "fina", 20, "vertical", 0, ["concreto_desprendido"], 0),
    ("columna", "concreto", "fina", 20, "vertical", 0, ["concreto_desprendido"], 0), ("columna", "concreto", "fina", 20, "vertical", 0, ["varilla_expuesta"], 0),
    ("muro", "mamposteria", "fina", 20, "vertical", 0, ["inclinacion"], 0), ("losa", "concreto", "media", 40, "horizontal", 1, ["ruidos"], 0),
    ("viga", "concreto", "ancha", 50, "diagonal", 1, [], 0), ("muro", "mamposteria", "ancha", 60, "horizontal", 0, [], 0),
]
assert len(E) == 50, len(E)


def _hoja2():
    """Segunda hoja: 50 escenarios DISTINTOS a la primera, por muestreo estratificado con semilla fija (reproducible)."""
    import random
    r = random.Random(2026); clave = lambda e: (*e[:6], tuple(e[6]), e[7]); vistos = {clave(e) for e in E}; out = []
    els = ["muro", "muro", "muro", "columna", "viga", "losa"]; anchos = ["fina"] * 5 + ["media"] * 3 + ["ancha"] * 2 + ["muyancha"]
    largos = [8, 10, 12, 15, 18, 20, 22, 25, 28] * 2 + [32, 38, 45, 55, 70, 90, 120, 180]; oris = ["horizontal", "vertical", "diagonal"]
    sens = [[]] * 12 + [["ruidos"], ["puertas_atascadas"], ["concreto_desprendido"], ["ruidos", "puertas_atascadas"], ["inclinacion"], ["varilla_expuesta"]]
    while len(out) < 50:
        el = r.choice(els); mat = "mamposteria" if el == "muro" and r.random() < .6 else "concreto"
        e = (el, mat, r.choice(anchos), r.choice(largos), r.choice(oris), int(r.random() < .1), r.choice(sens), int(r.random() < .06))
        if clave(e) in vistos: continue
        vistos.add(clave(e)); out.append(e)
    return out


SETS = {1: E, 2: _hoja2()}


def evaluar(e):
    el, mat, ancho, cm, ori, sis, sen, cruz = e
    ctx = dict(elemento=el, material=mat, sismo_reciente=bool(sis), senales=sen, ancho_cat=ancho, patron="cruzada" if cruz else "simple", grupo_uso="I", anio="nosabe")
    r = rules.evaluar(ctx, desde_manual(cm, ori), None, {})
    return r["semaforo"], r["indice"]


def describir(e):
    el, mat, ancho, cm, ori, sis, sen, cruz = e
    s = [f"{EL_TXT[el]} de {MAT_TXT[mat]}", f"grieta {ANCHO_TXT[ancho]}", f"largo {cm} cm" if cm < 100 else f"largo {cm / 100:.1f} m".replace(".", ","), f"orientación {ORI_TXT[ori]}"]
    s.append("hubo un sismo reciente" if sis else "sin sismo reciente")
    if cruz: s.append("otra grieta la cruza formando una X")
    s.append("; ".join(SEN_TXT[x] for x in sen) if sen else "sin otras señales")
    return ". ".join(x[0].upper() + x[1:] for x in s) + "."


def generar(carpeta=".", n=1):
    E = SETS[n]; sufijo = "" if n == 1 else f"_{n}"
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
    from openpyxl.worksheet.datavalidation import DataValidation
    os.makedirs(carpeta, exist_ok=True)
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Escenarios"
    ws["A1"] = f"Validación del semáforo de SismoScan: 50 escenarios (sin fotos){' · hoja ' + str(n) if n != 1 else ''}"; ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = ("Instrucción: para cada caso marque el color que usted daría a una vivienda con esa grieta, pensando con criterio conservador de seguridad "
                "(VERDE = uso normal con monitoreo · AMARILLO = uso restringido y revisión profesional · ROJO = no habitar, evacuar y revisión urgente). "
                "Elija en la columna «Su criterio» y, si quiere, escriba un comentario. Las medidas se suponen reales.")
    ws["A2"].alignment = Alignment(wrap_text=True, vertical="top"); ws.merge_cells("A2:E2"); ws.row_dimensions[2].height = 62
    ws["A3"] = "Evaluador (nombre y cargo): ______________________________________    Fecha: ____________"; ws["A3"].font = Font(bold=True); ws.merge_cells("A3:E3")
    enc = ["N.º", "Escenario", "Su criterio", "Comentario (opcional)", "Confianza (alta / media / baja)"]
    for c, t in enumerate(enc, 1):
        x = ws.cell(row=5, column=c, value=t); x.font = Font(bold=True, color="FFFFFF"); x.fill = PatternFill("solid", fgColor="1F3A5F"); x.alignment = Alignment(wrap_text=True, vertical="center")
    borde = Border(*(Side(style="thin", color="BBBBBB"),) * 4)
    dv = DataValidation(type="list", formula1='"VERDE,AMARILLO,ROJO"', allow_blank=True); ws.add_data_validation(dv)
    dv2 = DataValidation(type="list", formula1='"alta,media,baja"', allow_blank=True); ws.add_data_validation(dv2)
    for i, e in enumerate(E, 1):
        r = 5 + i
        ws.cell(row=r, column=1, value=i); ws.cell(row=r, column=2, value=describir(e)).alignment = Alignment(wrap_text=True, vertical="top")
        for c in range(1, 6): ws.cell(row=r, column=c).border = borde
        dv.add(ws.cell(row=r, column=3)); dv2.add(ws.cell(row=r, column=5)); ws.row_dimensions[r].height = 48
    for col, ancho in zip("ABCDE", (6, 78, 16, 40, 18)): ws.column_dimensions[col].width = ancho
    ws.freeze_panes = "A6"; ws.page_setup.orientation = "landscape"; ws.page_setup.fitToWidth = 1; ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True; ws.print_title_rows = "5:5"
    wb.save(os.path.join(carpeta, f"hoja_docente{sufijo}.xlsx"))
    with open(os.path.join(carpeta, f"clave_app{sufijo}.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n"); w.writerow(["n", "escenario", "app_semaforo", "app_indice"])
        for i, e in enumerate(E, 1):
            s, ind = evaluar(e); w.writerow([i, describir(e), s, ind])
    print("Listo:", carpeta)


def comparar(ruta, n=1):
    E = SETS[n]
    import openpyxl
    ws = openpyxl.load_workbook(ruta, data_only=True).active
    ORD = {"verde": 0, "amarillo": 1, "rojo": 2}
    filas, malas = [], []
    for i, e in enumerate(E, 1):
        doc = (ws.cell(row=5 + i, column=3).value or "").strip().lower()
        if doc not in ORD: continue
        app, ind = evaluar(e); filas.append((i, doc, app, ind))
    if not filas: print("La hoja no tiene respuestas."); return
    exacto = sum(d == a for _, d, a, _ in filas)
    sub = [f for f in filas if ORD[f[2]] < ORD[f[1]]]; sobre = [f for f in filas if ORD[f[2]] > ORD[f[1]]]
    print(f"Respondidos: {len(filas)} · coinciden exacto: {exacto} ({100 * exacto / len(filas):.0f} %) · app MENOS grave que el docente (subestima): {len(sub)} · app MÁS grave (prudente): {len(sobre)}")
    for tag, lista in (("SUBESTIMA", sub), ("SOBREESTIMA", sobre)):
        for i, d, a, ind in lista: print(f"  {tag} #{i}: docente={d} app={a} ({ind}) → {describir(E[i - 1])}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--hoja=")]
    n = next((int(a.split("=")[1]) for a in sys.argv[1:] if a.startswith("--hoja=")), 1)
    if args and args[0] == "comparar": comparar(args[1], n)
    else: generar(args[1] if len(args) > 1 else ".", n)
