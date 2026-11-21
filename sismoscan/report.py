"""Informe técnico preliminar en PDF (ReportLab). Una sola función pública: generar_pdf()."""
import io
from xml.sax.saxutils import escape

from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .analysis import rules

MARCA = colors.HexColor("#0f6b6b")
TINTA = colors.HexColor("#1b2a2f")
GRIS = colors.HexColor("#5b6b70")
LINEA = colors.HexColor("#d5dde0")
FONDO = colors.HexColor("#f3f6f6")
SEM = {"verde": (colors.HexColor("#047857"), colors.HexColor("#d1fae5"), "VERDE · USO SIN RESTRICCIONES"),
       "amarillo": (colors.HexColor("#b45309"), colors.HexColor("#fef3c7"), "AMARILLO · USO RESTRINGIDO"),
       "rojo": (colors.HexColor("#b91c1c"), colors.HexColor("#fee2e2"), "ROJO · RIESGO SEVERO / PELIGRO DE COLAPSO")}
_SUST = {"≥": ">=", "≤": "<=", "→": "->", "≈": "~", "−": "-", "√": "raiz ", "²": "2", "⚠️": "", "⚠": ""}   # fuera de la codificación del PDF


def _t(texto) -> str:
    """Texto seguro para Paragraph: sin caracteres no soportados y con el marcado escapado."""
    s = str(texto)
    for a, b in _SUST.items():
        s = s.replace(a, b)
    return escape(s)


def _estilos():
    base = getSampleStyleSheet()["BodyText"]
    return {
        "p": ParagraphStyle("p", parent=base, fontName="Helvetica", fontSize=9.5, leading=13.5, textColor=TINTA),
        "peq": ParagraphStyle("peq", parent=base, fontName="Helvetica", fontSize=8, leading=11, textColor=GRIS),
        "h": ParagraphStyle("h", parent=base, fontName="Helvetica-Bold", fontSize=11.5, leading=15, textColor=MARCA, spaceBefore=12, spaceAfter=5, keepWithNext=1),
        "tit": ParagraphStyle("tit", parent=base, fontName="Helvetica-Bold", fontSize=19, leading=23, textColor=TINTA),
        "sem": ParagraphStyle("sem", parent=base, fontName="Helvetica-Bold", fontSize=14, leading=18, alignment=TA_CENTER),
        "celda": ParagraphStyle("celda", parent=base, fontName="Helvetica", fontSize=9, leading=12, textColor=TINTA),
        "celdab": ParagraphStyle("celdab", parent=base, fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=TINTA),
    }


def _tabla(filas, anchos, est, cabecera=False):
    data = [[Paragraph(_t(c), est["celdab"] if (j == 0 and not cabecera) or (cabecera and i == 0) else est["celda"]) for j, c in enumerate(f)] for i, f in enumerate(filas)]
    t = Table(data, colWidths=anchos, hAlign="LEFT")
    estilo = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINEA),
              ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
    if cabecera:
        estilo += [("BACKGROUND", (0, 0), (-1, 0), FONDO)]
    else:
        estilo += [("BACKGROUND", (0, 0), (0, -1), FONDO)]
    t.setStyle(TableStyle(estilo))
    return t


def _barra(indice, color, ancho=17 * cm):
    d = Drawing(ancho, 22)
    d.add(Rect(0, 6, ancho, 9, fillColor=FONDO, strokeColor=LINEA, strokeWidth=0.5))
    d.add(Rect(0, 6, ancho * max(0, min(100, indice)) / 100, 9, fillColor=color, strokeColor=None))
    d.add(String(0, -4, "0", fontSize=7, fillColor=GRIS))
    d.add(String(ancho - 14, -4, "100", fontSize=7, fillColor=GRIS))
    return d


def _imagen(datos: bytes, ancho_max, alto_max):
    w, h = ImageReader(io.BytesIO(datos)).getSize()
    k = min(ancho_max / w, alto_max / h)
    return Image(io.BytesIO(datos), width=w * k, height=h * k)


