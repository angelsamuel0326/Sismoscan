"""Envío de correo opcional. Sin SMTP configurado no se envía nada: el enlace queda en el registro del servidor."""
import logging
import smtplib
import ssl
from email.message import EmailMessage

log = logging.getLogger("sismoscan.correo")


def enviar(cfg, destino: str, asunto: str, texto: str, enlace: str = "") -> bool:
    """True si el correo salió por SMTP; False si no hay SMTP o falló (el enlace se registra para el administrador)."""
    if not cfg.get("SMTP_HOST"):
        log.warning("[correo no enviado: sin SMTP] para=%s asunto=%s enlace=%s", destino, asunto, enlace)
        return False
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = cfg.get("SMTP_FROM") or cfg.get("SMTP_USER"), destino, asunto
    msg.set_content(texto)
    try:
        ctx = ssl.create_default_context()
        if cfg.get("SMTP_SSL"):
            srv = smtplib.SMTP_SSL(cfg["SMTP_HOST"], cfg["SMTP_PORT"], context=ctx, timeout=15)
        else:
            srv = smtplib.SMTP(cfg["SMTP_HOST"], cfg["SMTP_PORT"], timeout=15)
            srv.starttls(context=ctx)
        with srv:
            if cfg.get("SMTP_USER"):
                srv.login(cfg["SMTP_USER"], cfg["SMTP_PASSWORD"])
            srv.send_message(msg)
        return True
    except Exception as e:      # un fallo de correo nunca debe tumbar el registro ni el restablecimiento
        log.error("No se pudo enviar el correo a %s: %s | enlace=%s", destino, e, enlace)
        return False
