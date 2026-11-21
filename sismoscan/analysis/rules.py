"""Motor de reglas: cruza contexto, medidas geométricas y lectura visual para emitir un resultado PRELIMINAR.

Cada factor suma puntos y cita su fundamento. El semáforo (verde / amarillo / rojo) sigue la señalización
de la metodología unificada de evaluación post-sismo de la UNGRD (Circular 73 de 2026).

CALIBRACIÓN (v2): el índice es una suma de factores con pesos que totalizan 100 puntos; el color del semáforo se
deriva SOLO de ese índice (verde 0–29, amarillo 30–59, rojo 60–100), de modo que número y color nunca se contradicen.
PRUDENCIA: ante la duda el sistema sube de nivel, no lo baja (pisos mínimos en amarillo; disparadores en rojo).
Los disparadores críticos (cortante, apertura > 3 mm, acero expuesto, inclinación, desprendimiento en columna o viga)
no cambian la regla: elevan el índice al mínimo de la banda roja (60) y se muestran como «triaje conservador».

AVISO: los pesos y umbrales son criterios de ingeniería de referencia del prototipo. Deben ser validados por un
ingeniero civil/estructural contra la NSR-10 y las guías oficiales antes de cualquier uso real.
El resultado es una orientación, NO un dictamen estructural.
"""
ELEMENTOS = {"muro": "Muro", "columna": "Columna", "viga": "Viga", "losa": "Losa o techo"}
MATERIALES = {"concreto": "Concreto reforzado", "mamposteria": "Mampostería", "nosabe": "No sé"}
GRUPOS_USO = {"I": "Ocupación normal (vivienda, comercio)", "II": "Ocupación especial (colegios, reuniones)",
              "III": "Indispensable (hospitales, emergencias)", "IV": "Atención a la comunidad"}
ANIOS = {"antes1984": "Antes de 1984", "1984_1997": "1984 – 1997", "1998_2010": "1998 – 2010",
         "desde2010": "Desde 2010 (NSR-10)", "nosabe": "No lo sé"}
SENALES = {"inclinacion": "Se ve inclinada la edificación o el elemento (a simple vista)", "concreto_desprendido": "Se desprende concreto o revoque",
           "varilla_expuesta": "Se ve el hierro (varilla)", "ruidos": "Se oyen crujidos",
           "puertas_atascadas": "Puertas o ventanas atascadas"}
ANCHOS = {"fina": ("Fina, como un cabello", "< 0,3 mm", 0.2), "media": ("Media, no entra el borde de una tarjeta", "0,3 – 1 mm", 0.6),
          "ancha": ("Ancha, entra una tarjeta o moneda delgada", "1 – 3 mm", 2.0), "muyancha": ("Muy ancha, entra un lápiz o un dedo", "> 3 mm", 4.0),
          "nosabe": ("No lo sé", "", None)}
PATRONES = ("simple", "cruzada")

REF_ANCHO = "Anchos de grieta tolerables ≈ 0,3–0,4 mm en condiciones normales (guía ACI 224R)"
REF_SISMICO = "NSR-10: columnas y vigas hacen parte del sistema de resistencia sísmica (Título A)"
REF_USO = "NSR-10 A.2.5: grupos de uso I a IV según importancia de la edificación"
REF_ANIO = "Normativa sismorresistente: Decreto 1400/1984, Ley 400/1997 y NSR-98/NSR-10"
REF_UNGRD = "UNGRD, Circular 73 de 2026: semáforo verde, amarillo y rojo"
REFERENCIAS = [
    ("NSR-10", "Reglamento Colombiano de Construcción Sismo Resistente (Ley 400 de 1997, Decreto 926 de 2010). Título A.10: evaluación de edificaciones existentes."),
    ("UNGRD, Circular 73 de 2026", "Metodología unificada de evaluación de edificaciones afectadas por el terremoto: señalización verde, amarillo y rojo."),
    ("ACI 224R", "Control de fisuración en estructuras de concreto: referencia de anchos de grieta tolerables."),
    ("ACI 224.1R", "Causas, evaluación y reparación de grietas en estructuras de concreto: tipos de grieta (flexión, cortante, corrosión) y su gravedad."),
    ("ACI 364.1R", "Guía para la evaluación de estructuras de concreto existentes."),
    ("ATC-20", "Procedimientos de evaluación rápida de seguridad post-sismo (inspeccionado, uso restringido, inseguro)."),
]
# --- Calibración: pesos (suman 100) y bandas del semáforo -------------------------------------------------------
UMBRAL_AMARILLO = 30        # índice ≥ 30 → amarillo
UMBRAL_ROJO = 60            # índice ≥ 60 → rojo (también es el piso cuando se activa un disparador crítico)
BANDAS = {"verde": (0, UMBRAL_AMARILLO - 1), "amarillo": (UMBRAL_AMARILLO, UMBRAL_ROJO - 1), "rojo": (UMBRAL_ROJO, 100)}
PESOS = {"ancho": 30, "orientacion": 25, "longitud": 10, "elemento": 12, "contexto": 10, "exposicion": 8, "vision": 5}
PTS_ANCHO = (0, 8, 18, 30)                      # fina, media, ancha, muy ancha (> 3 mm)
PTS_ELEMENTO = {"muro": 0, "losa": 4, "viga": 7, "columna": 8}
assert sum(PESOS.values()) == 100


