"""Orquestador del análisis: valida → prepara la imagen → mide → detecta (OpenCV) → lectura de IA → reglas."""
import logging
import re

import cv2

from . import geometry, images, rules
from .vision import VisionError, proveedor_externo
from .vision.opencv_provider import detectar

log = logging.getLogger(__name__)


class EntradaInvalida(ValueError):
    pass


class FotoInservible(EntradaInvalida):
    """La foto es muy borrosa, oscura o plana: hay que repetirla."""


ORIGENES_ESCALA = {"ia"}          # la referencia fue propuesta por la IA a partir de un objeto de tamaño típico


def validar_contexto(d: dict) -> dict:
    """Solo se aceptan valores de listas cerradas; cualquier otra cosa se rechaza."""
    def elige(clave, permitidos, defecto=None):
        v = d.get(clave, defecto)
        if v not in permitidos:
            raise EntradaInvalida(f"Valor inválido en «{clave}».")
        return v
    senales = d.get("senales") or []
    if not isinstance(senales, list) or any(s not in rules.SENALES for s in senales):
        raise EntradaInvalida("Señales de peligro inválidas.")
    ubicacion = re.sub(r"[\x00-\x1f<>]+", " ", str(d.get("ubicacion") or "")).strip()[:80]
    return {"ubicacion": ubicacion, "elemento": elige("elemento", rules.ELEMENTOS), "material": elige("material", rules.MATERIALES, "nosabe"),
            "sismo_reciente": bool(d.get("sismo_reciente")), "senales": sorted(set(senales)),
            "ancho_cat": elige("ancho_cat", rules.ANCHOS, "nosabe"), "patron": elige("patron", rules.PATRONES, "simple"),
            "grupo_uso": elige("grupo_uso", rules.GRUPOS_USO, "I"), "anio": elige("anio", rules.ANIOS, "nosabe")}


def _cat_ancho(mm):
    return "fina" if mm < 0.3 else "media" if mm < 1 else "ancha" if mm < 3 else "muyancha"


def _concordancia(med, auto):
    if not auto.get("detectada"):
        return None
    dang = abs(med["angulo_deg"] - auto["angulo_deg"])
    if med.get("px_por_mm") and auto.get("largo_mm"):
        dl = abs(auto["largo_mm"] - med["largo_mm"]) / max(med["largo_mm"], 1)
        if dl <= 0.25 and dang <= 12:
            return "alta"
        if dl > 0.5 or dang > 25:
            return "baja"
        return "media"
    return "alta" if dang <= 12 else "baja" if dang > 30 else "media"


