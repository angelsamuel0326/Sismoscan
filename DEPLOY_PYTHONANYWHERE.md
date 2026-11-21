# Publicar SismoScan en PythonAnywhere (cuenta gratis)

Tu dirección quedará: `https://TUUSUARIO.pythonanywhere.com` (HTTPS incluido, necesario para instalar la app en el celular).
Cambia **TUUSUARIO** por tu nombre de usuario en todos los comandos.

## 1. Subir el proyecto
1. Pestaña **Files** → **Upload a file** → sube `sismoscan-final.zip`.
2. Pestaña **Consoles** → **Bash** y escribe:
   ```bash
   cd ~ && unzip -q sismoscan-final.zip && ls m
   ```
   Debes ver `wsgi.py`, `sismoscan`, `requirements-pythonanywhere.txt`, etc. El proyecto queda en `/home/TUUSUARIO/m`.

## 2. Instalar las librerías (entorno virtual)
```bash
mkvirtualenv --python=python3.12 sismoscan
cd ~/m
pip install --no-cache-dir -r requirements-pythonanywhere.txt
```
(`--no-cache-dir` ahorra espacio: la cuenta gratis tiene 512 MB.) Si `python3.12` no existe, prueba `python3.11` o `python3.13`.

## 3. Crear el archivo `.env` (secretos; nunca va en el zip)
```bash
cd ~/m
python -c "import secrets;print(secrets.token_hex(32))"
nano .env
```
Pega esto, cambiando la clave por la que acaba de imprimir y TUUSUARIO por el tuyo:
```
APP_ENV=production
SECRET_KEY=PEGA_AQUI_LA_CLAVE_LARGA
COOKIE_SECURE=1
TRUST_PROXY=1
MOSTRAR_ENLACES_DEMO=0
PUBLIC_BASE_URL=https://TUUSUARIO.pythonanywhere.com
TIMEZONE=America/Bogota
# IA opcional (déjalo vacío para usar solo la detección local y el chat por reglas)
# OPENAI_API_KEY=
```
Guarda con `Ctrl+O`, Enter y sal con `Ctrl+X`. Usa una clave de OpenAI **nueva** (la anterior que se filtró debes revocarla).

## 4. Configurar la web app
1. Pestaña **Web** → **Add a new web app** → **Manual configuration** → Python 3.12 (la misma versión del paso 2).
2. En **Virtualenv** escribe: `/home/TUUSUARIO/.virtualenvs/sismoscan`
3. En **Code → WSGI configuration file** abre el enlace (`/var/www/TUUSUARIO_pythonanywhere_com_wsgi.py`), borra todo y pega:
   ```python
   import sys
   ruta = "/home/TUUSUARIO/m"
   if ruta not in sys.path:
       sys.path.insert(0, ruta)
   from wsgi import app as application
   ```
4. Pulsa **Reload** (botón verde arriba) y abre `https://TUUSUARIO.pythonanywhere.com`.

## 5. Probar
- En el portátil: regístrate, haz un análisis y revisa el resultado, el chat y el PDF.
- En el celular (Chrome): abre la dirección, haz un análisis con la cámara y toca **Instalar app** (o menú ⋮ → «Instalar aplicación»).
- Si algo falla: pestaña **Web** → **Error log**.

## 6. Mantenimiento
- La app gratis **expira si no la usas en un mes**: entra a la pestaña **Web** y pulsa **Run until 1 month from today**. Hazlo antes de la exposición.
- Haz una copia de `~/m/instance/sismoscan.db` de vez en cuando (es tu base de datos).
- Para actualizar: sube el zip nuevo, descomprímelo **sin borrar** `.env` ni `instance/`, y pulsa **Reload**.
- En la cuenta gratis, las conexiones a internet externas están limitadas a una lista de sitios permitidos; la IA de OpenAI debería funcionar, pero compruébalo.
