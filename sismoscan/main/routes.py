"""Páginas de la aplicación (renderizadas en el servidor con Jinja2)."""
import math
from datetime import datetime, timezone

import json
from pathlib import Path

from flask import (Blueprint, Response, abort, make_response, current_app, flash, g, redirect, render_template, request,
                   send_from_directory, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from .. import chat, repo, report
from ..security import limitar
from ..analysis import rules
from ..security import cerrar_sesion, login_required

bp = Blueprint("main", __name__)


def _fecha(valor: str) -> datetime:
    return datetime.strptime(valor, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


@bp.app_template_filter("fecha")
def filtro_fecha(valor, formato="%d/%m/%Y %H:%M"):
    """Las fechas se guardan en UTC; se muestran en la zona horaria configurada (Bogotá por defecto)."""
    return fecha_local(valor, formato)


def fecha_local(valor, formato="%d/%m/%Y %H:%M"):
    try:
        from zoneinfo import ZoneInfo
        return _fecha(valor).astimezone(ZoneInfo(current_app.config["TIMEZONE"])).strftime(formato)
    except Exception:          # sin base de datos de zonas horarias: mostrar UTC
        return _fecha(valor).strftime(formato) + " UTC"


@bp.app_template_filter("fecha_iso")
def fecha_iso(valor):
    return fecha_local(valor, "%Y-%m-%d").replace(" UTC", "")


@bp.app_template_filter("cm")
def filtro_cm(mm):
    return f"{mm / 10:.1f}".replace(".", ",")


@bp.app_template_filter("cos")
def filtro_cos(grados):
    return math.cos(math.radians(grados))


@bp.app_template_filter("sin")
def filtro_sin(grados):
    return math.sin(math.radians(grados))


@bp.app_template_filter("coma")
def filtro_coma(v):
    return str(v).replace(".", ",")


@bp.route("/")
def inicio():
    return redirect(url_for("main.panel" if g.user else "auth.ingresar"))


@bp.route("/panel")
@login_required
def panel():
    analisis = repo.listar_analisis(g.user["id"])
    sem = [a["resultado"]["semaforo"] for a in analisis]
    stats = {"total": len(analisis), "rojos": sem.count("rojo"), "amarillos": sem.count("amarillo"), "verdes": sem.count("verde"),
             "promedio": round(sum(a["resultado"]["indice"] for a in analisis) / len(analisis)) if analisis else 0}
    tendencia = [a["resultado"]["indice"] for a in reversed(analisis[:12])]
    return render_template("panel.html", analisis=analisis[:5], stats=stats, tendencia=tendencia)


@bp.route("/analizar")
@login_required
def analizar():
    previo = None
    for clave in ("remedir", "otra"):
        if request.args.get(clave, "").isdigit():
            a = repo.obtener_analisis(g.user["id"], int(request.args[clave]))
            if a:
                e = a["entrada"]
                previo = {"modo": clave, "id": a["id"], "fecha": fecha_local(a["creado"]),
                          "entrada": {k: e.get(k) for k in ("elemento", "material", "ancho_cat", "patron", "sismo_reciente", "senales",
                                                            "grupo_uso", "anio", "ubicacion")}}
            break
    guia_img = (Path(current_app.static_folder) / "img" / "guia-regla.png").is_file()
    return render_template("analizar.html", R=rules, previo=previo, guia_img=guia_img)


@bp.route("/resultados/<int:aid>")
@login_required
def resultado(aid):
    a = repo.obtener_analisis(g.user["id"], aid)
    if not a:
        abort(404, description="No encontramos ese análisis.")
    serie = repo.serie_grieta(g.user["id"], repo.clave_grieta(a))
    caso = repo.analisis_caso(g.user["id"], repo.clave_caso(a))
    return render_template("resultado.html", cb_aid=aid, a=a, R=rules, serie=serie, caso=caso, graficas=grafica_evolucion(serie) if len(serie) > 1 else None, mensajes=repo.listar_mensajes(g.user["id"], aid),
                           sugerencias=chat.SUGERENCIAS, enlace=_enlace_publico(a), pie_chat=chat.PIE)


def _enlace_publico(a):
    """URL absoluta del enlace compartido (None si no se está compartiendo)."""
    if not a.get("share_token"):
        return None
    base = current_app.config.get("PUBLIC_BASE_URL", "").rstrip("/")
    ruta = url_for("main.compartido", token=a["share_token"])
    return (base + ruta) if base else url_for("main.compartido", token=a["share_token"], _external=True)


_NIVEL = {"verde": 0, "amarillo": 1, "rojo": 2}


def grafica_evolucion(serie):
    """Puntos listos para dibujar (SVG 300×125) de longitud e índice de una serie de mediciones de la misma grieta."""
    n = len(serie)
    def num(v):
        return f"{v:.1f}".rstrip("0").rstrip(".")
    out = []
    for etiqueta, extraer, tope, trazo, relleno in (
            ("Longitud (cm)", lambda a: a["resultado"]["medidas"]["largo_mm"] / 10, None, "stroke-brand-500", "fill-brand-500"),
            ("Índice de severidad (0–100)", lambda a: a["resultado"]["indice"], 100, "stroke-amber-500", "fill-amber-500")):
        vals = [extraer(a) for a in serie]
        t = tope or max(max(vals) * 1.15, 1)
        pts = []
        for i, (a, v) in enumerate(zip(serie, vals)):
            x = 30 + i * 250 / max(n - 1, 1)
            pts.append({"x": round(x, 1), "y": round(100 - v / t * 80, 1), "v": num(v), "fecha": fecha_local(a["creado"]),
                        "corta": fecha_local(a["creado"], "%d/%m")})
        out.append({"etiqueta": etiqueta, "tope": num(t), "puntos": pts, "linea": " ".join(f"{p['x']},{p['y']}" for p in pts),
                    "trazo": trazo, "relleno": relleno, "resumen": f"de {num(vals[0])} a {num(vals[-1])}"})
    return out


@bp.route("/caso/<int:clave>")
@login_required
def caso(clave):
    """Un inmueble con varias grietas. El semáforo del caso es el PEOR de sus grietas (criterio conservador)."""
    todos = repo.analisis_caso(g.user["id"], clave)
    if not todos:
        abort(404, description="No encontramos ese caso.")
    grietas = {}
    for a in todos:
        grietas.setdefault(repo.clave_grieta(a), []).append(a)
    grietas = list(grietas.values())                       # cada una, de la más antigua a la más reciente
    peor = max((s[-1]["resultado"]["semaforo"] for s in grietas), key=_NIVEL.get)
    return render_template("caso.html", clave=clave, grietas=grietas, peor=peor,
                           graficas=[grafica_evolucion(s) if len(s) > 1 else None for s in grietas],
                           ubicacion=next((a["entrada"].get("ubicacion") for a in todos if a["entrada"].get("ubicacion")), ""))


@bp.route("/historial.csv")
@login_required
def historial_csv():
    import csv, io
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["id", "fecha", "elemento", "material", "semaforo", "indice", "decision", "largo_cm", "angulo_grados", "orientacion", "ancho"])
    def seguro(v):                       # evita inyección de fórmulas al abrir en Excel
        v = str(v); return "'" + v if v[:1] in "=+-@" else v
    for a in repo.listar_analisis(g.user["id"], 1000):
        r, e = a["resultado"], a["entrada"]; m = r["medidas"]
        w.writerow([a["id"], fecha_local(a["creado"], "%Y-%m-%d %H:%M"), seguro(e.get("elemento", "")), seguro(e.get("material", "")), r["semaforo"], r["indice"],
                    seguro(r["decision"]), round(m["largo_mm"] / 10, 1), round(m["angulo_deg"]), m["orientacion"], m.get("ancho_cat", "")])
    resp = make_response("\ufeff" + buf.getvalue())      # BOM: Excel lee bien las tildes
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    resp.headers["Content-Disposition"] = "attachment; filename=sismoscan_historial.csv"
    return resp


@bp.route("/comparar")
@login_required
def comparar():
    try:
        ids = [int(request.args.get("a", "")), int(request.args.get("b", ""))]
    except ValueError:
        abort(400, description="Elige dos análisis para comparar.")
    if ids[0] == ids[1]:
        abort(400, description="Elige dos análisis distintos.")
    filas = [repo.obtener_analisis(g.user["id"], i) for i in ids]
    if not all(filas):
        abort(404, description="No encontramos uno de los análisis.")
    ant, nue = sorted(filas, key=lambda x: x["id"])
    ma, mn = ant["resultado"]["medidas"], nue["resultado"]["medidas"]
    d_largo = round((mn["largo_mm"] - ma["largo_mm"]) / 10, 1)
    d_ind = nue["resultado"]["indice"] - ant["resultado"]["indice"]
    pct = round(100 * d_largo * 10 / ma["largo_mm"]) if ma["largo_mm"] else 0
    if d_largo > 0 and (pct >= 10 or d_ind >= 5):
        veredicto = ("crece", "La grieta parece haber crecido. Si la medida es confiable, pide una revisión profesional pronto.")
    elif d_largo < 0 and pct <= -10:
        veredicto = ("menor", "La medida es menor. Revisa que las fotos y la referencia sean comparables; una grieta no suele encogerse.")
    else:
        veredicto = ("estable", "No hay un cambio claro. Sigue midiendo con la misma referencia y desde el mismo punto.")
    return render_template("comparar.html", ant=ant, nue=nue, d_largo=d_largo, pct=pct, d_ind=d_ind,
                           d_ang=round(mn["angulo_deg"] - ma["angulo_deg"]), veredicto=veredicto)


@bp.route("/resultados/<int:aid>/informe.pdf")
@login_required
def informe_pdf(aid):
    """Informe técnico preliminar descargable."""
    a = repo.obtener_analisis(g.user["id"], aid)
    if not a:
        abort(404, description="No encontramos ese análisis.")
    pdf = report.generar_pdf(a, repo.imagen_analisis(g.user["id"], aid, "miniatura"), repo.imagen_analisis(g.user["id"], aid, "deteccion"),
                             g.user["nombre"], fecha_local(a["creado"], "%d/%m/%Y %H:%M"),
                             serie=repo.serie_grieta(g.user["id"], repo.clave_grieta(a)), emitido_txt=fecha_local(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), "%d/%m/%Y %H:%M"),
                             fecha_fn=lambda v: fecha_local(v, "%d/%m/%Y"))
    return Response(pdf, mimetype="application/pdf", headers={"Content-Disposition": f'attachment; filename="SismoScan_Informe_SS-{aid:06d}.pdf"',
                                                              "Cache-Control": "no-store"})


