# Despliegue en Render (HTTPS) — SismoScan

1. Sube el proyecto a GitHub (sin `.env` ni `instance/`).
2. En Render: **New → Blueprint** y elige el repositorio. `render.yaml` crea el servicio web y PostgreSQL.
3. Variables a completar (Environment): `PUBLIC_BASE_URL` (la URL https de Render), `OPENAI_API_KEY` (opcional), SMTP (`SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`) para correos de verificación/recuperación, `SENTRY_DSN` (opcional).
4. Con `APP_ENV=production` la app **no arranca** si falta `SECRET_KEY` (≥32 caracteres), si `COOKIE_SECURE` no es 1 o si `MOSTRAR_ENLACES_DEMO` es 1.
5. Prueba tras desplegar: `/healthz`, registro → correo de verificación, "¿Olvidaste tu contraseña?", subir una foto desde el celular (la cámara solo funciona en HTTPS), chat.
6. Respaldos: `python tools/respaldo.py` (SQLite) o `pg_dump "$DATABASE_URL" -Fc -f respaldo.dump` (PostgreSQL). Prográmalo y guarda copias fuera del servidor.

Notas honestas
- El limitador de intentos está en memoria: con varios workers cada uno cuenta por separado. Para uso real usa Redis.
- El plan gratuito de Render duerme el servicio y puede caducar la base: revisa sus condiciones vigentes.
- PostgreSQL y OpenAI no se han probado en vivo desde el entorno de desarrollo (solo SQLite y motor local).
