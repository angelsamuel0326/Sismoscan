"""Respaldo de SismoScan.  Uso:  python tools/respaldo.py [carpeta_destino]

SQLite: copia consistente de la base (API de respaldo en caliente, incluye las miniaturas guardadas en ella).
PostgreSQL: usa pg_dump (debe estar instalado):  pg_dump "$DATABASE_URL" -Fc -f respaldo.dump
Programa esto con cron / una tarea programada y guarda los archivos fuera del servidor.
"""
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def respaldar(destino: str | os.PathLike | None = None) -> Path:
    destino = Path(destino or RAIZ / "respaldos"); destino.mkdir(parents=True, exist_ok=True)
    marca = time.strftime("%Y%m%d_%H%M%S")
    url = os.environ.get("DATABASE_URL", "")
    if url:
        if not shutil.which("pg_dump"):
            raise SystemExit("Falta pg_dump (instala postgresql-client).")
        salida = destino / f"sismoscan_{marca}.dump"
        subprocess.run(["pg_dump", url, "-Fc", "-f", str(salida)], check=True)
        return salida
    origen = Path(os.environ.get("DATABASE_PATH") or RAIZ / "instance" / "sismoscan.db")
    if not origen.exists():
        raise SystemExit(f"No existe la base: {origen}")
    salida = destino / f"sismoscan_{marca}.db"
    a, b = sqlite3.connect(origen), sqlite3.connect(salida)
    with b:
        a.backup(b)
    a.close(); b.close()
    os.chmod(salida, 0o600)
    return salida


if __name__ == "__main__":
    print("Respaldo creado:", respaldar(sys.argv[1] if len(sys.argv) > 1 else None))