def generar_pdf(a: dict, miniatura: bytes | None, deteccion: bytes | None, usuario: str, fecha_txt: str,
                serie: list | None = None, emitido_txt: str = "", fecha_fn=None) -> bytes:
    """a: análisis (repo.obtener_analisis). Devuelve los bytes del PDF."""
    est = _estilos()
    r, e = a["resultado"], a["entrada"]
    m = r["medidas"]
    col, claro, etiqueta = SEM[r["semaforo"]]
    W = A4[0] - 4 * cm
    numero = f"SS-{a['id']:06d}"
    cuerpo = []

    cuerpo.append(Paragraph("Informe técnico preliminar", est["tit"]))
    cuerpo.append(Paragraph("Evaluación de grietas en edificaciones · criterios NSR-10 y metodología UNGRD", est["peq"]))
    cuerpo.append(Spacer(1, 8))
    filas_enc = [["Informe No.", numero], ["Fecha y hora del análisis", fecha_txt]]
    if emitido_txt:
        filas_enc.append(["Fecha de emisión del informe", emitido_txt])
    filas_enc += [["Solicitante", usuario], ["Inmueble / ubicación", e.get("ubicacion") or "No indicada (escribir): ______________________________"]]
    cuerpo.append(_tabla(filas_enc, [5.2 * cm, W - 5.2 * cm], est))

    # Semáforo de habitabilidad
    cuerpo.append(Spacer(1, 12))
    caja = Table([[Paragraph(f'<font color="{col.hexval().replace("0x", "#")}">{_t(etiqueta)}</font>', est["sem"])],
                  [Paragraph(_t(r["titulo"]), ParagraphStyle("t2", parent=est["p"], alignment=TA_CENTER, fontName="Helvetica-Bold"))],
                  [Paragraph(f"Decisión preliminar: <b>{_t(r['decision'])}</b> · Índice de severidad: <b>{r['indice']}/100</b> · Confianza del análisis: <b>{r['confianza']['valor']} %</b>",
                             ParagraphStyle("t3", parent=est["peq"], alignment=TA_CENTER))]], colWidths=[W])
    caja.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), claro), ("BOX", (0, 0), (-1, -1), 1.2, col),
                              ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    cuerpo.append(caja)
    cuerpo.append(Spacer(1, 6))
    cuerpo.append(_barra(r["indice"], col, W))
    if r.get("triaje"):
        cuerpo.append(Paragraph(_t(r["triaje"]["titulo"]), est["h"]))
        cuerpo.append(Paragraph(_t(r["triaje"]["texto"]), est["p"]))
        for d in r["disparadores"]:
            cuerpo.append(Paragraph(_t(f"• {d['titulo']}: {d['detalle']} ({d['referencia']})"), est["p"]))
    elif r["criticas"]:
        cuerpo.append(Paragraph("Señales críticas detectadas", est["h"]))
        for c in r["criticas"]:
            cuerpo.append(Paragraph("• " + _t(c), est["p"]))

    # Medidas por eje
    cuerpo.append(Paragraph("1. Dimensiones registradas (ejes X e Y)", est["h"]))
    ori = {"horizontal": "Horizontal (eje X)", "vertical": "Vertical (eje Y)", "diagonal": "Diagonal"}[m["orientacion"]]
    if e.get("patron") == "cruzada":
        ori += " · grietas cruzadas en X"
    em = e["medicion"]
    metodo = ("Trazo calibrado sobre la fotografía" + (" (escala estimada por IA con un objeto de tamaño típico: aproximada)" if em.get("escala_ia") else "")
              if em.get("calibrada") else "Tamaño aproximado por categoría, sin referencia" if em.get("metodo") == "estimado" else "Valores ingresados por el usuario")
    f1 = lambda mm: f"{mm / 10:.1f}".replace(".", ",") + " cm"
    cuerpo.append(_tabla([["Longitud en el eje X (horizontal)", f1(m["ext_x_mm"])], ["Longitud en el eje Y (vertical)", f1(m["ext_y_mm"])],
                          ["Longitud total de la grieta", f1(m["largo_mm"])], ["Ángulo respecto al eje X", f"{m['angulo_deg']:.1f}".replace(".", ",") + "°"],
                          ["Orientación", ori], ["Método de medición", metodo]], [7 * cm, W - 7 * cm], est))

    # Datos del caso
    cuerpo.append(Paragraph("2. Datos del caso", est["h"]))
    senales = ", ".join(rules.SENALES[s] for s in e.get("senales", [])) or "Ninguna"
    cuerpo.append(_tabla([["Elemento", rules.ELEMENTOS[e["elemento"]]], ["Material", rules.MATERIALES.get(e.get("material"), "No sabe")],
                          ["Ancho (declarado)", rules.ANCHOS[e["ancho_cat"]][0]], ["Sismo reciente", "Sí" if e.get("sismo_reciente") else "No"],
                          ["Señales de peligro", senales], ["Grupo de uso", f"{e.get('grupo_uso')} · {rules.GRUPOS_USO.get(e.get('grupo_uso'), '')}"],
                          ["Época de construcción", rules.ANIOS.get(e.get("anio"), "No sabe")]], [5 * cm, W - 5 * cm], est))

    # Evidencia fotográfica
    if miniatura:
        cuerpo.append(Paragraph("3. Evidencia fotográfica", est["h"]))
        celdas, pies = [_imagen(miniatura, 8.2 * cm, 7 * cm)], ["Fotografía analizada"]
        if deteccion:
            celdas.append(_imagen(deteccion, 8.2 * cm, 7 * cm)); pies.append("Grieta detectada por visión por computador (rojo)")
        tf = Table([celdas, [Paragraph(_t(p), est["peq"]) for p in pies]], colWidths=[W / len(celdas)] * len(celdas))
        tf.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (0, 0), (-1, 0), "CENTER")]))
        cuerpo.append(KeepTogether(tf))
        if r.get("vision"):
            v = r["vision"]
            cuerpo.append(Spacer(1, 4))
            cuerpo.append(Paragraph(_t(f"Lectura visual por IA ({v.get('proveedor')}): patrón {v.get('patron')}; desprendimiento: {'sí' if v.get('desprendimiento') else 'no'}; "
                                       f"varilla expuesta: {'sí' if v.get('varilla_expuesta') else 'no'}; inclinación visible: {'sí' if v.get('inclinacion_visible') else 'no'}."), est["peq"]))

    # Factores
    cuerpo.append(Paragraph("4. Cómo se obtuvo el resultado", est["h"]))
    filas = [["Factor", "Puntos", "Detalle"]] + [[f["etiqueta"], f"{f['puntos']}/{f['max']}", f["detalle"]] for f in r["factores"] if f.get("max")]
    cuerpo.append(_tabla(filas, [4.2 * cm, 1.8 * cm, W - 6 * cm], est, cabecera=True))
    cuerpo.append(Paragraph(f"Puntaje acumulado: {r.get('indice_base', r['puntos'])}/100 · Índice final: {r['indice']}/100 · Verde 0–29, amarillo 30–59, rojo 60–100.", est["peq"]))

    # Recomendaciones
    cuerpo.append(Paragraph("5. Recomendaciones de seguridad", est["h"]))
    for i, t in enumerate(r["acciones"], 1):
        cuerpo.append(Paragraph(f"{i}. {_t(t)}", est["p"]))
    if r["semaforo"] == "rojo":
        tels = "; ".join(f"{n}: {t}" for n, t, *_ in rules_emergencias())
        cuerpo.append(Spacer(1, 4)); cuerpo.append(Paragraph(f"<b>Emergencias:</b> {_t(tels)}.", est["p"]))

    cuerpo.append(Paragraph("6. Advertencias y alcance", est["h"]))
    for t in r["advertencias"]:
        cuerpo.append(Paragraph("• " + _t(t), est["p"]))
    cuerpo.append(Paragraph("• Este informe es una orientación preliminar generada automáticamente. No constituye un dictamen técnico ni reemplaza la inspección de un ingeniero civil o estructural con matrícula profesional.", est["p"]))

    n_sec = 7
    if serie and len(serie) > 1 and fecha_fn:
        cuerpo.append(Paragraph("7. Evolución de esta grieta", est["h"]))
        filas = [["Fecha", "Longitud", "Índice", "Semáforo"]] + [
            [fecha_fn(x["creado"]), f"{x['resultado']['medidas']['largo_mm'] / 10:.1f} cm".replace(".", ","), f"{x['resultado']['indice']}/100",
             SEM[x["resultado"]["semaforo"]][2].split(" · ")[0].capitalize()] for x in serie]
        cuerpo.append(_tabla(filas, [W * .34, W * .22, W * .22, W * .22], est, cabecera=True))
        n_sec = 8
    cuerpo.append(Paragraph(f"{n_sec}. Referencias normativas", est["h"]))
    for t, d in rules.REFERENCIAS:
        cuerpo.append(Paragraph(f"<b>{_t(t)}.</b> {_t(d)}", est["peq"]))
        cuerpo.append(Spacer(1, 2))

    # Revisión profesional: espacio para el concepto y la firma del ingeniero que revise
    celda = ParagraphStyle("firma", parent=est["peq"], leading=11)
    firma = Table([[Paragraph("Nombre del ingeniero revisor", celda), "", Paragraph("Matrícula profesional (COPNIA)", celda), ""],
                   [Paragraph("Concepto técnico (confirma / ajusta el resultado)", celda), "", "", ""],
                   [Paragraph("Fecha de la revisión", celda), "", Paragraph("Firma y sello", celda), ""]],
                  colWidths=[4 * cm, W / 2 - 4 * cm, 4 * cm, W / 2 - 4 * cm], rowHeights=[1.1 * cm, 2.6 * cm, 2.2 * cm])
    firma.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), .6, colors.HexColor("#94a3b8")), ("SPAN", (1, 1), (3, 1)), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f5f9")), ("BACKGROUND", (2, 0), (2, 0), colors.HexColor("#f1f5f9")),
                               ("BACKGROUND", (2, 2), (2, 2), colors.HexColor("#f1f5f9"))]))
    cuerpo.append(KeepTogether([Paragraph(f"{n_sec + 1}. Revisión profesional", est["h"]),
                                Paragraph("Este espacio lo diligencia un ingeniero civil o estructural que revise el caso. Sin su firma, el informe es solo una orientación preliminar.", est["peq"]),
                                Spacer(1, 4), firma]))

    buf = io.BytesIO()

    def logo(canvas, x, y, t=1.0 * cm):
        """Marca: cuadro oscuro con borde ámbar y una grieta ámbar en zigzag (dibujada, sin archivos de imagen)."""
        canvas.setFillColor(colors.HexColor("#0f172a")); canvas.setStrokeColor(colors.HexColor("#f59e0b")); canvas.setLineWidth(.8)
        canvas.roundRect(x, y, t, t, .22 * cm, stroke=1, fill=1)
        canvas.setStrokeColor(colors.HexColor("#fbbf24")); canvas.setLineWidth(1.6); canvas.setLineJoin(1)
        p = canvas.beginPath(); p.moveTo(x + .5 * t, y + .88 * t); p.lineTo(x + .38 * t, y + .62 * t); p.lineTo(x + .6 * t, y + .46 * t); p.lineTo(x + .44 * t, y + .14 * t)
        canvas.drawPath(p, stroke=1, fill=0)

    def marco(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(colors.HexColor("#0f172a")); canvas.rect(0, A4[1] - 1.5 * cm, A4[0], 1.5 * cm, stroke=0, fill=1)
        logo(canvas, 2 * cm, A4[1] - 1.25 * cm, 1.0 * cm)
        canvas.setFillColor(colors.white); canvas.setFont("Helvetica-Bold", 13); canvas.drawString(3.25 * cm, A4[1] - 1 * cm, "Sismo")
        canvas.setFillColor(colors.HexColor("#fbbf24")); canvas.drawString(3.25 * cm + canvas.stringWidth("Sismo", "Helvetica-Bold", 13), A4[1] - 1 * cm, "Scan"); canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica", 8.5); canvas.drawRightString(A4[0] - 2 * cm, A4[1] - 1 * cm, f"Informe {numero} · Proyecto de Introducción a la Ingeniería · ODS 9")
        canvas.setFillColor(GRIS); canvas.setFont("Helvetica", 7.5)
        canvas.drawString(2 * cm, 1.1 * cm, "Orientación preliminar. No reemplaza la evaluación de un ingeniero civil o estructural.")
        canvas.drawRightString(A4[0] - 2 * cm, 1.1 * cm, f"Página {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2.4 * cm, bottomMargin=1.8 * cm,
                            title=f"Informe técnico preliminar {numero}", author="SismoScan", subject="Evaluación preliminar de grietas")
    doc.build(cuerpo, onFirstPage=marco, onLaterPages=marco)
    return buf.getvalue()


def rules_emergencias():
    from flask import current_app
    return current_app.config.get("EMERGENCY_NUMBERS", [])[:4]
