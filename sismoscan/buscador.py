"""Buscador de la base de conocimiento de Sisma (sin dependencias, sin internet, sin clave).

Compara el mensaje con ~1400 formas de preguntar (kb/conocimiento.json) usando TF-IDF sobre raíces de palabras y
pares de palabras, con sinónimos del habla colombiana («rajadura» = grieta, «temblor» = sismo) y corrección de
errores de tecleo. Devuelve la respuesta más parecida solo si la coincidencia es confiable; si no, sugiere preguntas."""
import difflib
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

RUTA = Path(__file__).with_name("kb") / "conocimiento.json"

STOP = set("""a al algo algun alguna algunas alguno algunos ante antes asi aun aqui bien cada como con contra cual cuales cuando de del desde donde dos el ella ellas ello ellos en entre era eran eres es esa esas ese eso esos esta estan estar estas este esto estos fue fueron ha hace hacer han hasta hay la las le les lo los mas me mi mis mucho muy nos o os otra otro para pero poco por porque pues que quien quienes se ser si sin sobre su sus tambien te tengo ti tiene tienen todo todos tu tus un una unas uno unos usted va vamos van vez voy y ya yo quiero quisiera saber necesito necesitaba favor porfa porfavor dime decir digame explicame cuentame podria puedes puede pueden sera seria""".split())

# palabra normalizada → forma canónica (antes de aplicar la raíz)
SIN = {}
for canon, palabras in {
    "grieta": "grietas fisura fisuras rajadura rajaduras rajon rajones raja rajas rajo rajada rajado rajar rajarse rajo cuarteadura cuarteaduras cuarteo hendidura hendiduras abertura aberturas quiebre quiebres rotura roturas rompio rompe resquebrajadura resquebrajada fractura fracturas agrietado agrietada agrietados agrietadas agrieta agrietar agrietarse agrietamiento agrietamientos",
    "sismo": "sismos temblor temblores terremoto terremotos movimiento telurico sacudon sacudida remezon remezones tembló temblo tiembla temblando",
    "muro": "muros pared paredes tabique tabiques muralla",
    "edificio": "edificios edificacion edificaciones inmueble inmuebles vivienda viviendas construccion construcciones estructura estructuras",
    "ingeniero": "ingenieros ingeniera ingenieras ingenieria",
    "columna": "columnas pilar pilares",
    "peligroso": "peligrosa peligrosos peligrosas peligro peligros riesgoso riesgosa riesgo riesgos grave graves",
    "reparar": "reparo reparacion reparaciones arreglar arreglo arreglos arreglarla arreglarlo componer remendar resanar resane",
    "techo": "techos cubierta cubiertas teja tejas cielo raso",
    "ancho": "anchos espesor grosor gruesa grueso gruesas gruesos anchura",
    "largo": "largos longitud longitudes largas larga",
    "foto": "fotos fotografia fotografias imagen imagenes picture",
    "celular": "movil telefono smartphone",
    "llamar": "llamo llamada llamadas contactar avisar",
    "evacuar": "evacuo evacuacion salir salgo huir correr escapar",
    "semaforo": "semaforos colores color",
    "aplicacion": "app apps programa plataforma sitio pagina web",
    "gratis": "gratuita gratuito costo cuesta precio cobran cobrar pagar",
}.items():
    for p in palabras.split():
        SIN[p] = canon


