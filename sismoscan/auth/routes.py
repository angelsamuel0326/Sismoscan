"""Registro, inicio y cierre de sesión."""
import re
import time
from collections import defaultdict

from flask import Blueprint, current_app, flash, g, make_response, redirect, render_template, request, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .. import mailer, repo
from ..security import cerrar_sesion, destino_seguro, emitir_sesion, limitar, login_required

bp = Blueprint("auth", __name__)
CORREO = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,}$")
COMUNES = {"12345678", "123456789", "1234567890", "password", "contraseña", "qwertyui", "11111111", "abcd1234", "sismoscan"}
_HASH_FALSO = generate_password_hash("contraseña-inexistente")     # iguala el tiempo de respuesta si el correo no existe


_fallos = defaultdict(list)       # (ip, correo) -> instantes de intentos fallidos
MAX_FALLOS, VENTANA_FALLOS = 5, 900


def _validar_clave(clave, correo=""):
    """Reglas comunes de contraseña. Devuelve un mensaje de error o None."""
    minimo = current_app.config["MIN_PASSWORD"]
    if len(clave) < minimo or len(clave) > 128:
        return f"La contraseña debe tener entre {minimo} y 128 caracteres."
    if clave.lower() in COMUNES or (correo and clave.lower() == correo):
        return "Esa contraseña es demasiado común. Elige otra."
    return None


def _enlace(ruta):
    base = (current_app.config.get("PUBLIC_BASE_URL") or request.host_url).rstrip("/")
    return base + ruta


def _enviar_enlace(u, tipo, ruta, asunto, cuerpo):
    """Envía el enlace por correo; si no hay SMTP, queda en el registro y (solo en desarrollo) se muestra en pantalla."""
    enlace = _enlace(ruta)
    enviado = mailer.enviar(current_app.config, u["correo"], asunto, f"{cuerpo}\n\n{enlace}\n\nSi no fuiste tú, ignora este mensaje.", enlace)
    if not enviado and current_app.config["MOSTRAR_ENLACES_DEMO"]:
        flash(f"Modo demostración (sin servidor de correo). Enlace: {enlace}", "ok")
    return enviado


def _enviar_verificacion(u):
    t = repo.crear_token(u["id"], "verificar", 48 * 60)
    _enviar_enlace(u, "verificar", f"/verificar/{t}", "Verifica tu correo en SismoScan", "Confirma tu correo para tu cuenta de SismoScan (el enlace vale 48 horas):")


@bp.route("/registro", methods=["GET", "POST"])
@limitar("registro", 10, 3600)
def registro():
    if g.user:
        return redirect(url_for("main.panel"))
    f = {"nombre": "", "correo": ""}
    if request.method == "POST":
        nombre = " ".join(request.form.get("nombre", "").split())
        correo = request.form.get("correo", "").strip().lower()
        clave = request.form.get("clave", "")
        f = {"nombre": nombre, "correo": correo}
        err = None
        if not 2 <= len(nombre) <= 80:
            err = "Escribe tu nombre (entre 2 y 80 caracteres)."
        elif not CORREO.match(correo):
            err = "Escribe un correo electrónico válido."
        elif _validar_clave(clave, correo):
            err = _validar_clave(clave, correo)
        elif clave != request.form.get("clave2", ""):
            err = "Las contraseñas no coinciden."
        elif not request.form.get("acepto"):
            err = "Debes aceptar el aviso de uso, los términos y la política de privacidad para continuar."
        elif repo.usuario_por_correo(correo):
            err = "Ese correo ya está registrado. Prueba iniciar sesión."
        if err:
            flash(err, "error")
        else:
            uid = repo.crear_usuario(nombre, correo, generate_password_hash(clave))
            _enviar_verificacion(repo.usuario_por_id(uid))
            resp = make_response(redirect(url_for("main.panel")))
            flash(f"¡Bienvenido a SismoScan, {nombre.split()[0]}!", "ok")
            return emitir_sesion(resp, uid)
    return render_template("auth/registro.html", f=f), 200