def analizar(cfg, datos: dict, archivo: bytes) -> dict:
    ctx = validar_contexto(datos)
    img = images.preparar(archivo, cfg["MAX_IMAGE_SIDE"], cfg["THUMB_SIDE"])
    calidad = images.evaluar_calidad(img.bgr)
    if calidad["bloqueo"]:                       # foto inservible: se pide repetirla en vez de analizar con datos malos
        raise FotoInservible(calidad["bloqueo"])

    # 1) medidas del usuario (trazo calibrado o valores manuales)
    m = datos.get("medicion") or {}
    trazo = ref = None
    try:
        if m.get("modo") == "trazo":
            lineas = m.get("trazos") if m.get("trazos") is not None else [m.get("trazo")]
            med = geometry.desde_trazos(lineas, m.get("ref"), m.get("ref_mm"), img.ancho, img.alto)
            trazo, ref = lineas, m["ref"]
            med["escala_ia"] = m.get("ref_origen") in ORIGENES_ESCALA
        elif m.get("modo") == "estimado":
            med = geometry.desde_estimado(m.get("largo_cat"), m.get("eje"), m.get("angulo"))
        elif m.get("modo") == "manual":
            med = geometry.desde_manual(m.get("largo_cm"), m.get("eje"), m.get("angulo"), m.get("x_cm"), m.get("y_cm"))
        else:
            raise EntradaInvalida("Falta la medición de la grieta (longitud y orientación).")
    except geometry.GeometriaInvalida as e:
        raise EntradaInvalida(str(e))

    proveedores = []
    # 2) detección local con OpenCV. Solo se usa cuando el usuario marcó la grieta sobre la foto: el trazo acota dónde buscar.
    #    Sin trazo la detección libre confunde bordes, sombras y texturas con grietas (ver tools/evaluar_banco.py), así que
    #    no se ejecuta ni alimenta las reglas.
    auto = {"detectada": False}
    if trazo:
        try:
            auto = detectar(img.bgr, trazo, ref, med["px_por_mm"])
            proveedores.append({"nombre": "local", "etiqueta": "Detección local (OpenCV)",
                                "estado": "ok" if auto.get("detectada") else "sin_hallazgos",
                                "detalle": "Grieta detectada junto a tu trazo." if auto.get("detectada") else "No se detectó una grieta clara junto a tu trazo."})
        except Exception:           # la detección es complementaria: nunca debe tumbar el análisis
            log.exception("Fallo en la detección local")
            auto = {"detectada": False}
            proveedores.append({"nombre": "local", "etiqueta": "Detección local (OpenCV)", "estado": "error", "detalle": "No pudo ejecutarse."})
    else:
        proveedores.append({"nombre": "local", "etiqueta": "Detección local (OpenCV)", "estado": "no_aplica",
                            "detalle": "Solo se ejecuta cuando marcas la grieta sobre la foto."})

    # 3) lectura semántica con IA externa (opcional)
    vision, prov = None, proveedor_externo(cfg)
    if prov:
        try:
            vision = prov.analizar(img.jpeg, ctx)
            proveedores.append({"nombre": prov.nombre, "etiqueta": f"IA {prov.nombre.capitalize()}" + (f" · {prov.model}" if hasattr(prov, "model") else ""),
                                "estado": "ok", "detalle": "Lectura visual recibida."})
        except VisionError as e:
            log.warning("Proveedor %s falló: %s", prov.nombre, e)
            proveedores.append({"nombre": prov.nombre, "etiqueta": f"IA {prov.nombre.capitalize()}", "estado": "error", "detalle": str(e)})
    else:
        proveedores.append({"nombre": "ia", "etiqueta": "IA externa", "estado": "no_configurado",
                            "detalle": "Sin clave de API: el resultado usa las medidas y la detección local."})

    extra = {"avisos_medicion": med.get("avisos") or [], "concordancia": _concordancia(med, auto), "calidad_baja": bool(calidad["avisos"]),
             "cruzada_local": bool(auto.get("cruzada")) and (auto.get("confianza") or 0) >= 0.5}
    if auto.get("ancho_mm") and auto.get("confianza", 0) >= 0.4:
        extra["ancho_cat_local"] = _cat_ancho(auto["ancho_mm"])

    res = rules.evaluar(ctx, med, vision, extra)
    for av in calidad["avisos"]:
        res["advertencias"].insert(0, av)
    res["proveedores"] = proveedores
    res["deteccion_local"] = {k: auto.get(k) for k in ("detectada", "largo_mm", "angulo_deg", "ancho_mm", "confianza", "cruzada")}
    res["vision"] = {k: v for k, v in (vision or {}).items() if k != "observaciones"} or None
    entrada = {**ctx, "medicion": {k: v for k, v in med.items() if k not in ("px_por_mm", "avisos")} | {"calibrada": bool(med.get("px_por_mm"))},
               "calidad_foto": {k: calidad[k] for k in ("nitidez", "brillo", "contraste")}}
    return {"entrada": entrada, "resultado": res, "miniatura": img.miniatura if cfg["STORE_THUMBNAIL"] else None,
            "deteccion": auto.get("overlay_png") if cfg["STORE_THUMBNAIL"] else None}
