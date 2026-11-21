"""Fábrica de proveedores de visión. VISION_PROVIDER = auto | openai | google | local.
La detección local (OpenCV) siempre se ejecuta; OpenAI/Google aportan la lectura semántica si están configurados."""
from .base import VisionError  # noqa: F401
from .google_provider import GoogleProvider
from .openai_provider import OpenAIProvider


def proveedor_externo(cfg):
    modo = cfg["VISION_PROVIDER"]
    if modo == "local":
        return None
    candidatos = {"openai": [OpenAIProvider], "google": [GoogleProvider], "auto": [OpenAIProvider, GoogleProvider]}.get(modo, [OpenAIProvider, GoogleProvider])
    for clase in candidatos:
        p = clase(cfg)
        if p.disponible():
            return p
    return None


def estado_proveedores(cfg) -> dict:
    p = proveedor_externo(cfg)
    return {"local": True, "externo": p.nombre if p else None, "modelo": getattr(p, "model", "") if p else "",
            "modo": cfg["VISION_PROVIDER"]}