@bp.route("/ingresar", methods=["GET", "POST"])
@limitar("login", 10, 900)
def ingresar():
    if g.user:
        return redirect(url_for("main.panel"))
    correo = ""
    if request.method == "POST":
        correo = request.form.get("correo", "").strip().lower()
        clave_f, ahora = (request.remote_addr, correo), time.time()
        _fallos[clave_f] = [t for t in _fallos[clave_f] if ahora - t < VENTANA_FALLOS]
        if len(_fallos[clave_f]) >= MAX_FALLOS and current_app.config["RATELIMIT_ENABLED"]:
            minutos = max(1, int((VENTANA_FALLOS - (ahora - _fallos[clave_f][0])) / 60) + 1)
            flash(f"Demasiados intentos fallidos con este correo. Por seguridad, espera unos {minutos} min o usa «¿Olvidaste tu contraseña?».", "error")
            return render_template("auth/ingresar.html", correo=correo), 429
        u = repo.usuario_por_correo(correo)
        ok = check_password_hash(u["clave_hash"] if u else _HASH_FALSO, request.form.get("clave", ""))
        if u and ok:
            _fallos.pop(clave_f, None)
            resp = make_response(redirect(destino_seguro(request.args.get("next"))))
            return emitir_sesion(resp, u["id"], recordar=bool(request.form.get("recordar")))
        _fallos[clave_f].append(ahora)
        quedan = MAX_FALLOS - len(_fallos[clave_f])
        flash("Correo o contraseña incorrectos." + (f" Te quedan {quedan} intento{'s' if quedan != 1 else ''}." if 0 < quedan <= 2 else ""), "error")
    return render_template("auth/ingresar.html", correo=correo), 200


@bp.post("/salir")
def salir():
    resp = make_response(redirect(url_for("auth.ingresar")))
    return cerrar_sesion(resp)


# ---------------- recuperar contraseña ----------------
@bp.route("/olvide", methods=["GET", "POST"])
@limitar("olvide", 5, 3600)
def olvide():
    if request.method == "POST":
        correo = request.form.get("correo", "").strip().lower()
        u = repo.usuario_por_correo(correo) if CORREO.match(correo) else None
        if u:
            t = repo.crear_token(u["id"], "reset", 30)
            _enviar_enlace(u, "reset", f"/restablecer/{t}", "Restablece tu contraseña de SismoScan", "Usa este enlace para elegir una contraseña nueva (vale 30 minutos):")
        flash("Si ese correo está registrado, te enviamos las instrucciones para restablecer la contraseña (revisa también el spam).", "ok")
        return redirect(url_for("auth.ingresar"))
    return render_template("auth/olvide.html")


@bp.route("/restablecer/<token>", methods=["GET", "POST"])
@limitar("restablecer", 10, 3600)
def restablecer(token):
    if not repo.token_valido(token, "reset"):
        flash("Ese enlace no es válido o ya venció. Pide uno nuevo.", "error")
        return redirect(url_for("auth.olvide"))
    if request.method == "POST":
        clave = request.form.get("clave", "")
        err = _validar_clave(clave) or (None if clave == request.form.get("clave2", "") else "Las contraseñas no coinciden.")
        if err:
            flash(err, "error")
        else:
            uid = repo.consumir_token(token, "reset")
            if uid:
                repo.cambiar_clave(uid, generate_password_hash(clave))
                repo.marcar_verificado(uid)           # llegar al enlace por correo prueba que controla el buzón
                flash("Contraseña actualizada. Inicia sesión con la nueva.", "ok")
                return redirect(url_for("auth.ingresar"))
    return render_template("auth/restablecer.html", token=token)


# ---------------- verificar correo ----------------
@bp.get("/verificar/<token>")
def verificar(token):
    uid = repo.consumir_token(token, "verificar")
    if uid:
        repo.marcar_verificado(uid)
        flash("¡Correo verificado! Gracias.", "ok")
    else:
        flash("Ese enlace de verificación no es válido o ya venció.", "error")
    return redirect(url_for("main.panel" if g.user else "auth.ingresar"))


@bp.post("/reenviar-verificacion")
@login_required
@limitar("reenviar", 3, 3600)
def reenviar_verificacion():
    if g.user["verificado"]:
        flash("Tu correo ya está verificado.", "ok")
    else:
        _enviar_verificacion(g.user)
        flash("Te enviamos un nuevo enlace de verificación.", "ok")
    return redirect(request.referrer if request.referrer and request.referrer.startswith(request.host_url) else url_for("main.cuenta"))
