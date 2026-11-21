"""Detección local de grietas con visión clásica (OpenCV): no requiere internet ni claves.

Método: realce de contraste (CLAHE) → "black-hat" morfológico (resalta estructuras oscuras y delgadas) → umbral de Otsu
→ componentes conectados alargados → esqueleto morfológico → longitud, ángulo (ajuste de recta), ancho (transformada de
distancia) y patrón cruzado. Si el usuario trazó la grieta, solo se consideran componentes cercanos al trazo
(refinamiento); el objeto de referencia se excluye de la máscara.
"""
import math

import cv2
import numpy as np

LADO_ANALISIS = 900
FACTOR_8CONEXO = 1.1      # un píxel de esqueleto 8-conexo equivale en promedio a ~1,1 px de longitud real


def _esqueleto(mask: np.ndarray) -> np.ndarray:
    skel = np.zeros_like(mask)
    el = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    work = mask.copy()
    for _ in range(400):
        er = cv2.erode(work, el)
        skel = cv2.bitwise_or(skel, cv2.subtract(work, cv2.dilate(er, el)))
        work = er
        if not cv2.countNonZero(work):
            break
    return skel


def _angulo(puntos: np.ndarray) -> float:
    vx, vy, _, _ = cv2.fitLine(puntos.astype(np.float32), cv2.DIST_L2, 0, 0.01, 0.01).ravel()
    return math.degrees(math.atan2(abs(vy), abs(vx)))


def _crestas_oscuras(gris: np.ndarray, diag: float):
    """Filtro de crestas por la matriz Hessiana en varias escalas (tipo Frangi): responde a líneas OSCURAS (finas o anchas)
    y casi no responde a escalones de brillo (bordes), sombras suaves ni superficies planas.
    Devuelve (respuesta uint8, máscara binaria)."""
    g = gris.astype(np.float32) / 255.0
    resp = np.zeros_like(g)
    for frac in (0.0025, 0.005, 0.010):
        sg = max(1.5, diag * frac)
        gs = cv2.GaussianBlur(g, (0, 0), sg)
        hxx = cv2.Sobel(gs, cv2.CV_32F, 2, 0, ksize=3); hyy = cv2.Sobel(gs, cv2.CV_32F, 0, 2, ksize=3); hxy = cv2.Sobel(gs, cv2.CV_32F, 1, 1, ksize=3)
        tr = (hxx + hyy) / 2.0; df = np.sqrt(((hxx - hyy) / 2.0) ** 2 + hxy ** 2)
        l1, l2 = tr + df, tr - df                           # l1 ≥ l2; cresta oscura: l1 grande y positivo, |l2| pequeño
        lin = np.where(l1 > 0, l1 - np.abs(l2) * 0.6, 0.0)
        resp = np.maximum(resp, np.maximum(lin, 0) * sg ** 2)
    r8 = np.clip(resp * 255, 0, 255).astype(np.uint8)          # escala ABSOLUTA: una pared lisa no genera "grietas"
    alto = max(float(np.percentile(r8, 97)), 115.0); bajo = max(float(np.percentile(r8, 93)), 50.0)   # solo el ~3–7 % más "lineal" de la imagen
    fuerte = (r8 >= alto).astype(np.uint8); debil = (r8 >= bajo).astype(np.uint8)
    n, lab = cv2.connectedComponents(debil, connectivity=8)
    ok = np.unique(lab[fuerte > 0]); mask = np.isin(lab, ok[ok > 0]).astype(np.uint8) * 255   # histéresis
    return r8, mask


def _rectitud(pts, l1) -> float:
    """Desviación media respecto a la recta ajustada, relativa a la extensión (0 = recta perfecta)."""
    vx, vy, x0, y0 = cv2.fitLine(pts.astype(np.float32), cv2.DIST_L2, 0, 0.01, 0.01).ravel()
    perp = np.abs((pts[:, 0] - x0) * vy - (pts[:, 1] - y0) * vx)
    return float(np.sqrt(np.mean(perp ** 2))) / max(3.5 * l1, 1)