def norm(t: str) -> str:
    t = unicodedata.normalize("NFD", t.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _raiz(w: str) -> str:
    w = SIN.get(w, w)
    if len(w) > 5 and w.endswith("es"):
        w = w[:-2]
    elif len(w) > 4 and w.endswith("s"):
        w = w[:-1]
    return w[:7]


def _tokens(texto: str) -> list[str]:
    ws = re.findall(r"[a-z0-9]+", norm(texto))
    return [w for w in ws if w not in STOP or w in ("no",)]


class _Indice:
    def __init__(self):
        datos = json.loads(RUTA.read_text(encoding="utf-8"))
        self.entradas = {e["id"]: e for e in datos}
        self.docs = []                       # (id_entrada, pregunta, vector)
        df = Counter()
        crudos = []
        for e in datos:
            for q in e["q"]:
                f = self._feats([_raiz(w) for w in _tokens(q)])
                crudos.append((e["id"], q, f))
                df.update(f.keys())
        self.pool = defaultdict(Counter)
        for i, q, f in crudos:
            self.pool[i].update(f)
        N = len(crudos)
        self.idf = {k: math.log((N + 1) / (v + 0.5)) + 1 for k, v in df.items()}
        self.vocab = sorted({k for k in df if " " not in k})
        for i, q, f in crudos:
            self.docs.append((i, q, self._vec(f)))
        self.pvec = {i: self._vec(f) for i, f in self.pool.items()}

    @staticmethod
    def _feats(raices: list[str]) -> Counter:
        f = Counter(raices)
        for a, b in zip(raices, raices[1:]):
            f[a + " " + b] += 1
        return f

    def _vec(self, f: Counter) -> dict:
        v = {k: c * self.idf.get(k, 1.0) * (1.3 if " " in k else 1.0) for k, c in f.items() if k in self.idf}
        norma = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {k: x / norma for k, x in v.items()}

    def consulta(self, texto: str) -> list[tuple[float, str, str]]:
        raices = []
        for w in _tokens(texto):
            r = _raiz(w)
            if r not in self.idf and len(r) > 3:           # error de tecleo: busca la raíz más parecida
                cerca = difflib.get_close_matches(r, self.vocab, n=1, cutoff=0.8)
                if cerca:
                    r = cerca[0]
            raices.append(r)
        v = self._vec(self._feats(raices))
        if not v:
            return []
        mejor = {}
        for i, q, d in self.docs:
            s = _cos(v, d)
            if s > mejor.get(i, (0, ""))[0]:
                mejor[i] = (s, q)
        # puntaje de la entrada: mejor pregunta individual + parecido con todas sus preguntas juntas
        punt = {i: PESO_MAX * s + (1 - PESO_MAX) * _cos(v, self.pvec[i]) for i, (s, q) in mejor.items()}
        return sorted(((p, i, mejor[i][1]) for i, p in punt.items()), reverse=True)[:5]


def _cos(a: dict, c: dict) -> float:
    if len(a) > len(c):
        a, c = c, a
    return sum(x * c.get(k, 0.0) for k, x in a.items())


PESO_MAX = 0.35


_IDX = None


def _indice() -> _Indice:
    global _IDX
    if _IDX is None:
        _IDX = _Indice()
    return _IDX


UMBRAL_SEGURO = 0.50
UMBRAL_PROBABLE = 0.33
UMBRAL_SUGERIR = 0.20


def buscar(texto: str) -> dict:
    """{'nivel': 'seguro'|'probable'|'sugerir'|'nada', 'id', 'respuesta', 'pregunta', 'puntaje', 'sugerencias': [...]}"""
    ix = _indice()
    top = ix.consulta(texto)
    if not top:
        return {"nivel": "nada", "puntaje": 0.0, "sugerencias": []}
    s1, i1, q1 = top[0]
    s2 = top[1][0] if len(top) > 1 else 0.0
    sug = [q for _, _, q in top[:3]]
    base = {"id": i1, "pregunta": q1, "puntaje": round(s1, 3), "sugerencias": sug}
    if s1 >= UMBRAL_SEGURO or (s1 >= UMBRAL_PROBABLE and (s1 >= 1.15 * s2 or s1 >= 0.42)):
        return {**base, "nivel": "seguro" if s1 >= UMBRAL_SEGURO else "probable", "respuesta": ix.entradas[i1]["a"]}
    if s1 >= UMBRAL_SUGERIR:
        return {**base, "nivel": "sugerir"}
    return {"nivel": "nada", "puntaje": round(s1, 3), "sugerencias": []}
