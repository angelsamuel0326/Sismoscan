"""Validación y preparación de imágenes: formato real, orientación EXIF, reducción y eliminación de metadatos."""
import io
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

Image.MAX_IMAGE_PIXELS = 40_000_000      # protege contra "bombas de descompresión"
FORMATOS = {"JPEG", "PNG", "WEBP"}


class ImagenInvalida(ValueError):
    """Error con mensaje apto para mostrar al usuario."""


@dataclass
class ImagenPreparada:
    jpeg: bytes          # imagen reducida para análisis (sin EXIF/GPS)
    miniatura: bytes     # JPEG pequeño para historial
    bgr: np.ndarray      # matriz OpenCV
    ancho: int
    alto: int


def _jpeg(img: Image.Image, calidad: int) -> bytes:
    b = io.BytesIO()
    img.save(b, "JPEG", quality=calidad, optimize=True)      # re-codificar elimina todos los metadatos
    return b.getvalue()


def preparar(datos: bytes, lado_max: int = 1600, lado_mini: int = 640) -> ImagenPreparada:
    if not datos:
        raise ImagenInvalida("No se recibió ninguna imagen.")
    try:
        with Image.open(io.BytesIO(datos)) as im:
            if im.format not in FORMATOS:
                raise ImagenInvalida("Formato no admitido. Usa una foto JPG, PNG o WEBP.")
            im.load()
            img = ImageOps.exif_transpose(im).convert("RGB")
    except ImagenInvalida:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, ValueError):
        raise ImagenInvalida("El archivo no es una imagen válida o es demasiado grande.")
    if min(img.size) < 200:
        raise ImagenInvalida("La imagen es demasiado pequeña (mínimo 200 px por lado).")
    img.thumbnail((lado_max, lado_max), Image.LANCZOS)
    mini = img.copy()
    mini.thumbnail((lado_mini, lado_mini), Image.LANCZOS)
    bgr = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)
    return ImagenPreparada(_jpeg(img, 88), _jpeg(mini, 78), bgr, img.width, img.height)


# Umbrales calibrados con el banco de pruebas (todas las fotos reales tienen nitidez > 90, brillo 100-200).
BLOQUEO_NITIDEZ, AVISO_NITIDEZ = 12.0, 40.0
BLOQUEO_OSCURA, AVISO_OSCURA = 30.0, 55.0
BLOQUEO_CLARA, AVISO_CLARA = 245.0, 225.0
BLOQUEO_PLANA = 5.0


def evaluar_calidad(bgr) -> dict:
    """Mide nitidez (varianza del Laplaciano), brillo y contraste. «bloqueo» = mensaje si la foto no sirve para analizar
    (hay que repetirla); «avisos» = problemas leves que solo bajan la confianza. Misma regla que usa el navegador al cargar la foto."""
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    nit, br, sd = float(cv2.Laplacian(g, cv2.CV_64F).var()), float(g.mean()), float(g.std())
    bloqueo, avisos = None, []
    if nit < BLOQUEO_NITIDEZ:
        bloqueo = "La foto está muy borrosa. Repítela con el celular quieto, enfocando la grieta (toca la pantalla para enfocar)."
    elif br < BLOQUEO_OSCURA:
        bloqueo = "La foto está demasiado oscura. Repítela con más luz (luz natural o una linterna de lado)."
    elif br > BLOQUEO_CLARA:
        bloqueo = "La foto está sobreexpuesta (muy clara). Repítela sin flash directo ni luz fuerte de frente."
    elif sd < BLOQUEO_PLANA:
        bloqueo = "La foto casi no tiene detalle (muy plana). Acércate a la grieta y repítela con buena luz."
    else:
        if nit < AVISO_NITIDEZ:
            avisos.append("La foto está algo borrosa: si puedes, repítela más nítida.")
        if br < AVISO_OSCURA:
            avisos.append("La foto está oscura: si puedes, repítela con más luz.")
        elif br > AVISO_CLARA:
            avisos.append("La foto está muy clara: si puedes, repítela con menos luz.")
    return {"nitidez": round(nit, 1), "brillo": round(br, 1), "contraste": round(sd, 1), "bloqueo": bloqueo, "avisos": avisos}
