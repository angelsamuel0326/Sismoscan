"""Contrato común de los proveedores de visión y normalización de su salida (que se trata como dato NO confiable)."""
import json
import re


class VisionError(Exception):
    """El proveedor no pudo analizar la imagen (red, clave inválida, respuesta inesperada)."""


PATRONES = {"horizontal", "vertical", "diagonal", "cruzada", "mapa", "ninguno", "indeterminado"}
ANCHOS = {"fina", "media", "ancha", "muyancha", "indeterminado"}
CALIDAD = {"buena", "regular", "mala"}


def _bool(v):
    return v if isinstance(v, bool) else None


def normalizar(raw: dict, proveedor: str, modelo: str = "") -> dict:
    """Solo se aceptan valores de listas cerradas; el texto libre se recorta y se limpia."""
    if not isinstance(raw, dict):
        raise VisionError("Respuesta de visión con formato inesperado.")
    patron = raw.get("patron_grieta")
    ancho = raw.get("ancho_estimado")
    calidad = raw.get("calidad_foto")
    try:
        conf = max(0.0, min(1.0, float(raw.get("confianza"))))
    except (TypeError, ValueError):
        conf = None
    obs = raw.get("observaciones")
    obs = re.sub(r"[\x00-\x1f<>]+", " ", obs).strip()[:240] if isinstance(obs, str) else ""
    return {"proveedor": proveedor, "modelo": modelo,
            "patron": patron if patron in PATRONES else "indeterminado",
            "ancho_cat": ancho if ancho in ANCHOS else "indeterminado",
            "calidad_foto": calidad if calidad in CALIDAD else None,
            "desprendimiento": _bool(raw.get("desprendimiento")), "varilla_expuesta": _bool(raw.get("varilla_expuesta")),
            "inclinacion_visible": _bool(raw.get("inclinacion_visible")), "grieta_probable": _bool(raw.get("grieta_visible")),
            "confianza": conf, "observaciones": obs}


def extraer_json(texto: str) -> dict:
    try:
        return json.loads(texto)
    except (TypeError, ValueError):
        m = re.search(r"\{.*\}", texto or "", re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except ValueError:
                pass
    raise VisionError("La respuesta del modelo no es JSON válido.")
