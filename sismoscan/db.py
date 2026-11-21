"""Acceso a la base de datos con dos motores intercambiables.

· SQLite (por defecto, sin instalar nada): DATABASE_PATH.
· PostgreSQL (producción): DATABASE_URL=postgresql://usuario:clave@host/db  (requiere «psycopg»).

El resto de la app solo usa `get_db()` y los métodos de `Conexion` (execute / insertar / commit), de modo que
migrar de motor no exige tocar `repo.py`. Los marcadores son «?» y se traducen a «%s» para PostgreSQL.
"""
import sqlite3

from flask import current_app, g

# Plantilla común; {ID} y {BLOB} cambian según el motor.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id {ID},
  nombre TEXT NOT NULL,
  correo TEXT NOT NULL UNIQUE,
  clave_hash TEXT NOT NULL,
  creado TEXT NOT NULL,
  verificado INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS tokens(               -- restablecer clave / verificar correo (solo se guarda el hash)
  id {ID},
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  tipo TEXT NOT NULL,
  token_hash TEXT NOT NULL UNIQUE,
  expira BIGINT NOT NULL,
  usado INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sessions(            -- permite revocar el JWT al cerrar sesión
  jti TEXT PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expira BIGINT NOT NULL,
  revocada INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS analyses(
  id {ID},
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  creado TEXT NOT NULL,
  entrada TEXT NOT NULL,                        -- JSON: contexto + medidas
  resultado TEXT NOT NULL,                      -- JSON: salida del motor de reglas
  miniatura {BLOB},                             -- JPEG reducido, sin EXIF (opcional)
  deteccion {BLOB},                             -- PNG con la grieta detectada (opcional)
  share_token TEXT,                             -- enlace público revocable (opcional)
  caso_id BIGINT,                               -- caso (inmueble) al que pertenece: id del primer análisis del caso, NULL si es la raíz
  grieta_id BIGINT                              -- misma grieta medida de nuevo: id del primer análisis de la serie, NULL si es la raíz
);
CREATE TABLE IF NOT EXISTS chat_messages(
  id {ID},
  analysis_id BIGINT NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  rol TEXT NOT NULL,                            -- 'user' | 'assistant'
  texto TEXT NOT NULL,
  creado TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_analyses_user ON analyses(user_id, id);
CREATE INDEX IF NOT EXISTS ix_chat_analysis ON chat_messages(analysis_id, id);
"""


def _es_pg(cfg) -> bool:
    return bool(cfg.get("DATABASE_URL"))


def _url_pg(cfg) -> str:
    u = cfg["DATABASE_URL"]
    return "postgresql://" + u[len("postgres://"):] if u.startswith("postgres://") else u   # Render entrega «postgres://»


class Conexion:
    """Envoltura mínima que unifica sqlite3 y psycopg."""

    def __init__(self, raw, pg: bool):
        self.raw, self.pg = raw, pg

    def execute(self, sql: str, params=()):
        if self.pg:
            sql = sql.replace("?", "%s")
        return self.raw.execute(sql, params)

    def insertar(self, sql: str, params=()) -> int:
        """INSERT que devuelve el id generado."""
        if self.pg:
            return self.execute(sql + " RETURNING id", params).fetchone()["id"]
        return self.execute(sql, params).lastrowid

    def commit(self):
        self.raw.commit()

    def close(self):
        self.raw.close()


def _conectar(cfg) -> Conexion:
    if _es_pg(cfg):
        import psycopg                                   # import tardío: solo se exige si se usa PostgreSQL
        from psycopg.rows import dict_row
        return Conexion(psycopg.connect(_url_pg(cfg), row_factory=dict_row), True)
    con = sqlite3.connect(cfg["DATABASE_PATH"], timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA journal_mode=WAL")
    return Conexion(con, False)


def get_db() -> Conexion:
    if "db" not in g:
        g.db = _conectar(current_app.config)
    return g.db


def close_db(_exc=None):
    con = g.pop("db", None)
    if con is not None:
        con.close()


def init_db(app):
    cfg = app.config
    con = _conectar(cfg)
    pg = con.pg
    esquema = _SCHEMA.format(ID="BIGSERIAL PRIMARY KEY" if pg else "INTEGER PRIMARY KEY", BLOB="BYTEA" if pg else "BLOB")
    for sentencia in [x.strip() for x in esquema.split(";") if x.strip()]:
        con.execute(sentencia)
    # Migración ligera para bases creadas con versiones anteriores
    if pg:
        con.execute("ALTER TABLE analyses ADD COLUMN IF NOT EXISTS share_token TEXT")
        con.execute("ALTER TABLE analyses ADD COLUMN IF NOT EXISTS caso_id BIGINT")
        con.execute("ALTER TABLE analyses ADD COLUMN IF NOT EXISTS grieta_id BIGINT")
        con.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS verificado INTEGER NOT NULL DEFAULT 0")
    else:
        if "verificado" not in [r["name"] for r in con.execute("PRAGMA table_info(users)")]:
            con.execute("ALTER TABLE users ADD COLUMN verificado INTEGER NOT NULL DEFAULT 0")
        cols = [r["name"] for r in con.execute("PRAGMA table_info(analyses)")]
        if "share_token" not in cols:
            con.execute("ALTER TABLE analyses ADD COLUMN share_token TEXT")
        for c in ("caso_id", "grieta_id"):
            if c not in cols:
                con.execute(f"ALTER TABLE analyses ADD COLUMN {c} BIGINT")
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_analyses_share ON analyses(share_token)")
    con.execute("CREATE INDEX IF NOT EXISTS ix_analyses_caso ON analyses(caso_id)")
    con.execute("CREATE INDEX IF NOT EXISTS ix_analyses_grieta ON analyses(grieta_id)")
    con.commit()
    con.close()


def init_app(app):
    app.teardown_appcontext(close_db)
    init_db(app)
