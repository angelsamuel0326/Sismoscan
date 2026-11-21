"""API JSON (v1) usada por la interfaz: análisis de imágenes e historial."""
import json
import logging
from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, g, jsonify, request, url_for

from .. import asistente, chat, repo
from ..analysis import images, pipeline
from ..security import limitar, login_required

bp = Blueprint("api", __name__)
log = logging.getLogger(__name__)


def _fecha_captura(valor):
    """Hora en que se tomó la foto si el análisis se envió después (modo sin conexión). Se acepta solo si es razonable."""
    if not valor:
        return None
    try:
        t = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
        t = t.astimezone(timezone.utc) if t.tzinfo else t.replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    ahora = datetime.now(timezone.utc)
    if t > ahora + timedelta(minutes=5) or t < ahora - timedelta(days=60):
        return None
    return t.strftime("%Y-%m-%d %H:%M:%S")


@bp.post("/analyses")
@login_required
@limitar("analisis", 40, 3600)
def crear_analisis():
    """multipart/form-data: «imagen» (archivo) + «datos» (JSON con contexto, medición y consentimiento)."""
    archivo = request.files.get("imagen")
    if archivo is None:
        return jsonify(error="Falta la fotografía."), 400
    try:
        datos = json.loads(request.form.get("datos", ""))
        if not isinstance(datos, dict):
            raise ValueError
    except ValueError:
        return jsonify(error="Los datos del análisis no son válidos."), 400
    if datos.get("consentimiento") is not True:
        return jsonify(error="Debes autorizar el procesamiento de la foto para continuar."), 400
    try:
        out = pipeline.analizar(current_app.config, datos, archivo.read())
    except pipeline.FotoInservible as e:
        return jsonify(error=str(e), repetir_foto=True), 422
    except (pipeline.EntradaInvalida, images.ImagenInvalida) as e:
        return jsonify(error=str(e)), 400
    caso_id = grieta_id = None
    for campo in ("remedir_de", "otra_de"):
        if datos.get(campo) not in (None, ""):
            try:
                previo = repo.obtener_analisis(g.user["id"], int(datos[campo]))
            except (TypeError, ValueError):
                previo = None
            if not previo:
                return jsonify(error="El análisis anterior no existe."), 400
            caso_id = repo.clave_caso(previo)
            if campo == "remedir_de":
                grieta_id = repo.clave_grieta(previo)
            break
    aid = repo.guardar_analisis(g.user["id"], out["entrada"], out["resultado"], out["miniatura"], out["deteccion"], caso_id, grieta_id,
                                _fecha_captura(datos.get("capturado_en")))
    return jsonify(id=aid, url=url_for("main.resultado", aid=aid), semaforo=out["resultado"]["semaforo"]), 201


@bp.post("/escala")
@login_required
@limitar("escala", 20, 3600)
def sugerir_escala():
    """multipart: «imagen». La IA propone un objeto de tamaño típico como referencia; el usuario siempre lo revisa."""
    from ..analysis.vision import proveedor_externo, VisionError
    prov = proveedor_externo(current_app.config)
    if not prov or not hasattr(prov, "estimar_escala"):
        return jsonify(error="La estimación con IA no está configurada (falta la clave de OpenAI). Usa una tarjeta o regla de referencia."), 503
    archivo = request.files.get("imagen")
    if archivo is None:
        return jsonify(error="Falta la fotografía."), 400
    try:
        img = images.preparar(archivo.read(), current_app.config["MAX_IMAGE_SIDE"], current_app.config["THUMB_SIDE"])
        return jsonify(prov.estimar_escala(img.jpeg))
    except images.ImagenInvalida as e:
        return jsonify(error=str(e)), 400
    except VisionError as e:
        log.warning("Escala por IA falló: %s", e)
        return jsonify(error=str(e)), 502