@bp.post("/resultados/<int:aid>/compartir")
@login_required
def compartir(aid):
    if repo.activar_compartir(g.user["id"], aid) is None:
        abort(404, description="No encontramos ese análisis.")
    # Un formulario no puede saltar a wa.me: la CSP (form-action 'self') bloquea esa redirección en Chrome.
    # Por eso solo se crea el enlace y se vuelve al resultado, donde el botón de WhatsApp ya es un enlace directo.
    if request.form.get("destino") == "whatsapp":
        flash("Enlace creado. Toca «Informe por WhatsApp» otra vez para enviarlo.", "ok")
        return redirect(url_for("main.resultado", aid=aid) + "#compartir")
    flash("Enlace público creado. Cualquiera que lo tenga puede ver el resumen (sin foto ni datos personales).", "ok")
    return redirect(url_for("main.resultado", aid=aid) + "#compartir")


@bp.post("/resultados/<int:aid>/dejar-de-compartir")
@login_required
def dejar_de_compartir(aid):
    repo.desactivar_compartir(g.user["id"], aid)
    flash("El enlace público ya no funciona.", "ok")
    return redirect(url_for("main.resultado", aid=aid) + "#compartir")


@bp.route("/c/<token>")
@limitar("compartido", 120, 600, metodos=("GET",))
def compartido(token):
    """Resumen público de solo lectura: sin foto, sin nombre y sin ubicación del inmueble."""
    a = repo.analisis_por_token(token)
    if not a:
        abort(404, description="Este enlace no existe o ya no está activo.")
    resp = Response(render_template("compartido.html", a=a, R=rules))
    resp.headers["X-Robots-Tag"] = "noindex, nofollow"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


