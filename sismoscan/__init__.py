"""SismoScan - fábrica de la aplicación Flask."""
import os
import secrets
from pathlib import Path

from flask import Flask, g, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from config import Config


def _css_version(app: Flask) -> str:
    """Número que cambia cuando cambia el CSS: obliga al navegador a descargar la versión nueva."""
    try:
        d = Path(app.static_folder) / "css"
        return str(int(max((d / n).stat().st_mtime for n in ("app.css", "auth.css", "panel.css", "analizar.css", "resultado.css", "historial.css", "metodologia.css", "marca.css", "chatbot.css"))))
    except OSError:
        return "0"


def _clave_secreta(app: Flask) -> str:
    """En producción SECRET_KEY es obligatoria; en desarrollo se genera y se guarda en instance/."""
    if app.config["SECRET_KEY"]:
        return app.config["SECRET_KEY"]
    if app.config["APP_ENV"] == "production":
        raise RuntimeError("Define la variable de entorno SECRET_KEY en producción.")
    f = Path(app.instance_path) / "secret.key"
    if not f.exists():
        f.write_text(secrets.token_urlsafe(48))
        os.chmod(f, 0o600)
    return f.read_text().strip()


def _iniciar_sentry(app: Flask) -> None:
    """Registro de errores opcional: solo si hay SENTRY_DSN y sentry-sdk instalado."""
    dsn = app.config.get("SENTRY_DSN")
    if not dsn:
        return
    try:
        import sentry_sdk
        sentry_sdk.init(dsn=dsn, send_default_pii=False, traces_sample_rate=0.0, environment=app.config["APP_ENV"])
    except ImportError:
        app.logger.warning("SENTRY_DSN definido pero sentry-sdk no está instalado (pip install sentry-sdk[flask]).")


def _validar_produccion(app: Flask) -> None:
    """En producción exige ajustes seguros: clave larga, cookies Secure y no mostrar enlaces de demostración."""
    if app.config["APP_ENV"] != "production" or app.config.get("TESTING"):
        return
    if len(app.config["SECRET_KEY"]) < 32:
        raise RuntimeError("SECRET_KEY debe tener al menos 32 caracteres en producción.")
    if not app.config["COOKIE_SECURE"]:
        raise RuntimeError("COOKIE_SECURE debe ser 1 en producción (HTTPS).")
    if app.config.get("MOSTRAR_ENLACES_DEMO"):
        raise RuntimeError("MOSTRAR_ENLACES_DEMO debe ser 0 en producción: mostraría los enlaces de recuperación en pantalla.")


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    os.makedirs(app.instance_path, exist_ok=True)
    _iniciar_sentry(app)
    app.config["SECRET_KEY"] = _clave_secreta(app)
    _validar_produccion(app)
    if not app.config["DATABASE_PATH"]:
        app.config["DATABASE_PATH"] = str(Path(app.instance_path) / "sismoscan.db")
    if app.config["TRUST_PROXY"]:
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    from . import db, security
    from .analysis import rules
    app.jinja_env.globals["ELEMENTOS"] = rules.ELEMENTOS
    db.init_app(app)
    security.init_app(app)

    from .auth.routes import bp as auth_bp
    from .main.routes import bp as main_bp
    from .api.routes import bp as api_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix="/api/v1")

    @app.context_processor
    def contexto():
        from .analysis.vision import estado_proveedores
        from . import asistente
        return {"css_v": _css_version(app), "ASISTENTE_BIENVENIDA": asistente.BIENVENIDA, "ASISTENTE_SUGERENCIAS": asistente.SUGERENCIAS, "ASISTENTE_IA": asistente.ia_activa(app.config), "emergencias": app.config["EMERGENCY_NUMBERS"], "usuario": g.get("user"), "proveedores_vision": estado_proveedores(app.config), "equipo": app.config["EQUIPO"], "contacto": app.config["CONTACT_EMAIL"]}

    @app.errorhandler(HTTPException)
    def error_http(e):
        if request.path.startswith("/api/"):
            return jsonify(error=e.description or e.name), e.code
        return render_template("error.html", codigo=e.code, titulo=e.name, mensaje=e.description), e.code

    @app.errorhandler(Exception)
    def error_interno(e):
        app.logger.exception("Error no controlado")
        if request.path.startswith("/api/"):
            return jsonify(error="Error interno del servidor."), 500
        return render_template("error.html", codigo=500, titulo="Error interno",
                               mensaje="Algo salió mal de nuestro lado. Inténtalo de nuevo."), 500

    return app
