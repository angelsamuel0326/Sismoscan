"""Consultas a la base de datos (capa de acceso a datos). Compatible con SQLite y PostgreSQL."""
import hashlib
import json
import secrets
import time
from datetime import datetime, timezone

from .db import get_db


def _ahora() -> str:
    """Fecha UTC como texto 'YYYY-MM-DD HH:MM:SS' (igual en ambos motores)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# ---- usuarios ----
def crear_usuario(nombre, correo, clave_hash):
    db = get_db()
    uid = db.insertar("INSERT INTO users(nombre,correo,clave_hash,creado) VALUES(?,?,?,?)", (nombre, correo, clave_hash, _ahora()))
    db.commit()
    return uid


def usuario_por_correo(correo):
    return get_db().execute("SELECT * FROM users WHERE correo=?", (correo,)).fetchone()


def usuario_por_id(uid):
    return get_db().execute("SELECT id,nombre,correo,creado,verificado FROM users WHERE id=?", (uid,)).fetchone()


def actualizar_nombre(uid, nombre):
    db = get_db(); db.execute("UPDATE users SET nombre=? WHERE id=?", (nombre, uid)); db.commit()


def cambiar_clave(uid, clave_hash):
    """Cambia la clave y cierra todas las sesiones abiertas."""
    db = get_db()
    db.execute("UPDATE users SET clave_hash=? WHERE id=?", (clave_hash, uid))
    db.execute("UPDATE sessions SET revocada=1 WHERE user_id=?", (uid,))
    db.commit()


def marcar_verificado(uid):
    db = get_db(); db.execute("UPDATE users SET verificado=1 WHERE id=?", (uid,)); db.commit()


def borrar_usuario(uid):
    """Elimina la cuenta y TODO lo asociado (análisis, fotos, chat, sesiones, tokens)."""
    db = get_db()
    for t, col in (("chat_messages", "user_id"), ("analyses", "user_id"), ("sessions", "user_id"), ("tokens", "user_id"), ("users", "id")):
        db.execute(f"DELETE FROM {t} WHERE {col}=?", (uid,))
    db.commit()


def exportar_datos(uid):
    """Copia de los datos del usuario (habeas data): cuenta, análisis (sin imágenes) y conversaciones."""
    u = usuario_por_id(uid)
    analisis = listar_analisis(uid, 10000)
    for a in analisis:
        a["conversacion"] = listar_mensajes(uid, a["id"], 1000)
    return {"cuenta": {"nombre": u["nombre"], "correo": u["correo"], "creado_utc": u["creado"], "correo_verificado": bool(u["verificado"])},
            "analisis": analisis, "exportado_utc": _ahora(),
            "nota": "Las fotos no se incluyen en esta copia; se eliminan junto con tu cuenta."}


# ---- tokens de un solo uso (restablecer clave / verificar correo) ----
def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def crear_token(uid, tipo, minutos):
    token = secrets.token_urlsafe(32)
    db = get_db()
    db.execute("DELETE FROM tokens WHERE expira < ? OR (user_id=? AND tipo=?)", (int(time.time()), uid, tipo))   # solo uno vigente por tipo
    db.execute("INSERT INTO tokens(user_id,tipo,token_hash,expira) VALUES(?,?,?,?)", (uid, tipo, _hash(token), int(time.time()) + minutos * 60))
    db.commit()
    return token


def token_valido(token, tipo):
    """Devuelve el id de usuario si el token existe, no venció y no se usó; si no, None. No lo consume."""
    if not token or len(token) > 100:
        return None
    r = get_db().execute("SELECT user_id,expira,usado FROM tokens WHERE token_hash=? AND tipo=?", (_hash(token), tipo)).fetchone()
    return r["user_id"] if r and not r["usado"] and r["expira"] > time.time() else None


def consumir_token(token, tipo):
    uid = token_valido(token, tipo)
    if uid:
        db = get_db(); db.execute("UPDATE tokens SET usado=1 WHERE token_hash=?", (_hash(token),)); db.commit()
    return uid


# ---- sesiones JWT ----
def registrar_sesion(jti, uid, expira):
    db = get_db()
    db.execute("DELETE FROM sessions WHERE expira < ?", (int(time.time()),))   # limpieza oportunista
    db.execute("INSERT INTO sessions(jti,user_id,expira) VALUES(?,?,?)", (jti, uid, expira))
    db.commit()


def sesion_valida(jti, uid):
    r = get_db().execute("SELECT revocada,expira FROM sessions WHERE jti=? AND user_id=?", (jti, uid)).fetchone()
    return bool(r) and not r["revocada"] and r["expira"] > time.time()


def revocar_sesion(jti):
    db = get_db()
    db.execute("UPDATE sessions SET revocada=1 WHERE jti=?", (jti,))
    db.commit()


# ---- análisis ----
def guardar_analisis(uid, entrada, resultado, miniatura, deteccion, caso_id=None, grieta_id=None, creado=None):
    db = get_db()
    aid = db.insertar("INSERT INTO analyses(user_id,creado,entrada,resultado,miniatura,deteccion,caso_id,grieta_id) VALUES(?,?,?,?,?,?,?,?)",
                      (uid, creado or _ahora(), json.dumps(entrada, ensure_ascii=False), json.dumps(resultado, ensure_ascii=False), miniatura, deteccion,
                       caso_id, grieta_id))
    db.commit()
    return aid


def _fila(r):
    return {"id": r["id"], "creado": r["creado"], "entrada": json.loads(r["entrada"]), "resultado": json.loads(r["resultado"]),
            "tiene_miniatura": bool(r["tiene_mini"]), "tiene_deteccion": bool(r["tiene_det"]), "share_token": r["share_token"],
            "caso_id": r["caso_id"], "grieta_id": r["grieta_id"]}


_SEL = ("SELECT id,creado,entrada,resultado,share_token,caso_id,grieta_id,miniatura IS NOT NULL AS tiene_mini,deteccion IS NOT NULL AS tiene_det "
        "FROM analyses WHERE ")


def listar_analisis(uid, limite=200):
    return [_fila(r) for r in get_db().execute(_SEL + "user_id=? ORDER BY id DESC LIMIT ?", (uid, limite))]


def obtener_analisis(uid, aid):
    r = get_db().execute(_SEL + "user_id=? AND id=?", (uid, aid)).fetchone()
    return _fila(r) if r else None


def imagen_analisis(uid, aid, campo):
    if campo not in ("miniatura", "deteccion"):
        return None
    r = get_db().execute(f"SELECT {campo} AS b FROM analyses WHERE user_id=? AND id=?", (uid, aid)).fetchone()
    return bytes(r["b"]) if r and r["b"] else None


def borrar_analisis(uid, aid):
    db = get_db()
    cur = db.execute("DELETE FROM analyses WHERE user_id=? AND id=?", (uid, aid))
    db.commit()
    return cur.rowcount > 0


# ---- enlace público revocable ----
def activar_compartir(uid, aid):
    """Genera (o reutiliza) un token aleatorio. Devuelve None si el análisis no es del usuario."""
    a = obtener_analisis(uid, aid)
    if not a:
        return None
    if a["share_token"]:
        return a["share_token"]
    token = secrets.token_urlsafe(16)
    db = get_db()
    db.execute("UPDATE analyses SET share_token=? WHERE user_id=? AND id=?", (token, uid, aid))
    db.commit()
    return token


def desactivar_compartir(uid, aid):
    db = get_db()
    db.execute("UPDATE analyses SET share_token=NULL WHERE user_id=? AND id=?", (uid, aid))
    db.commit()


def analisis_por_token(token):
    if not token or len(token) > 64:
        return None
    r = get_db().execute(_SEL + "share_token=?", (token,)).fetchone()
    return _fila(r) if r else None


# ---- chat ----
def guardar_mensaje(uid, aid, rol, texto):
    db = get_db()
    db.insertar("INSERT INTO chat_messages(analysis_id,user_id,rol,texto,creado) VALUES(?,?,?,?,?)", (aid, uid, rol, texto, _ahora()))
    db.commit()


def listar_mensajes(uid, aid, limite=60):
    filas = get_db().execute("SELECT rol,texto,creado FROM chat_messages WHERE user_id=? AND analysis_id=? ORDER BY id DESC LIMIT ?", (uid, aid, limite)).fetchall()
    return [{"rol": r["rol"], "texto": r["texto"], "creado": r["creado"]} for r in reversed(filas)]


def contar_mensajes_usuario(uid, aid):
    return get_db().execute("SELECT COUNT(*) AS n FROM chat_messages WHERE user_id=? AND analysis_id=? AND rol='user'", (uid, aid)).fetchone()["n"]


# ---------------- casos (un inmueble, varias grietas) y series (la misma grieta medida de nuevo) ----------------
def clave_caso(a) -> int:
    return a["caso_id"] or a["id"]


def clave_grieta(a) -> int:
    return a["grieta_id"] or a["id"]


def serie_grieta(uid, clave):
    """Mediciones de una misma grieta, de la más antigua a la más reciente."""
    filas = get_db().execute(_SEL + "user_id=? AND (id=? OR grieta_id=?) ORDER BY creado, id", (uid, clave, clave))
    return [_fila(r) for r in filas]


def analisis_caso(uid, clave):
    filas = get_db().execute(_SEL + "user_id=? AND (id=? OR caso_id=?) ORDER BY creado, id", (uid, clave, clave))
    return [_fila(r) for r in filas]
