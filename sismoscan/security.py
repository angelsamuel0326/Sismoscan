"""Seguridad: sesión JWT en cookie HttpOnly, CSRF, límite de intentos y cabeceras HTTP."""
import hmac
import secrets
import threading
import time
from functools import wraps
from urllib.parse import urlparse

import jwt
from flask import abort, current_app, g, jsonify, redirect, request, url_for

from . import repo

COOKIE_JWT = "ss_session"
COOKIE_CSRF = "ss_csrf"          # solo para visitantes sin sesión (login/registro)
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


# ---------------- JWT ----------------
def emitir_sesion(response, user_id: int, recordar: bool = False):
    """Crea un JWT firmado (HS256) con un id revocable y lo guarda en una cookie HttpOnly."""
    cfg = current_app.config
    ahora = int(time.time())
    horas = cfg["REMEMBER_DAYS"] * 24 if recordar else cfg["SESSION_HOURS"]
    exp = ahora + horas * 3600
    jti, csrf = secrets.token_urlsafe(16), secrets.token_urlsafe(24)
    token = jwt.encode({"sub": str(user_id), "jti": jti, "csrf": csrf, "iat": ahora, "exp": exp},
                       cfg["SECRET_KEY"], algorithm="HS256")
    repo.registrar_sesion(jti, user_id, exp)
    response.set_cookie(COOKIE_JWT, token, max_age=horas * 3600, httponly=True,
                        secure=cfg["COOKIE_SECURE"], samesite="Lax", path="/")
    response.delete_cookie(COOKIE_CSRF, path="/")
    return response


def cerrar_sesion(response):
    if getattr(g, "jti", None):
        repo.revocar_sesion(g.jti)
    response.delete_cookie(COOKIE_JWT, path="/")
    return response


def _cargar_usuario():
    g.user, g.jti, g.csrf, g._set_anon_csrf = None, None, None, None
    token = request.cookies.get(COOKIE_JWT)
    if token:
        try:
            d = jwt.decode(token, current_app.config["SECRET_KEY"], algorithms=["HS256"],
                           options={"require": ["exp", "sub", "jti", "csrf"]})
            uid = int(d["sub"])
            if repo.sesion_valida(d["jti"], uid):
                u = repo.usuario_por_id(uid)
                if u:
                    g.user, g.jti, g.csrf = u, d["jti"], d["csrf"]
        except (jwt.PyJWTError, ValueError):
            pass
    if g.csrf is None:                       # visitante: token CSRF por doble cookie
        anon = request.cookies.get(COOKIE_CSRF)
        if not anon:
            anon = secrets.token_urlsafe(24)
            g._set_anon_csrf = anon
        g.csrf = anon


def csrf_token() -> str:
    return g.csrf


def _verificar_csrf():
    if request.method not in UNSAFE:
        return
    enviado = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token") or ""
    if not hmac.compare_digest(enviado, g.csrf or ""):
        abort(400, description="Sesión de formulario inválida o vencida. Recarga la página e inténtalo de nuevo.")


# ---------------- decoradores ----------------
def login_required(view):
    @wraps(view)
    def envuelta(*a, **k):
        if g.user is None:
            if request.path.startswith("/api/"):
                return jsonify(error="Inicia sesión para continuar."), 401
            return redirect(url_for("auth.ingresar", next=request.full_path.rstrip("?")))
        return view(*a, **k)
    return envuelta


def destino_seguro(destino: str | None) -> str:
    """Evita 'open redirect': solo rutas relativas del mismo sitio."""
    if destino and destino.startswith("/") and not destino.startswith("//") and not urlparse(destino).netloc:
        return destino
    return url_for("main.panel")


# ---------------- límite de intentos ----------------
_lock = threading.Lock()
_hits: dict[str, list[float]] = {}


def limitar(nombre: str, maximo: int, ventana: int, metodos=UNSAFE):
    def deco(view):
        @wraps(view)
        def envuelta(*a, **k):
            if current_app.config["RATELIMIT_ENABLED"] and request.method in metodos:
                clave, ahora = f"{nombre}:{request.remote_addr}", time.time()
                with _lock:
                    lst = [t for t in _hits.get(clave, []) if ahora - t < ventana]
                    lst.append(ahora)
                    _hits[clave] = lst
                    excedido = len(lst) > maximo
                if excedido:
                    abort(429, description="Demasiados intentos. Espera unos minutos e inténtalo de nuevo.")
            return view(*a, **k)
        return envuelta
    return deco


def reiniciar_limites():   # útil en pruebas
    with _lock:
        _hits.clear()


# ---------------- cabeceras ----------------
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; "
       "font-src 'self' https://fonts.gstatic.com; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; "
       "manifest-src 'self'; worker-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")


def _despues(resp):
    if g.get("_set_anon_csrf"):
        resp.set_cookie(COOKIE_CSRF, g._set_anon_csrf, httponly=True, samesite="Lax",
                        secure=current_app.config["COOKIE_SECURE"], path="/", max_age=3600 * 4)
    resp.headers.setdefault("Content-Security-Policy", CSP)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    resp.headers.setdefault("Permissions-Policy", "camera=(self), microphone=(), geolocation=()")
    if current_app.config["COOKIE_SECURE"]:
        resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    if not request.path.startswith("/static/") and "Cache-Control" not in resp.headers:
        resp.headers["Cache-Control"] = "no-store"
    return resp


def init_app(app):
    app.before_request(_cargar_usuario)
    app.before_request(_verificar_csrf)
    app.after_request(_despues)
    app.jinja_env.globals["csrf_token"] = csrf_token
