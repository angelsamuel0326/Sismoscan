"""Geometría de la grieta: longitud, extensión en ejes X/Y y orientación, a partir de un trazo sobre la foto
(con un objeto de referencia de tamaño conocido) o de valores ingresados a mano."""
import math

UMBRAL_EJE = 15.0                       # <=15° horizontal (eje X) · >=75° vertical (eje Y) · en medio diagonal
ANGULO_POR_EJE = {"horizontal": 0.0, "vertical": 90.0, "diagonal": 45.0}


class GeometriaInvalida(ValueError):
    pass


def orientacion(angulo: float) -> str:
    if angulo <= UMBRAL_EJE:
        return "horizontal"
    if angulo >= 90 - UMBRAL_EJE:
        return "vertical"
    return "diagonal"


def _num(v, nombre, lo, hi):
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise GeometriaInvalida(f"{nombre} no es un número válido.")
    if not math.isfinite(x) or not lo <= x <= hi:
        raise GeometriaInvalida(f"{nombre} debe estar entre {lo:g} y {hi:g}.")
    return x


def _pares(lista, nombre, minimo, maximo):
    if not isinstance(lista, list) or not minimo <= len(lista) <= maximo:
        raise GeometriaInvalida(f"{nombre}: se esperaban entre {minimo} y {maximo} puntos.")
    out = []
    for p in lista:
        if not (isinstance(p, (list, tuple)) and len(p) == 2):
            raise GeometriaInvalida(f"{nombre}: formato de punto inválido.")
        out.append((_num(p[0], nombre, 0, 1), _num(p[1], nombre, 0, 1)))
    return out