def _pegada_al_borde(xs, ys, w, h) -> bool:
    """Marcos, bordes de la foto y franjas negras: tocan el borde de la imagen y son delgados."""
    m = 0.02
    ancho_c, alto_c = xs.max() - xs.min() + 1, ys.max() - ys.min() + 1
    delgado = min(ancho_c / w, alto_c / h) < 0.04
    return delgado and (xs.min() < m * w or xs.max() > (1 - m) * w or ys.min() < m * h or ys.max() > (1 - m) * h)


def _es_borde_o_cable(pts, l1, diag, w, h) -> bool:
    """Una grieta es irregular; el borde de un muro, un cable o el marco de una ventana son rectas casi perfectas y de grosor
    uniforme. Una grieta recta pero que se abre y se cierra NO se descarta."""
    vx, vy, x0, y0 = cv2.fitLine(pts.astype(np.float32), cv2.DIST_L2, 0, 0.01, 0.01).ravel()
    perp = np.abs((pts[:, 0] - x0) * vy - (pts[:, 1] - y0) * vx)
    ratio = float(np.sqrt(np.mean(perp ** 2))) / max(3.5 * l1, 1)
    if ratio >= 0.012:
        return False
    if ratio < 0.003:
        return True
    xs, ys = pts[:, 0].astype(int), pts[:, 1].astype(int)
    m = np.zeros((ys.max() - ys.min() + 2, xs.max() - xs.min() + 2), np.uint8); m[ys - ys.min() + 1, xs - xs.min() + 1] = 255
    sk = _esqueleto(m); anchos = 2 * cv2.distanceTransform(m, cv2.DIST_L2, 3)[sk > 0]
    return len(anchos) >= 10 and float(np.std(anchos) / (np.mean(anchos) + 1e-6)) < 0.18


def _es_textura(mask_comp, xs, ys, extension) -> bool:
    """Granos y rugosidad del revoque: manchas compactas y enredadas, no una línea."""
    ancho_caja = xs.max() - xs.min() + 1; alto_caja = ys.max() - ys.min() + 1
    relleno = len(xs) / float(ancho_caja * alto_caja)
    return relleno > 0.35 and max(ancho_caja, alto_caja) < 0.2 * 1000