@bp.post("/autocompletar")
@login_required
@limitar("autocompletar", 30, 3600)
def autocompletar():
    """multipart: «imagen». Propone los datos del formulario a partir de la foto; el usuario acepta o modifica."""
    from ..analysis import autocompletar as ac
    from ..analysis.vision import proveedor_externo, VisionError
    archivo = request.files.get("imagen")
    if archivo is None:
        return jsonify(error="Falta la fotografía."), 400
    try:
        img = images.preparar(archivo.read(), current_app.config["MAX_IMAGE_SIDE"], current_app.config["THUMB_SIDE"])
    except images.ImagenInvalida as e:
        return jsonify(error=str(e)), 400
    prov = proveedor_externo(current_app.config)
    if prov and hasattr(prov, "describir"):
        try:
            return jsonify(prov.describir(img.jpeg))
        except VisionError as e:
            log.warning("Autocompletar por IA falló: %s", e)
    try:
        return jsonify(ac.local(img.bgr))
    except Exception:  # la sugerencia es opcional: si falla, el formulario se llena a mano
        log.exception("Autocompletar local falló")
        return jsonify(origen="ninguno", campos={}, observaciones="No se pudo leer la foto automáticamente. Llena el formulario a mano."), 200


@bp.get("/analyses")
@login_required
def listar():
    return jsonify([{"id": a["id"], "creado": a["creado"], "semaforo": a["resultado"]["semaforo"], "indice": a["resultado"]["indice"],
                     "decision": a["resultado"]["decision"]} for a in repo.listar_analisis(g.user["id"])])


@bp.delete("/analyses/<int:aid>")
@login_required
def borrar(aid):
    if not repo.borrar_analisis(g.user["id"], aid):
        return jsonify(error="Análisis no encontrado."), 404
    return jsonify(ok=True)


# ---------------- chat post-análisis ----------------
@bp.get("/analyses/<int:aid>/chat")
@login_required
def chat_historial(aid):
    if not repo.obtener_analisis(g.user["id"], aid):
        return jsonify(error="Análisis no encontrado."), 404
    return jsonify(mensajes=repo.listar_mensajes(g.user["id"], aid))


@bp.post("/analyses/<int:aid>/chat")
@login_required
@limitar("chat", 40, 3600)
def chat_enviar(aid):
    """JSON {mensaje}. El asistente recibe como contexto el análisis guardado (no confía en nada enviado por el cliente)."""
    a = repo.obtener_analisis(g.user["id"], aid)
    if not a:
        return jsonify(error="Análisis no encontrado."), 404
    datos = request.get_json(silent=True) or {}
    texto = " ".join(str(datos.get("mensaje", "")).split())
    if not texto:
        return jsonify(error="Escribe tu pregunta."), 400
    if len(texto) > chat.MAX_MENSAJE:
        return jsonify(error=f"El mensaje es demasiado largo (máximo {chat.MAX_MENSAJE} caracteres)."), 400
    if repo.contar_mensajes_usuario(g.user["id"], aid) >= chat.MAX_USUARIO_POR_ANALISIS:
        return jsonify(error="Alcanzaste el límite de preguntas para este análisis. Haz un nuevo análisis o consulta a un ingeniero."), 400
    historial = repo.listar_mensajes(g.user["id"], aid, 12)
    out = chat.responder(texto, historial, a, current_app.config)
    repo.guardar_mensaje(g.user["id"], aid, "user", texto)
    repo.guardar_mensaje(g.user["id"], aid, "assistant", out["respuesta"])
    return jsonify(out)


# ---------------- asistente general flotante ----------------
@bp.post("/asistente")
@login_required
@limitar("asistente", 60, 3600)
def asistente_enviar():
    """JSON {mensaje, historial?}. No guarda nada en el servidor; el historial viaja desde el navegador y se sanea."""
    datos = request.get_json(silent=True) or {}
    texto = " ".join(str(datos.get("mensaje", "")).split())
    if not texto:
        return jsonify(error="Escribe tu pregunta."), 400
    if len(texto) > asistente.MAX_MENSAJE:
        return jsonify(error=f"El mensaje es demasiado largo (máximo {asistente.MAX_MENSAJE} caracteres)."), 400
    historial = asistente.limpiar_historial(datos.get("historial"))
    aid = datos.get("analisis_id")
    a = repo.obtener_analisis(g.user["id"], aid) if isinstance(aid, int) and not isinstance(aid, bool) else None
    if a:       # en la página de un resultado, la burbuja usa el mismo motor (y los mismos datos) que el chat de esa página
        return jsonify(chat.responder(texto, historial, a, current_app.config))
    return jsonify(asistente.responder(texto, historial, current_app.config))
