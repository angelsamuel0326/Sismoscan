"""Entrada WSGI para gunicorn (Render) y PythonAnywhere."""
from sismoscan import create_app

app = create_app()