def detectar(bgr: np.ndarray, trazo_norm=None, ref_norm=None, px_por_mm_orig=None) -> dict:
    h0, w0 = bgr.shape[:2]
    esc = min(1.0, LADO_ANALISIS / max(h0, w0))
    img = cv2.resize(bgr, None, fx=esc, fy=esc, interpolation=cv2.INTER_AREA) if esc < 1 else bgr.copy()
    h, w = img.shape[:2]
    diag = math.hypot(w, h)

    gris = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    gris = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gris)
    bh, mask = _crestas_oscuras(gris, diag)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))

    pt = lambda p: (int(p[0] * w), int(p[1] * h))
    if ref_norm:                                           # excluir el objeto de referencia
        a, b = pt(ref_norm[0]), pt(ref_norm[1])
        m = int(diag * 0.05)
        cv2.rectangle(mask, (min(a[0], b[0]) - m, min(a[1], b[1]) - m), (max(a[0], b[0]) + m, max(a[1], b[1]) + m), 0, -1)
    buf = None
    if trazo_norm:
        buf = np.zeros((h, w), np.uint8)
        lineas = trazo_norm if isinstance(trazo_norm[0][0], (list, tuple)) else [trazo_norm]   # una o varias líneas
        for L in lineas:
            cv2.polylines(buf, [np.array([pt(p) for p in L], np.int32)], False, 255, max(9, int(diag * 0.05)))

    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    cand = []
    for i in range(1, n):
        area = stats[i, cv2.CC_STAT_AREA]
        if area < 0.00025 * w * h:
            continue
        ys, xs = np.nonzero(labels == i)
        pts = np.column_stack([xs, ys]).astype(np.float64)
        ev = np.linalg.eigvalsh(np.cov((pts - pts.mean(0)).T))
        l1, l2 = math.sqrt(max(ev[1], 1e-9)), math.sqrt(max(ev[0], 1e-9))
        extension = 3.5 * l1
        if l1 / l2 < 3 or extension < 0.04 * diag:
            continue
        if buf is not None:
            solape = np.count_nonzero(buf[ys, xs]) / len(xs)
            if solape < 0.25:
                continue
        else:                                                # sin trazo del usuario: descartar lo que no se parece a una grieta
            if _es_borde_o_cable(pts, l1, diag, w, h) or _es_textura(mask_comp=None, xs=xs, ys=ys, extension=extension) or _pegada_al_borde(xs, ys, w, h):
                continue
        cand.append({"i": i, "ext": extension, "xs": xs, "ys": ys, "rect": _rectitud(pts, l1)})
    resultado = {"detectada": False, "componentes": 0}
    if not cand:
        return resultado
    if buf is None:                                          # sin trazo: una grieta es irregular; las juntas y aleros rectos solo valen si no hay otra cosa
        irregulares = [c for c in cand if c["rect"] >= 0.007]
        if irregulares:
            cand = irregulares
    cand.sort(key=lambda c: -c["ext"])
    elegidos = cand[:4] if buf is not None else [c for c in cand if c["ext"] >= 0.5 * cand[0]["ext"]][:3]
    sel = np.zeros((h, w), np.uint8)
    for c in elegidos:
        sel[c["ys"], c["xs"]] = 255
    skel = _esqueleto(sel)
    sy, sx = np.nonzero(skel)
    if len(sx) < 10:
        return resultado
    dt = cv2.distanceTransform(sel, cv2.DIST_L2, 3)
    ancho_px = max(1.0, float(np.median(2 * dt[skel > 0])) - 1.0)
    # longitud ≈ área / ancho (más estable que contar el esqueleto, que genera ramas espurias en trazos gruesos)
    largo_px = min(cv2.countNonZero(sel) / ancho_px, len(sx) * FACTOR_8CONEXO)
    ang = _angulo(np.column_stack([sx, sy]))

    cruzada = False
    if len(elegidos) >= 2:
        angs = []
        for c in elegidos:
            if c["ext"] >= 0.08 * diag:
                angs.append((_angulo(np.column_stack([c["xs"], c["ys"]])), c))
        for ia in range(len(angs)):
            for ib in range(ia + 1, len(angs)):
                (a1, c1), (a2, c2) = angs[ia], angs[ib]
                if abs(a1 - a2) > 35:
                    m1 = np.zeros((h, w), np.uint8); m1[c1["ys"], c1["xs"]] = 255
                    m2 = np.zeros((h, w), np.uint8); m2[c2["ys"], c2["xs"]] = 255
                    if cv2.countNonZero(cv2.bitwise_and(cv2.dilate(m1, np.ones((7, 7), np.uint8)), m2)):
                        cruzada = True

    contraste = float(bh[skel > 0].mean() / (bh.mean() + 1e-6))
    elong = elegidos[0]["ext"] / max(ancho_px, 1)
    confianza = round(min(1.0, max(0.0, (contraste - 1) / 6)) * 0.6 + min(elong / 40, 1) * 0.4, 2)

    # superposición para mostrar al usuario qué detectó el sistema
    ov = img.copy()
    ov[cv2.dilate(skel, np.ones((3, 3), np.uint8)) > 0] = (40, 40, 255)
    if ov.shape[1] > 640:
        ov = cv2.resize(ov, (640, int(ov.shape[0] * 640 / ov.shape[1])), interpolation=cv2.INTER_AREA)
    ok, png = cv2.imencode(".png", ov)

    k_orig = 1.0 / (px_por_mm_orig * esc) if px_por_mm_orig else None   # mm por px de la imagen de análisis
    resultado.update({"detectada": True, "componentes": len(elegidos), "angulo_deg": round(ang, 1), "cruzada": cruzada,
                      "largo_px": round(largo_px, 1), "ancho_px": round(ancho_px, 2), "confianza": confianza,
                      "overlay_png": png.tobytes() if ok else None})
    if k_orig:
        resultado["largo_mm"] = round(largo_px * k_orig, 1)
        resultado["ancho_mm"] = round(ancho_px * k_orig, 2)
    return resultado
