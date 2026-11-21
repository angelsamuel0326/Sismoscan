<p align="center"><img src="docs/img/logo.png" alt="SismoScan" width="360"></p>

# SismoScan · PWA de evaluación preliminar de grietas

Flask + SQLite/PostgreSQL + OpenCV + ReportLab + Tailwind CSS v4. Proyecto de Introducción a la Ingeniería (USC, ODS 9).
**Orientación preliminar: no reemplaza la inspección de un ingeniero civil/estructural.**

## Estructura
```
app.py, wsgi.py            entradas (flask run / gunicorn)
config.py                  configuración por variables de entorno
sismoscan/
  __init__.py              fábrica create_app, manejo de errores
  db.py, repo.py           SQLite o PostgreSQL (users, sessions, analyses, chat_messages) y consultas
  chat.py                  asistente post-análisis (IA + reglas + guardrails)
  report.py                informe técnico preliminar en PDF
  security.py              JWT en cookie HttpOnly revocable, CSRF, límites de tasa, CSP/cabeceras
  auth/ main/ api/         blueprints: registro/ingreso · páginas y PWA · API /api/v1
  analysis/
    images.py              validación (Pillow), EXIF, reducción, limpieza de metadatos
    geometry.py            trazo + referencia → mm; ángulo y orientación X/Y/diagonal
    rules.py               motor de reglas NSR-10 / UNGRD con factores trazables
    pipeline.py            orquesta: medidas → OpenCV → IA externa → reglas
    vision/                opencv_provider, openai_provider, google_provider
  templates/ static/       Jinja + Tailwind compilado, JS, manifest.json, sw.js, iconos
tools/build_css.mjs        compila Tailwind sin CLI (opcional)
tests/                     unittest (python -m unittest discover -s tests -v)
```

## Funciones
Registro/ingreso · análisis con cámara o galería · medición sobre la foto **o** por ejes X/Y escritos a mano · detección local + IA opcional · semáforo NSR-10/UNGRD · **chat conversacional** sobre el análisis · **informe PDF** · **alerta de emergencia** (resultado rojo) con directorio telefónico · **compartir** por WhatsApp/enlace revocable · historial · PWA instalable.

## Instalación y ejecución local
```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env     # opcional; exporta las variables o usa python-dotenv
python app.py            # http://127.0.0.1:5000
```
La cámara del navegador exige HTTPS salvo en `localhost`. Para probar en el celular usa un túnel HTTPS (p. ej. `cloudflared tunnel --url http://localhost:5000`).

## IA de visión (opcional)
Sin claves funciona con medidas del usuario + detección local OpenCV.
- OpenAI: `OPENAI_API_KEY` (modelo `OPENAI_MODEL`, por defecto `gpt-4o`).
- Google Cloud Vision: `GOOGLE_VISION_API_KEY`.
- `VISION_PROVIDER=auto|openai|google|local`. Al usar un proveedor externo la app lo informa en el consentimiento.

## Estilos (Tailwind)
`static/css/app.css` ya viene compilado. Para regenerarlo con la CLI oficial:
```bash
npm i -D tailwindcss @tailwindcss/cli
npx @tailwindcss/cli -i sismoscan/static/css/input.css -o sismoscan/static/css/app.css --minify
```
(o `node tools/build_css.mjs` si tienes el paquete `tailwindcss` v4 instalado).

## Chat con guardrails
`POST /api/v1/analyses/<id>/chat`. Capas: (1) mensajes de emergencia (heridos, atrapados, gas, colapso…) → respuesta fija con teléfonos, sin IA; (2) con semáforo rojo, preguntas de entrar/sacar cosas → texto fijo; (3) con `OPENAI_API_KEY`, la IA recibe un prompt restrictivo y el análisis como *datos* (el texto del usuario nunca se mezcla con las instrucciones); la respuesta se filtra (nada permisivo con rojo/amarillo) y siempre recomienda un ingeniero; (4) sin clave o si falla, responde el motor local. El chat recibe el **resumen del análisis** (medidas, riesgo y lectura visual), no la imagen.

## Informe PDF y compartir
`GET /resultados/<id>/informe.pdf` (membrete, fecha, foto, ejes X/Y, semáforo, factores, recomendaciones, referencias). El enlace público `/c/<token>` es de solo lectura, **sin foto, sin nombre y sin ubicación**, con `noindex`, y se desactiva cuando quieras.

## Despliegue en Render (con PostgreSQL y HTTPS)
1. Sube el proyecto a un repositorio de GitHub (no subas `.env` ni `instance/`).
2. En Render: **New → Blueprint** → elige el repositorio. Lee `render.yaml` y crea el servicio web y la base `sismoscan-db`; `DATABASE_URL` se enlaza sola y `SECRET_KEY` se genera.
3. En el servicio → **Environment**, agrega `OPENAI_API_KEY` (opcional) y `PUBLIC_BASE_URL=https://<tu-app>.onrender.com`.
4. Render emite el certificado **HTTPS** automáticamente, necesario para la cámara y para instalar la PWA. Abre la URL, regístrate y prueba `/healthz`.
5. Las tablas se crean solas al arrancar. En el plan gratuito el servicio "duerme" tras inactividad (primera carga lenta) y la base gratuita puede tener caducidad: revisa las condiciones vigentes y, para uso real, usa un plan de pago.