def _eje_principal(lineas_mm):
    """Ángulo (0–90°) del eje principal de TODA la grieta (PCA de los puntos, ponderado por longitud).
    Representa mejor a una grieta en zigzag o ramificada que mirar solo el inicio y el final."""
    pts = []
    for L in lineas_mm:
        for a, b in zip(L, L[1:]):
            n = max(1, int(math.dist(a, b) // 2))
            pts += [(a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n) for i in range(n + 1)]
    if len(pts) < 2:
        return 0.0
    mx, my = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
    sxx = sum((p[0] - mx) ** 2 for p in pts); syy = sum((p[1] - my) ** 2 for p in pts); sxy = sum((p[0] - mx) * (p[1] - my) for p in pts)
    ang = 0.5 * math.atan2(2 * sxy, sxx - syy)           # dirección principal en [-90°, 90°]
    return abs(math.degrees(ang)) if abs(math.degrees(ang)) <= 90 else 90.0


def _resumen(lineas_mm, metodo, px_por_mm=None, avisos=None):
    largo = sum(math.dist(a, b) for L in lineas_mm for a, b in zip(L, L[1:]))
    if largo < 1:
        raise GeometriaInvalida("El trazo es demasiado corto.")
    xs = [p[0] for L in lineas_mm for p in L]; ys = [p[1] for L in lineas_mm for p in L]
    dx, dy = max(xs) - min(xs), max(ys) - min(ys)
    ang = _eje_principal(lineas_mm)
    avisos = list(avisos or [])
    diag = math.hypot(dx, dy)
    if len(lineas_mm) == 1 and diag > 0 and largo > 2.5 * diag:
        avisos.append(f"El largo trazado ({largo / 10:.0f} cm) es mucho mayor que el espacio que ocupa la grieta ({diag / 10:.0f} cm): "
                      "hay trazos que se devuelven o se cruzan. Revisa que cada línea siga la grieta una sola vez.")
    return {"metodo": metodo, "largo_mm": round(largo, 1), "ext_x_mm": round(dx, 1), "ext_y_mm": round(dy, 1),
            "angulo_deg": round(ang, 1), "orientacion": orientacion(ang), "px_por_mm": px_por_mm,
            "n_lineas": len(lineas_mm), "avisos": avisos}


def avisos_referencia(ref, lineas, ancho_px, alto_px, ref_mm=None):
    """Señales de que el objeto de referencia pudo marcarse mal (p. ej. se marcó la grieta en vez de la tarjeta)."""
    out = []
    d_ref = math.dist((ref[0][0] * ancho_px, ref[0][1] * alto_px), (ref[1][0] * ancho_px, ref[1][1] * alto_px))
    lado = max(ancho_px, alto_px)
    ref_mm_aprox = None
    if d_ref > 0.4 * lado and ref_mm is not None and ref_mm <= 300:
        out.append(f"La referencia ocupa el {d_ref / lado * 100:.0f} % de la foto pero dijiste que mide solo {ref_mm / 10:g} cm. "
                   "¿Seguro que es una tarjeta o una regla? Si marcaste algo más grande (una puerta, un marco), escribe su medida real "
                   "o usa un objeto pequeño pegado junto a la grieta.")
    if d_ref > 0.6 * lado:
        out.append(f"La referencia ocupa el {d_ref / lado * 100:.0f} % de la foto: es muy grande para una tarjeta o regla. "
                   "Si marcaste la grieta o una pared en lugar del objeto, las medidas saldrán erradas.")
    # ¿la referencia coincide con la grieta? (puntos de la referencia pegados a la línea de la grieta y de largo parecido)
    pts = [p for L in lineas for p in L]
    def dist_a_trazo(p):
        return min(math.dist((p[0] * ancho_px, p[1] * alto_px), (q[0] * ancho_px, q[1] * alto_px)) for q in pts)
    if pts and all(dist_a_trazo(p) < 0.03 * lado for p in ref):
        out.append("Los puntos de la referencia están sobre la grieta. La referencia debe ser un objeto de medida conocida "
                   "(tarjeta, regla, moneda) puesto junto a la grieta, no la grieta misma.")
    return out


def desde_trazos(trazos_norm, ref_norm, ref_mm, ancho_px: int, alto_px: int) -> dict:
    """Una o varias líneas (coordenadas normalizadas 0-1) → milímetros reales usando el objeto de referencia.
    Longitud = suma de todas las líneas; extensiones X/Y = caja que las contiene; ángulo = eje principal."""
    if not isinstance(trazos_norm, list) or not 1 <= len(trazos_norm) <= 8:
        raise GeometriaInvalida("trazo: se esperaban entre 1 y 8 líneas.")
    lineas = [_pares(t, "trazo", 2, 400) for t in trazos_norm]
    if sum(len(t) for t in lineas) > 1600:
        raise GeometriaInvalida("trazo: demasiados puntos.")
    ref = _pares(ref_norm, "referencia", 2, 2)
    ref_mm = _num(ref_mm, "medida de referencia (mm)", 5, 5000)
    px = lambda p: (p[0] * ancho_px, p[1] * alto_px)
    d_ref = math.dist(px(ref[0]), px(ref[1]))
    if d_ref < 10:
        raise GeometriaInvalida("Los dos puntos de la referencia están demasiado juntos.")
    k = d_ref / ref_mm                                   # px por mm
    mm = [[(px(p)[0] / k, px(p)[1] / k) for p in L] for L in lineas]
    return _resumen(mm, "trazo", round(k, 4), avisos_referencia(ref, lineas, ancho_px, alto_px, ref_mm))


def desde_trazo(trazo_norm, ref_norm, ref_mm, ancho_px: int, alto_px: int) -> dict:
    return desde_trazos([trazo_norm], ref_norm, ref_mm, ancho_px, alto_px)


def desde_manual(largo_cm=None, eje=None, angulo=None, x_cm=None, y_cm=None) -> dict:
    """Medidas escritas a mano. Dos formas:
    · Ejes: longitud proyectada en X (horizontal) y en Y (vertical) → longitud = √(x²+y²), ángulo = atan2(y, x).
    · Longitud total + orientación (horizontal / vertical / diagonal) y ángulo opcional."""
    if x_cm not in (None, "") or y_cm not in (None, ""):
        x = _num(x_cm if x_cm not in (None, "") else 0, "longitud en el eje X (cm)", 0, 2000) * 10.0
        y = _num(y_cm if y_cm not in (None, "") else 0, "longitud en el eje Y (cm)", 0, 2000) * 10.0
        if x == 0 and y == 0:
            raise GeometriaInvalida("Ingresa la longitud en el eje X, en el eje Y o en ambos.")
        largo = math.hypot(x, y)
        ang = math.degrees(math.atan2(y, x))
        return {"metodo": "manual", "largo_mm": round(largo, 1), "ext_x_mm": round(x, 1), "ext_y_mm": round(y, 1),
                "angulo_deg": round(ang, 1), "orientacion": orientacion(ang), "px_por_mm": None, "n_lineas": 1, "avisos": []}
    largo = _num(largo_cm, "longitud (cm)", 0.1, 2000) * 10.0
    if eje not in ANGULO_POR_EJE:
        raise GeometriaInvalida("Orientación inválida (horizontal, vertical o diagonal).")
    ang = ANGULO_POR_EJE[eje] if angulo in (None, "") else _num(angulo, "ángulo", 0, 90)
    r = math.radians(ang)
    return {"metodo": "manual", "largo_mm": round(largo, 1), "ext_x_mm": round(largo * math.cos(r), 1),
            "ext_y_mm": round(largo * math.sin(r), 1), "angulo_deg": round(ang, 1),
            "orientacion": orientacion(ang), "px_por_mm": None, "n_lineas": 1, "avisos": []}


# Longitudes representativas para el modo «sin referencia» (el usuario solo elige una categoría de tamaño).
LARGOS_ESTIMADOS = {"corta": 20.0, "media": 60.0, "larga": 150.0}      # cm


def desde_estimado(largo_cat=None, eje=None, angulo=None) -> dict:
    """Sin objeto de referencia: tamaño por categoría (corta < 30 cm · media 30–100 cm · larga > 1 m) y orientación elegida."""
    if largo_cat not in LARGOS_ESTIMADOS:
        raise GeometriaInvalida("Elige el tamaño aproximado de la grieta (corta, media o larga).")
    m = desde_manual(LARGOS_ESTIMADOS[largo_cat], eje, angulo)
    m["metodo"] = "estimado"
    m["avisos"] = ["Sin objeto de referencia: la longitud es una categoría aproximada elegida por ti, no una medida."]
    return m