def semaforo_de(indice: int) -> str:
    """ÚNICA función que traduce índice → color."""
    return "rojo" if indice >= UMBRAL_ROJO else "amarillo" if indice >= UMBRAL_AMARILLO else "verde"


def _f(clave, etiqueta, puntos, maximo, detalle, ref=""):
    return {"clave": clave, "etiqueta": etiqueta, "puntos": puntos, "max": maximo, "detalle": detalle, "referencia": ref}


def _d(clave, titulo, detalle, ref):
    return {"clave": clave, "titulo": titulo, "detalle": detalle, "referencia": ref}


def evaluar(ctx: dict, med: dict, vision: dict | None = None, extra: dict | None = None) -> dict:
    """ctx: respuestas del usuario · med: medidas (geometry) · vision: lectura semántica de IA (opcional)
    · extra: calidad de la medición (calibrada, concordancia automática, etc.)."""
    vision, extra = vision or {}, extra or {}
    elemento, material = ctx["elemento"], ctx.get("material", "nosabe")
    senales = set(ctx.get("senales") or [])
    ori, ang, largo = med["orientacion"], med["angulo_deg"], med["largo_mm"]
    adv, factores, disparadores = [], [], []

    # --- ancho (usuario; si no sabe, la IA o la detección local con escala) ---
    cat = ctx.get("ancho_cat", "nosabe")
    origen_ancho = "indicado por ti"
    if cat == "nosabe":
        cat, origen_ancho = None, ""
        for fuente, valor in (("estimado por la IA", vision.get("ancho_cat")), ("estimado por la detección local", extra.get("ancho_cat_local"))):
            if valor in ("fina", "media", "ancha", "muyancha"):
                cat, origen_ancho = valor, fuente
                break
        if cat is None:
            cat, origen_ancho = "media", "supuesto"
            adv.append("No se pudo determinar el ancho; se asumió una grieta de ancho medio (0,3–1 mm).")
    pa = ["fina", "media", "ancha", "muyancha"].index(cat)
    factores.append(_f("ancho", "Ancho de la grieta", PTS_ANCHO[pa], PESOS["ancho"], f"{ANCHOS[cat][0]} ({ANCHOS[cat][1]}), {origen_ancho}.", REF_ANCHO))

    # --- orientación respecto a los ejes ---
    patron_ia = vision.get("patron")
    cruzada = ctx.get("patron") == "cruzada" or (patron_ia == "cruzada" and (vision.get("confianza") or 0) >= 0.6) or bool(extra.get("cruzada_local"))
    if cruzada:
        po, det = 25, "Grietas cruzadas en X: patrón típico de cortante cíclico."
    elif ori == "diagonal":
        po, det = 15, f"Diagonal ({ang:.0f}° respecto al eje X): puede indicar esfuerzo cortante."
    else:
        eje = "eje X (horizontal)" if ori == "horizontal" else "eje Y (vertical)"
        po, det = 0, f"Alineada con el {eje} ({ang:.0f}°): menos crítica por su orientación."
    if patron_ia == "mapa" and po < 6:
        po, det = 6, "La IA observa fisuración en mapa (red de grietas finas)."
    factores.append(_f("orientacion", "Orientación (ejes X / Y)", po, PESOS["orientacion"], det, "ACI 224.1R: las grietas diagonales y en X en elementos estructurales suelen asociarse a cortante"))

    # --- longitud ---
    pl = 0 if largo < 300 else 3 if largo < 1000 else 6 if largo < 3000 else 10
    factores.append(_f("longitud", "Longitud", pl, PESOS["longitud"], f"{largo / 10:.1f} cm ({'corta' if pl == 0 else 'media' if pl <= 3 else 'larga' if pl <= 6 else 'muy larga'}).", ""))

    # --- elemento afectado ---
    pe = PTS_ELEMENTO[elemento]
    det = (f"{ELEMENTOS[elemento]}: elemento principal del sistema de resistencia sísmica." if elemento in ("columna", "viga")
           else f"{ELEMENTOS[elemento]}: aporta rigidez y soporta cargas de piso." if elemento == "losa"
           else f"{ELEMENTOS[elemento]}: elemento no principal del sistema sismorresistente.")
    if elemento == "columna" and ori == "horizontal" and pa >= 1:
        pe, det = 12, "Columna con grieta horizontal: posible falla por flexión."
    factores.append(_f("elemento", "Elemento afectado", pe, PESOS["elemento"], det, REF_SISMICO))

    # --- contexto y señales ---
    pc, partes = 0, []
    if ctx.get("sismo_reciente"):
        pc += 4; partes.append("sismo reciente")
    for s, t in (("ruidos", "crujidos"), ("puertas_atascadas", "puertas atascadas")):
        if s in senales:
            pc += 3; partes.append(t)
    factores.append(_f("contexto", "Contexto y señales", pc, PESOS["contexto"], ", ".join(partes).capitalize() + "." if partes else "Sin señales adicionales.", ""))

    # --- exposición (uso y antigüedad) ---
    px_, partes = 0, []
    if ctx.get("grupo_uso") in ("III", "IV"):
        px_ += 4; partes.append(f"grupo de uso {ctx['grupo_uso']} (mayor importancia)")
    if ctx.get("anio") == "antes1984":
        px_ += 4; partes.append("construida antes de la primera norma sismorresistente colombiana (1984)")
    factores.append(_f("exposicion", "Uso y antigüedad", px_, PESOS["exposicion"], ", ".join(partes).capitalize() + "." if partes else "Sin factores agravantes declarados.", REF_USO + "; " + REF_ANIO))

    # --- lectura visual por IA ---
    pv, partes = 0, []
    conf_ia = vision.get("confianza") or 0
    if vision.get("desprendimiento") and conf_ia >= 0.5 and "concreto_desprendido" not in senales:
        pv += 5; partes.append("desprendimiento de material")
    if vision.get("grieta_probable") is False:
        adv.append("La IA no identifica una grieta clara en la foto: revisa el encuadre, la luz y el enfoque.")
    if vision.get("observaciones"):
        partes.append(f"«{vision['observaciones']}»")
    factores.append(_f("vision", "Lectura visual por IA", pv, PESOS["vision"], ("; ".join(partes) + ".") if partes else "Sin hallazgos adicionales o IA externa no configurada.", ""))

    # --- disparadores críticos: elevan el índice al piso de la banda roja ---
    forma = "en X (cruzada)" if cruzada else f"diagonal ({ang:.0f}° respecto al eje X)"
    cortante = (cruzada or ori == "diagonal") and (
        (elemento in ("columna", "viga") and pa >= 1)
        or (cruzada and pa >= 2)
        or (ori == "diagonal" and pa >= 2 and bool(ctx.get("sismo_reciente"))))
    if cortante:
        disparadores.append(_d("cortante", "Alerta de cortante",
                               f"Grieta {forma}, ancho {ANCHOS[cat][1] or cat}, en {ELEMENTOS[elemento].lower()}: patrón compatible con falla por cortante, que es frágil (puede ocurrir sin aviso previo).",
                               "ACI 224.1R; NSR-10 Título C (cortante) y A.10; ATC-20"))
    if pa == 2 and (elemento == "columna" or (elemento == "viga" and largo > 1000)):
        disparadores.append(_d("ancho_estructural", f"Grieta de 1 a 3 mm en {elemento}" + (" y de más de 1 m" if elemento == "viga" else ""),
                               "En un elemento que carga la edificación, una grieta mayor a 1 mm (4 a 10 veces lo tolerable) puede indicar pérdida de capacidad: se trata con criterio conservador.",
                               REF_ANCHO + "; ATC-20"))
    if pa == 3:
        disparadores.append(_d("apertura", "Apertura mayor a 3 mm",
                               "Una abertura de más de 3 mm supera con amplitud el ancho tolerable (≈ 0,3–0,4 mm) e indica daño significativo.",
                               REF_ANCHO + "; ATC-20"))
    if "varilla_expuesta" in senales or (vision.get("varilla_expuesta") and conf_ia >= 0.6):
        disparadores.append(_d("acero", "Acero de refuerzo expuesto", "Se ve la varilla: el concreto perdió recubrimiento y el refuerzo está desprotegido.", "NSR-10 Título C (recubrimientos); ACI 224.1R"))
    if "inclinacion" in senales or (vision.get("inclinacion_visible") and conf_ia >= 0.6):
        disparadores.append(_d("inclinacion", "Edificación o elemento inclinado", "Una inclinación visible sugiere pérdida de verticalidad o asentamiento.", "ATC-20"))
    if "concreto_desprendido" in senales and elemento in ("columna", "viga"):
        disparadores.append(_d("desprendimiento", f"Desprendimiento de concreto en {elemento}", f"Pérdida de material en una {elemento}: puede reducir su capacidad de carga.", "ATC-20; ACI 224.1R"))

    # --- índice, semáforo y triaje (la banda sale SOLO del índice) ---
    base = sum(f["puntos"] for f in factores)
    indice = max(base, UMBRAL_ROJO) if disparadores else base
    semaforo = semaforo_de(indice)
    pisos = []
    if "concreto_desprendido" in senales and elemento not in ("columna", "viga"):
        pisos.append("Se desprende material")
    if (cruzada or ori == "diagonal") and elemento in ("columna", "viga"):
        pisos.append(f"Grieta {'en X' if cruzada else 'diagonal'} en {elemento}: patrón posible de cortante aunque sea fina")
    if largo > 300:
        pisos.append(f"Longitud de {largo / 10:.0f} cm: supera los 30 cm, una fisura superficial rara vez es tan larga")
    # Pisos por prudencia (ante la duda se sube de nivel, nunca se baja): una grieta que ya no es una fisura merece revisión.
    if pa >= 2:
        pisos.append(f"Ancho de {ANCHOS[cat][1]}: supera con amplitud el ancho tolerable (≈ 0,3–0,4 mm)")
    elif pa == 1:
        if elemento in ("columna", "viga"):
            pisos.append(f"Grieta de ancho medio en {elemento}: elemento principal del sistema sismorresistente")
        if ori == "diagonal":
            pisos.append("Grieta diagonal de ancho medio: puede indicar cortante o asentamiento diferencial")
        if largo >= 1000:
            pisos.append(f"Grieta de ancho medio y larga ({largo / 1000:.1f} m)")
    # Señales de movimiento o de sismo reciente: una grieta, por pequeña que sea, no se deja en verde (ATC-20: inspección tras el sismo).
    if ctx.get("sismo_reciente"):
        pisos.append("Hubo un sismo reciente: toda grieta nueva merece inspección profesional")
    if "ruidos" in senales:
        pisos.append("Se oyen crujidos: puede haber movimiento activo")
    if "puertas_atascadas" in senales:
        pisos.append("Puertas o ventanas atascadas: posible deformación o asentamiento")
    if pisos and semaforo == "verde":
        indice = UMBRAL_AMARILLO
        semaforo = semaforo_de(indice)
        factores.append(_f("piso", "Piso mínimo amarillo", 0, 0, "; ".join(pisos) + ": el índice sube al mínimo de la banda amarilla.", ""))
    # Longitud: una grieta de más de 50 cm sube a amarillo alto y la de más de 1,5 m, o larga y ancha/diagonal, a rojo.
    # Nunca puede quedar en verde.
    minimo_largo = 0
    if largo > 1500:
        minimo_largo = UMBRAL_ROJO if (pa >= 1 or ori == "diagonal" or cruzada) else 50
    elif largo > 500:
        minimo_largo = 45
    if minimo_largo > indice:
        factores.append(_f("piso_longitud", "Penalización por longitud", 0, 0,
                           f"Grieta de {largo / 10:.0f} cm: el índice sube al mínimo de {minimo_largo}/100 (más de 50 cm nunca es verde).", ""))
        indice = minimo_largo
        semaforo = semaforo_de(indice)
    ajuste = indice - base

    triaje = None
    if disparadores:
        claves = {d["clave"] for d in disparadores}
        nombre = ("por Alerta de Cortante" if "cortante" in claves else "por Apertura Crítica (> 3 mm)" if "apertura" in claves else "por Señal Estructural Crítica")
        texto = ("Ante una evaluación remota y preliminar, SismoScan aplica un criterio conservador: prefiere una falsa alarma a no detectar un daño grave. "
                 + ("Las grietas diagonales o en X en elementos que resisten cortante pueden preceder a una falla frágil, sin aviso previo. " if "cortante" in claves else "")
                 + f"Puntaje acumulado por factores: {base}/100"
                 + (f"; por el disparador crítico se eleva al mínimo de la banda roja ({UMBRAL_ROJO}/100), un ajuste de +{ajuste}." if ajuste > 0
                    else f", que ya está en la banda roja; el disparador lo confirma.")
                 + " Un ingeniero estructural debe confirmar o descartar el daño.")
        triaje = {"titulo": f"Triaje de Seguridad Conservador {nombre}", "texto": texto, "base": base, "ajuste": ajuste, "final": indice}

    if semaforo == "rojo":
        decision, titulo = "EVACUAR", "Evacuar y pedir inspección profesional urgente"
        acciones = ["Salgan de la edificación con calma, sin usar ascensores y llevando solo lo esencial.",
                    "No regresen hasta que un ingeniero estructural o la autoridad competente lo autorice.",
                    "Llamen a la línea de emergencias 123 o a la oficina de gestión del riesgo de su municipio.",
                    "Alejen a las personas de muros, balcones y fachadas cercanas."]
    elif semaforo == "amarillo":
        if ctx.get("sismo_reciente"):
            decision, titulo = "EVACUAR", "Evacuación preventiva hasta que un profesional evalúe"
        else:
            decision, titulo = "PERMANECER CON RESTRICCIONES", "Uso restringido: permanecer con precaución y pedir inspección"
        acciones = ["Eviten permanecer cerca de la zona afectada y no cuelguen peso en ese elemento.",
                    "Marquen los extremos de la grieta con lápiz y fecha para verificar si crece.",
                    "Soliciten una evaluación detallada de un ingeniero civil o estructural en 24–72 horas.",
                    "Si aparecen nuevas grietas, ruidos o la grieta crece, evacuen."]
    else:
        decision, titulo = "PERMANECER", "Es razonable permanecer, con monitoreo"
        acciones = ["Marquen los extremos de la grieta con lápiz y fecha, y revísenla cada semana.",
                    "Si crece, se ensancha o aparecen otras grietas, repitan el análisis y consulten a un profesional.",
                    "Después de cualquier sismo fuerte, vuelvan a evaluarla."]

    # --- confianza del análisis ---
    conf, razones = 50, []
    if med.get("px_por_mm"):
        conf += 15; razones.append("medida calibrada con objeto de referencia (+15)")
    elif med.get("metodo") == "estimado":
        conf -= 10; razones.append("tamaño aproximado elegido por ti, sin referencia (−10)")
        adv.insert(0, "No hay objeto de referencia: la longitud es una categoría aproximada. Para una medida real, repite el análisis con una tarjeta o regla junto a la grieta.")
    else:
        razones.append("medida ingresada a mano, sin calibración en la foto (+0)")
    if med.get("escala_ia"):
        conf -= 10; razones.append("escala estimada por IA con un objeto de tamaño típico (−10)")
    if vision.get("proveedor"):
        conf += 10; razones.append("lectura visual por IA disponible (+10)")
    cn = extra.get("concordancia")
    if cn == "alta":
        conf += 10; razones.append("la detección automática coincide con tu medición (+10)")
    elif cn == "baja":
        conf -= 15; razones.append("la detección automática difiere de tu medición (−15)")
        adv.append("La detección automática difiere de tu medición. Revisa los puntos que marcaste o toma otra foto de frente.")
    for av in (extra.get("avisos_medicion") or []) if med.get("metodo") != "estimado" else []:
        adv.insert(0, av)
        conf -= 20; razones.append("la referencia parece mal marcada (−20)")
    if vision.get("calidad_foto") == "mala" or extra.get("calidad_baja"):
        conf -= 15; razones.append("calidad de foto baja (−15)")
    if origen_ancho == "supuesto":
        conf -= 10; razones.append("ancho asumido (−10)")
    conf = max(10, min(95, conf))

    adv += ["Resultado preliminar y orientativo: no reemplaza la inspección de un ingeniero estructural.",
            "La medición depende de fotografiar de frente a la superficie y de que el objeto de referencia esté a la misma distancia que la grieta."]
    return {"semaforo": semaforo, "decision": decision, "titulo": titulo, "indice": indice, "puntos": base, "indice_base": base, "ajuste": ajuste,
            "factores": factores, "criticas": [d["titulo"] for d in disparadores], "disparadores": disparadores, "triaje": triaje,
            "bandas": {"amarillo": UMBRAL_AMARILLO, "rojo": UMBRAL_ROJO},
            "acciones": acciones, "advertencias": adv,
            "confianza": {"valor": conf, "razones": razones}, "referencia_semaforo": REF_UNGRD,
            "medidas": {k: med[k] for k in ("metodo", "largo_mm", "ext_x_mm", "ext_y_mm", "angulo_deg", "orientacion")} | {"ancho_cat": cat}}