Instalar la PWA: en Android (Chrome) botón **Instalar** o menú → *Instalar app*; en iPhone (Safari) **Compartir → Añadir a pantalla de inicio**.

**PythonAnywhere**: crea un virtualenv (`pip install -r requirements.txt`), en *Web → WSGI file* usa `from wsgi import app as application`, define `APP_ENV=production`, `SECRET_KEY`, `COOKIE_SECURE=1` y recarga (SQLite funciona; las cuentas gratuitas limitan las llamadas salientes a IA).

**Netlify**: solo sirve sitios estáticos/funciones; **no puede ejecutar Flask**.

## Probar con PostgreSQL en local
```bash
docker run --name pg -e POSTGRES_PASSWORD=pw -e POSTGRES_DB=sismoscan -p 5432:5432 -d postgres:16
export DATABASE_URL=postgresql://postgres:pw@localhost:5432/sismoscan
python app.py
```
La capa de datos (`db.py`/`repo.py`) usa SQL estándar con marcadores `?` traducidos a `%s`. **No se ha ejecutado contra un PostgreSQL real durante el desarrollo**: pruébalo así antes de la demo.

## Validación con banco de imágenes
`tests/banco/` contiene fotos etiquetadas (`banco.csv`) y `tools/evaluar_banco.py` las evalúa: `python tools/evaluar_banco.py` genera `resultados.md` y `resultados.csv` (acierto del semáforo, matriz de confusión, detección y orientación).
Para agregar fotos: copia el archivo a `tests/banco/`, añade una fila al CSV (contexto, medidas `x_cm`/`y_cm`, orientación y semáforo esperados, quién etiquetó, fuente y licencia) y vuelve a ejecutar.
**Límites:** las etiquetas actuales son un criterio visual preliminar (deben confirmarse con un ingeniero) y las medidas de fotos sin escala son supuestos; por eso el acierto del semáforo mide *consistencia* de las reglas, no exactitud estructural. La detección automática libre (sin trazo) resultó poco fiable en fotos reales —marca bordes, sombras y texturas—, por lo que la app solo la usa cuando el usuario marca la grieta sobre la foto.

## Seguridad
scrypt para contraseñas · JWT HS256 en cookie HttpOnly/SameSite con `jti` revocable · CSRF · límite de intentos · CSP estricta · validación real de imágenes (no confía en extensión/MIME) · metadatos eliminados · datos aislados por usuario · `next` solo rutas internas.

## Limitaciones
Los umbrales de `rules.py` son valores de prototipo y deben validarse con Ingeniería Civil. La detección local tiene error ≈ ±20 %; la medición del usuario es la autoritativa. Las llamadas reales a OpenAI/Google y la conexión a PostgreSQL no se probaron en el desarrollo (solo simulaciones y SQLite). Los teléfonos de emergencia son los habituales en Colombia (123, 119, 132, 144); verifícalos para tu municipio y cámbialos con `EMERGENCY_JSON`.

## Novedades (cuenta, legal y operación)
- Footer, páginas `/acerca`, `/ayuda`, `/privacidad` (Ley 1581 de 2012), `/terminos`.
- Cuenta: editar nombre, cambiar contraseña, descargar datos (JSON), eliminar cuenta; recuperar contraseña y verificación de correo (SMTP opcional; ver `.env.example`); "Recordarme"; bloqueo tras 5 intentos fallidos; medidor de fuerza de clave.
- Historial: búsqueda, fechas, exportar CSV, comparar dos análisis (`/comparar`).
- Operación: `tools/respaldo.py`, Sentry opcional, validación de producción, `DEPLOY.md`, `tests/e2e_navegador.py` (Playwright).

## Confiabilidad y funciones (v3)
- Semáforo prudente: pisos mínimos en amarillo (ancho ≥ 1 mm; ancho medio en columna/viga, diagonal o ≥ 1 m). Banco ampliado con 6 controles sin grieta; métricas en `/metodologia` (`python tools/evaluar_banco.py`).
- Calidad de foto: borrosa/oscura/sobreexpuesta/plana se rechaza y se pide repetir (navegador y servidor con los mismos umbrales).
- Escala: aviso si la referencia no es creíble, modo «sin referencia» (categoría de tamaño, confianza baja) y «Sugerir referencia con IA» (requiere `OPENAI_API_KEY`; la medida real sale de una tabla del servidor, no del modelo).
- «Medir de nuevo esta grieta» + gráfica de evolución, «Agregar otra grieta» y página de caso (semáforo del caso = el peor).
- Informe PDF con logo, fechas, ubicación, evolución y espacio de revisión/firma del ingeniero.
- Sin conexión: el análisis se prepara y se guarda en el celular (IndexedDB) y se envía solo al volver internet. Pruebas: `tests/e2e_flujos.py`.
