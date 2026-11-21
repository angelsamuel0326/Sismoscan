"""Proveedor Google Cloud Vision (REST, clave de API). Detecta etiquetas y objetos; es una señal complementaria:
no mide grietas, solo corrobora que la foto muestra una grieta/daño. Requiere GOOGLE_VISION_API_KEY."""
import base64

import requests

from .base import VisionError, normalizar

ETIQUETAS_GRIETA = ("crack", "fracture", "damage", "wear")
ETIQUETAS_ESCOMBRO = ("rubble", "debris", "ruins", "demolition")


class GoogleProvider:
    nombre = "google"

    def __init__(self, cfg):
        self.key, self.timeout = cfg["GOOGLE_VISION_API_KEY"], cfg["VISION_TIMEOUT"]

    def disponible(self) -> bool:
        return bool(self.key)

    def analizar(self, jpeg: bytes, ctx: dict) -> dict:
        body = {"requests": [{"image": {"content": base64.b64encode(jpeg).decode()},
                              "features": [{"type": "LABEL_DETECTION", "maxResults": 20}, {"type": "OBJECT_LOCALIZATION", "maxResults": 5}]}]}
        try:
            r = requests.post("https://vision.googleapis.com/v1/images:annotate", params={"key": self.key}, json=body, timeout=self.timeout)
        except requests.RequestException:
            raise VisionError("No se pudo contactar a Google Cloud Vision.")
        if r.status_code in (400, 401, 403):
            raise VisionError("Google Cloud Vision rechazó la solicitud o la clave.")
        if not r.ok:
            raise VisionError(f"Google Cloud Vision respondió con error {r.status_code}.")
        try:
            etiquetas = [(e["description"].lower(), e.get("score", 0)) for e in r.json()["responses"][0].get("labelAnnotations", [])]
        except (KeyError, IndexError, ValueError):
            raise VisionError("Respuesta de Google Cloud Vision inesperada.")
        grieta = any(any(k in d for k in ETIQUETAS_GRIETA) and s >= 0.5 for d, s in etiquetas)
        escombro = any(any(k in d for k in ETIQUETAS_ESCOMBRO) and s >= 0.5 for d, s in etiquetas)
        top = ", ".join(d for d, _ in etiquetas[:5])
        raw = {"grieta_visible": True if grieta else None, "desprendimiento": True if escombro else None,
               "confianza": max((s for d, s in etiquetas if any(k in d for k in ETIQUETAS_GRIETA)), default=0.4),
               "observaciones": f"Etiquetas detectadas: {top}" if top else ""}
        return normalizar(raw, self.nombre, "cloud-vision-v1")