@bp.route("/c/<token>/informe.pdf")
@limitar("compartido", 60, 600, metodos=("GET",))
def compartido_pdf(token):
    """Informe técnico público (sin foto, sin nombre y sin ubicación)."""
    a = repo.analisis_por_token(token)
    if not a:
        abort(404, description="Este enlace no existe o ya no está activo.")
    a = {**a, "entrada": {**a["entrada"], "ubicacion": ""}}
    pdf = report.generar_pdf(a, None, None, "Usuario de SismoScan (compartido)", fecha_local(a["creado"], "%d/%m/%Y %H:%M"))
    return Response(pdf, mimetype="application/pdf", headers={"Content-Disposition": f'inline; filename="SismoScan_Informe_{a["id"]:06d}.pdf"',
                                                              "Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow"})


@bp.post("/resultados/<int:aid>/eliminar")
@login_required
def eliminar(aid):
    if repo.borrar_analisis(g.user["id"], aid):
        flash("Análisis eliminado.", "ok")
    return redirect(url_for("main.historial"))


@bp.route("/historial")
@login_required
def historial():
    return render_template("historial.html", analisis=repo.listar_analisis(g.user["id"]))


@bp.route("/imagenes/<int:aid>/<tipo>")
@login_required
def imagen(aid, tipo):
    campo = {"miniatura": "miniatura", "deteccion": "deteccion"}.get(tipo)
    datos = repo.imagen_analisis(g.user["id"], aid, campo) if campo else None
    if not datos:
        abort(404)
    return Response(datos, mimetype="image/jpeg" if campo == "miniatura" else "image/png",
                    headers={"Cache-Control": "private, max-age=3600"})


