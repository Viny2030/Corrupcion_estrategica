"""
robot_diario.py

Robot de ingesta del módulo "Vectores de Influencia Estatal Extranjera"
(lo corre el workflow semanal de GitHub Actions). Pensado para correr como scheduled task (Cowork/Claude,
o cualquier cron), SIN depender de que la desktop del usuario esté
conectada: solo necesita salida a internet (BORA/BCRA/API en vivo) y,
opcionalmente, un clon de este repo.

Qué hace cada corrida
----------------------
1. Trae la lista de vectores activos desde la API en vivo
   (GET /api/vectores) para saber contra qué actores/sectores/países
   matchear novedades — no depende de un mapeo hardcodeado, así que
   si se dan de alta vectores nuevos el robot los cubre automáticamente
   en la corrida siguiente.

2. Corre las fuentes de ingestion_fuentes_reales.py:
     - BcraScraper().obtener_comunicados() — todo el índice de noticias.
     - BoraScraper.listar_dia() — primera sección del Boletín Oficial de
       los últimos N días (--dias-bora); abre los avisos de RIGI, del
       Ministerio de Economía o con alguna clave en el título.
   RigiScraper (panel de argentina.gob.ar) sigue bloqueado, no se invoca.

3. Para cada comunicado encontrado, matchea por palabras clave contra
   actor_extranjero/sector/pais_origen/mecanismo de los vectores
   activos (y contra los "a vigilar" vía el mismo GET). Si matchea:
     a. Deduplica contra GET /api/vectores/{slug}/evidencia y
        /api/vectores/{slug}/actualizaciones — si la URL ya está
        registrada, no vuelve a postear.
     b. Si es nuevo, arma un payload de evidencia + novedad.

4. Modo por defecto: DRY RUN — solo imprime qué postearía y por qué.
   Nada se escribe en la API en vivo salvo que se pase --apply.
   Esto es deliberado: el robot cataloga noticias/fuentes contra
   vectores ya existentes (no crea vectores nuevos ni cambia scores/
   clasificación — eso sigue siendo una decisión manual, igual que en
   el resto del ecosistema), pero aun así escribe en una base pública;
   --apply es la confirmación explícita de que se quiere publicar.

Uso
---
    python robot_diario.py                  # dry-run contra la API en vivo
    python robot_diario.py --apply          # postea de verdad
    python robot_diario.py --api-base http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta

import requests

from ingestion_fuentes_reales import BcraScraper, BoraScraper, ComunicadoBcra

# Dominio directo de Railway
API_BASE_DEFAULT = os.getenv("API_BASE_URL", "https://corrupcionestrategica-production.up.railway.app")
TIMEOUT = 20

# Encabezados base estándar
HEADERS_LECTURA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

# Las escrituras en la API piden el header X-Robot-Token (ver auth.py).
HEADERS_ESCRITURA = {
    **HEADERS_LECTURA,
    "X-Robot-Token": os.getenv("ROBOT_TOKEN", ""),
}

# Términos genéricos que NO deben usarse como keyword de match: son tan
# comunes en cualquier noticia sobre inversión extranjera en Argentina
# que matchean casi cualquier vector (mismo problema documentado en
# matcher_cuit_rigi.py con nombres de empresas — acá aplicado a texto
# libre de noticias). Sin este filtro, cualquier nota que mencione
# "China" matchea los 16 vectores activos aunque solo uno sea relevante.
STOPWORDS_KEYWORD = {
    "china", "chino", "chinos", "chinas", "rusia", "ruso", "rusos",
    "estado", "estatal", "estatales", "gobierno", "nacional", "banco",
    "banca", "bancario", "argentina", "argentino", "argentinos",
    "inversion", "inversión", "inversiones", "financiamiento",
    "infraestructura", "proyecto", "proyectos", "empresa", "empresas",
    "corporation", "corp", "group", "grupo", "company", "compañía",
    "sector", "mineria", "minería", "energia", "energía", "industrial",
    "commercial", "bank", "holding", "internacional", "international",
    "provincias", "provincia", "mineras", "afip", "poder", "ejecutivo",
}

# Palabras clave propias de cada vector (nombres de empresas, organismos y
# proyectos). Se usan en vez de partir actor_extranjero/contraparte en
# palabras sueltas: eso generaba claves genéricas ("ministerio", "universidad",
# "s.a.", "bcra", "national", "rigi") que en el Boletín Oficial o en las
# noticias del BCRA matchean casi cualquier aviso. Para vectores nuevos que no
# estén acá se usa el índice automático, con más palabras genéricas filtradas.
KEYWORDS_VECTOR = {
    "atucha-iii-cnnc": ["cnnc", "atucha iii", "hualong"],
    "litio-rigi-zijin-ganfeng": ["ganfeng", "zijin", "liex", "lithea"],
    "espacio-doble-uso-neuquen-rio-gallegos": ["cltc", "emposat", "ascentio", "espacio lejano"],
    "5g-enacom-huawei": ["huawei"],
    "swap-bcra-pboc-tesoro-eeuu": ["pboc", "banco popular de china", "people's bank of china", "swap de monedas", "acuerdo de swap"],
    "institutos-confucio-uba-unlp-unc-mendoza": ["instituto confucio", "institutos confucio", "hanban"],
    "defensa-armamento-rusia-china": ["rosoboronexport", "mig-35", "yak-130"],
    # (sin "anpyn": aparece en los códigos GDE de cualquier resolución de la agencia)
    "hidrovia-parana-paraguay-dragado": ["jan de nul", "via navegable troncal", "hidrovia"],
    "medios-china-daily-china-watch": ["china daily", "china watch"],
    "litio-tolillar-rosatom-uranium-one": ["rosatom", "uranium one", "alpha lithium", "tolillar"],
    "banca-icbc-argentina": ["icbc"],
    "agro-cofco-terminal-timbues": ["cofco"],
    "represas-santa-cruz-gezhouba": ["gezhouba", "condor cliff", "la barrancosa"],
    "belgrano-cargas-cmec": ["cmec", "china machinery engineering"],
    "solar-cauchari-jujuy-powerchina": ["powerchina", "cauchari", "shanghai electric"],
    "pesca-calamar-flota-china": ["cnfc", "haoyang", "huafeng", "zhejiang ocean", "shanghai fisheries"],
}

STOPWORDS_KEYWORD |= {
    "ministerio", "universidad", "congreso", "educacion", "educación", "capital", "medio", "medios",
    "s.a.", "s.a.u.", "n.v.", "sociedad", "consejo", "federal", "agencia", "licitacion", "licitación",
    "fuerzas", "armadas", "power", "electric", "control", "national", "nuclear", "rigi", "bcra",
    "tesoro", "eeuu", "bajo", "oferta", "confirmada", "contraparte", "operador", "puertos",
    "subsidiaria", "products", "ocean", "family", "bandera", "flota", "mining", "lithium",
    "construction", "engineering", "technologies", "launch", "tracking", "logistica", "logística",
    "trenes", "cargas", "argentinas", "america", "américa", "rosario", "mendoza", "jujuy",
}


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode()
    return t.lower()


@dataclass
class Hallazgo:
    slug: str
    comunicado: object          # ComunicadoBcra o AvisoBora (titulo, url, fecha, texto)
    razon_match: str
    tipo_fuente: str = "prensa_oficial_bcra"


def obtener_vectores_activos(api_base: str) -> list[dict]:
    headers = {**HEADERS_LECTURA, **HEADERS_ESCRITURA}
    resp = requests.get(f"{api_base}/api/vectores", params={"activo": True}, headers=headers, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def construir_index_keywords(vectores: list[dict]) -> dict[str, list[str]]:
    """Por cada slug, arma una lista de palabras/frases clave específicas
    a partir de actor_extranjero y contraparte_argentina — nombres
    propios (empresas, bancos, organismos), no descripciones en prosa.
    Deliberadamente NO usa sector/pais_origen/mecanismo: son texto
    descriptivo genérico y matchean casi cualquier noticia (ver
    STOPWORDS_KEYWORD para los términos ya descartados por probarlo)."""
    index: dict[str, list[str]] = {}
    for v in vectores:
        if v["slug"] in KEYWORDS_VECTOR:
            index[v["slug"]] = sorted(_norm(k) for k in KEYWORDS_VECTOR[v["slug"]])
            continue
        campos = [v.get("actor_extranjero", ""), v.get("contraparte_argentina") or ""]
        palabras = set()
        for campo in campos:
            for token in re.split(r"[\s,/()–-]+", campo):
                token = token.strip().lower()
                if len(token) >= 4 and not token.isdigit() and token not in STOPWORDS_KEYWORD:
                    palabras.add(_norm(token))
        if palabras:
            index[v["slug"]] = sorted(palabras)
    return index


def matchear(comunicado, index: dict[str, list[str]]) -> list[tuple[str, str]]:
    texto = _norm(f"{comunicado.titulo} {comunicado.texto}")
    matches = []
    for slug, palabras in index.items():
        for palabra in palabras:
            if re.search(rf"\b{re.escape(palabra)}\b", texto):
                matches.append((slug, palabra))
                break
    return matches


def ya_registrado(api_base: str, slug: str, url: str) -> bool:
    """Chequea evidencia + actualizaciones ya registradas para ese vector,
    para no volver a postear la misma fuente en corridas sucesivas."""
    headers = {**HEADERS_LECTURA, **HEADERS_ESCRITURA}
    for endpoint in ("evidencia", "actualizaciones"):
        resp = requests.get(f"{api_base}/api/vectores/{slug}/{endpoint}", headers=headers, timeout=TIMEOUT)
        if resp.status_code != 200:
            continue
        for item in resp.json():
            if endpoint == "evidencia" and item.get("url") == url:
                return True
            if endpoint == "actualizaciones":
                fuentes = item.get("fuentes_json") or []
                if any(f.get("url") == url for f in fuentes if isinstance(f, dict)):
                    return True
    return False


def postear_hallazgo(api_base: str, h: Hallazgo, apply: bool) -> None:
    c = h.comunicado
    resumen = f"[robot] {c.titulo[:300]} (fuente: {h.tipo_fuente}; match: '{h.razon_match}')"
    payload_novedad = {
        "resumen": resumen,
        "es_vector_nuevo": False,
        "cambio_clasificacion": False,
        "fuentes": [{"titulo": c.titulo, "url": c.url}],
    }
    payload_evidencia = {
        "tipo_fuente": h.tipo_fuente,
        "titulo": c.titulo[:500],
        "url": c.url,
        "fecha_publicacion": c.fecha.isoformat(),
    }

    if not apply:
        print(f"  [DRY-RUN] postearía novedad + evidencia en '{h.slug}':")
        print(f"            {c.titulo}")
        print(f"            {c.url}")
        return

    r1 = requests.post(f"{api_base}/api/vectores/{h.slug}/actualizacion", json=payload_novedad,
                       headers=HEADERS_ESCRITURA, timeout=TIMEOUT)
    r2 = requests.post(f"{api_base}/api/vectores/{h.slug}/evidencia", json=payload_evidencia,
                       headers=HEADERS_ESCRITURA, timeout=TIMEOUT)
    ok = r1.status_code == 201 and r2.status_code == 201
    estado = "OK" if ok else f"ERROR (novedad={r1.status_code}, evidencia={r2.status_code})"
    print(f"  [{estado}] '{h.slug}' <- {c.titulo}")


# En el Boletín Oficial se abre el detalle sólo de los avisos cuyo título
# menciona alguna clave, RIGI, o vienen del Ministerio de Economía (que es
# quien publica las aprobaciones de VPU del RIGI).
_RE_BORA_REVISAR = re.compile(r"RIGI|GRANDES INVERSIONES|MINISTERIO DE ECONOM", re.I)


def _avisos_bora(dias: int, index: dict[str, list[str]]) -> list:
    bora = BoraScraper()
    claves = {k for ks in index.values() for k in ks}
    salida = []
    hoy = date.today()
    for d in range(dias):
        fecha = hoy - timedelta(days=d)
        if fecha.weekday() >= 5:  # sin Boletín sábado y domingo
            continue
        try:
            listado = bora.listar_dia(fecha)
        except requests.RequestException as exc:
            print(f"  BORA {fecha}: sin acceso ({exc})")
            continue
        for url, texto in listado:
            t = _norm(texto)
            if not (_RE_BORA_REVISAR.search(texto) or any(re.search(rf"\b{re.escape(k)}\b", t) for k in claves)):
                continue
            try:
                aviso = bora.obtener_aviso_url(url)
                aviso.titulo = texto  # organismo + norma, más útil que el <h1> del detalle
                salida.append(aviso)
                time.sleep(0.3)
            except requests.RequestException:
                continue
    return salida


def correr(api_base: str, apply: bool, dias_bora: int = 7) -> int:
    print(f"Robot — API base: {api_base} — modo: {'APPLY' if apply else 'DRY-RUN'}")

    try:
        vectores = obtener_vectores_activos(api_base)
    except requests.RequestException as exc:
        print(f"No se pudo consultar {api_base}/api/vectores: {exc}", file=sys.stderr)
        return 1
    print(f"{len(vectores)} vectores activos cargados desde la API.")

    index = construir_index_keywords(vectores)

    fuentes = []
    print("\nFuente: BCRA (índice completo de noticias)")
    try:
        comunicados = BcraScraper().obtener_comunicados()
    except requests.RequestException as exc:
        print(f"  Fallo de red al consultar BCRA: {exc}")
        comunicados = []
    print(f"  {len(comunicados)} comunicado(s) revisado(s).")
    fuentes += [(c, "prensa_oficial_bcra") for c in comunicados]

    print(f"\nFuente: Boletín Oficial, primera sección (últimos {dias_bora} días)")
    avisos = _avisos_bora(dias_bora, index)
    print(f"  {len(avisos)} aviso(s) abiertos (RIGI, Ministerio de Economía o con alguna clave en el título).")
    fuentes += [(a, "boletin_oficial") for a in avisos]

    hallazgos_nuevos = 0
    for item, tipo in fuentes:
        for slug, palabra in matchear(item, index):
            if ya_registrado(api_base, slug, item.url):
                continue
            postear_hallazgo(api_base, Hallazgo(slug=slug, comunicado=item, razon_match=palabra, tipo_fuente=tipo), apply)
            hallazgos_nuevos += 1

    # Aprobaciones RIGI de la semana (tengan o no vínculo con un vector): sirven
    # para detectar a mano actores nuevos que todavía no son vectores.
    rigi = [a for a in avisos if re.search(r"adhesi[oó]n al RIGI|R[eé]gimen de Incentivo para Grandes Inversiones", a.texto, re.I)]
    lineas = [f"- {a.titulo} — {a.url}" for a in rigi]
    print(f"\nAvisos RIGI en el Boletín Oficial ({len(rigi)}):")
    for l in lineas:
        print("  " + l)
    resumen_gh = os.getenv("GITHUB_STEP_SUMMARY")
    if resumen_gh:
        with open(resumen_gh, "a", encoding="utf-8") as f:
            f.write(f"## Robot vectores — {hallazgos_nuevos} hallazgo(s)\n\n### Avisos RIGI ({len(rigi)})\n" + "\n".join(lineas) + "\n")

    print(f"\nResumen: {hallazgos_nuevos} hallazgo(s) nuevo(s) {'posteado(s)' if apply else 'detectado(s) (dry-run)'}.")
    print("Nota: el panel RIGI (argentina.gob.ar) sigue sin API pública; las aprobaciones se toman del Boletín Oficial.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api-base", default=API_BASE_DEFAULT, help="Base URL de la API en vivo")
    parser.add_argument("--apply", action="store_true", help="Postea de verdad (default: dry-run)")
    parser.add_argument("--dias-bora", type=int, default=7, help="Días hacia atrás a revisar en el Boletín Oficial")
    args = parser.parse_args()
    sys.exit(correr(args.api_base.rstrip("/"), args.apply, args.dias_bora))


if __name__ == "__main__":
    main()