@bp.route("/privacidad")
def privacidad():
    return render_template("legal_privacidad.html")


@bp.route("/terminos")
def terminos():
    return render_template("legal_terminos.html")


@bp.route("/acerca")
def acerca():
    return render_template("acerca.html")


@bp.route("/ayuda")
def ayuda():
    return render_template("ayuda.html")


@bp.route("/metodologia")
def metodologia():
    return render_template("metodologia.html", R=rules, banco=_resultados_banco())


def _resultados_banco():
    """Métricas del banco de pruebas (las genera tools/evaluar_banco.py). None si aún no se han calculado."""
    ruta = Path(current_app.root_path).parent / "tests" / "banco" / "resultados.json"
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# ---- PWA: manifest y service worker en la raíz para que el alcance sea todo el sitio ----
@bp.route("/manifest.json")
def manifest():
    r = send_from_directory(current_app.static_folder, "manifest.json", mimetype="application/manifest+json")
    r.headers["Cache-Control"] = "public, max-age=3600"
    return r


@bp.route("/service-worker.js")
@bp.route("/sw.js")
def service_worker():
    r = send_from_directory(current_app.static_folder, "service-worker.js", mimetype="text/javascript")
    r.headers["Cache-Control"] = "no-cache"
    r.headers["Service-Worker-Allowed"] = "/"
    return r


@bp.route("/offline")
def offline():
    return render_template("offline.html")


@bp.route("/healthz")
def healthz():
    return {"ok": True}


# ---------------- cuenta y perfil ----------------
@bp.route("/cuenta")
@login_required
def cuenta():
    return render_template("cuenta.html", total=len(repo.listar_analisis(g.user["id"], 10000)))


@bp.post("/cuenta/nombre")
@login_required
def cuenta_nombre():
    nombre = " ".join(request.form.get("nombre", "").split())
    if not 2 <= len(nombre) <= 80:
        flash("Escribe un nombre de entre 2 y 80 caracteres.", "error")
    else:
        repo.actualizar_nombre(g.user["id"], nombre)
        flash("Nombre actualizado.", "ok")
    return redirect(url_for("main.cuenta"))


@bp.post("/cuenta/clave")
@login_required
@limitar("cambiar_clave", 8, 3600)
def cuenta_clave():
    from ..auth.routes import _validar_clave
    u = repo.usuario_por_correo(g.user["correo"])
    nueva = request.form.get("nueva", "")
    err = None
    if not check_password_hash(u["clave_hash"], request.form.get("actual", "")):
        err = "La contraseña actual no es correcta."
    elif _validar_clave(nueva, g.user["correo"]):
        err = _validar_clave(nueva, g.user["correo"])
    elif nueva != request.form.get("nueva2", ""):
        err = "Las contraseñas nuevas no coinciden."
    if err:
        flash(err, "error")
        return redirect(url_for("main.cuenta"))
    repo.cambiar_clave(g.user["id"], generate_password_hash(nueva))
    flash("Contraseña cambiada. Se cerraron todas las sesiones; inicia sesión de nuevo.", "ok")
    return cerrar_sesion(redirect(url_for("auth.ingresar")))


@bp.route("/cuenta/exportar.json")
@login_required
@limitar("exportar", 10, 3600, metodos=("GET",))
def cuenta_exportar():
    datos = json.dumps(repo.exportar_datos(g.user["id"]), ensure_ascii=False, indent=2)
    return Response(datos, mimetype="application/json", headers={"Content-Disposition": "attachment; filename=sismoscan_mis_datos.json", "Cache-Control": "no-store"})


@bp.post("/cuenta/eliminar")
@login_required
@limitar("eliminar_cuenta", 5, 3600)
def cuenta_eliminar():
    u = repo.usuario_por_correo(g.user["correo"])
    if request.form.get("confirmacion", "").strip().upper() != "ELIMINAR" or not check_password_hash(u["clave_hash"], request.form.get("clave", "")):
        flash("No se eliminó la cuenta: escribe ELIMINAR y tu contraseña actual correctamente.", "error")
        return redirect(url_for("main.cuenta"))
    repo.borrar_usuario(g.user["id"])
    flash("Tu cuenta y todos tus datos fueron eliminados.", "ok")
    return cerrar_sesion(redirect(url_for("auth.ingresar")))
