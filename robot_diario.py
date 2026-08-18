"""
robot_diario.py

Robot de ingesta diaria del módulo "Vectores de Influencia Estatal
Extranjera". Pensado para correr como scheduled task (Cowork/Claude,
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

2. Corre las fuentes confirmadas de ingestion_fuentes_reales.py:
     - BcraScraper().obtener_comunicados_swap() — funcional end-to-end.
     - BoraScraper — solo obtener_aviso()/filtrar_resoluciones_rigi()
       sobre avisos ya conocidos; buscar() sigue bloqueada (ver ese
       módulo), así que por ahora NO aporta hallazgos nuevos acá.
   RigiScraper sigue bloqueado, no se invoca.

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
import re
import sys
from dataclasses import dataclass

import requests

from ingestion_fuentes_reales import BcraScraper, ComunicadoBcra

API_BASE_DEFAULT = "https://corrupcionestrategica-production.up.railway.app"
TIMEOUT = 20

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


@dataclass
class Hallazgo:
    slug: str
    comunicado: ComunicadoBcra
    razon_match: str


def obtener_vectores_activos(api_base: str) -> list[dict]:
    resp = requests.get(f"{api_base}/api/vectores", params={"activo": True}, timeout=TIMEOUT)
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
        campos = [v.get("actor_extranjero", ""), v.get("contraparte_argentina") or ""]
        palabras = set()
        for campo in campos:
            for token in re.split(r"[\s,/()–-]+", campo):
                token = token.strip().lower()
                if len(token) >= 4 and not token.isdigit() and token not in STOPWORDS_KEYWORD:
                    palabras.add(token)
        if palabras:
            index[v["slug"]] = sorted(palabras)
    return index


def matchear(comunicado: ComunicadoBcra, index: dict[str, list[str]]) -> list[tuple[str, str]]:
    texto = f"{comunicado.titulo} {comunicado.texto}".lower()
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
    for endpoint in ("evidencia", "actualizaciones"):
        resp = requests.get(f"{api_base}/api/vectores/{slug}/{endpoint}", timeout=TIMEOUT)
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
    resumen = f"[robot diario] {c.titulo} (match: '{h.razon_match}')"
    payload_novedad = {
        "resumen": resumen,
        "es_vector_nuevo": False,
        "cambio_clasificacion": False,
        "fuentes": [{"titulo": c.titulo, "url": c.url}],
    }
    payload_evidencia = {
        "tipo_fuente": "prensa_oficial_bcra",
        "titulo": c.titulo,
        "url": c.url,
        "fecha_publicacion": c.fecha.isoformat(),
    }

    if not apply:
        print(f"  [DRY-RUN] postearía novedad + evidencia en '{h.slug}':")
        print(f"            {c.titulo}")
        print(f"            {c.url}")
        return

    r1 = requests.post(f"{api_base}/api/vectores/{h.slug}/actualizacion", json=payload_novedad, timeout=TIMEOUT)
    r2 = requests.post(f"{api_base}/api/vectores/{h.slug}/evidencia", json=payload_evidencia, timeout=TIMEOUT)
    ok = r1.status_code == 201 and r2.status_code == 201
    estado = "OK" if ok else f"ERROR (novedad={r1.status_code}, evidencia={r2.status_code})"
    print(f"  [{estado}] '{h.slug}' <- {c.titulo}")


def correr(api_base: str, apply: bool) -> int:
    print(f"Robot diario — API base: {api_base} — modo: {'APPLY' if apply else 'DRY-RUN'}")

    try:
        vectores = obtener_vectores_activos(api_base)
    except requests.RequestException as exc:
        print(f"No se pudo consultar {api_base}/api/vectores: {exc}", file=sys.stderr)
        return 1
    print(f"{len(vectores)} vectores activos cargados desde la API.")

    index = construir_index_keywords(vectores)

    print("\nFuente: BCRA (comunicados de swap/China/PBOC)")
    try:
        comunicados = BcraScraper().obtener_comunicados_swap()
    except requests.RequestException as exc:
        print(f"  Fallo de red al consultar BCRA: {exc}")
        comunicados = []
    print(f"  {len(comunicados)} comunicado(s) recuperado(s) del índice de noticias.")

    hallazgos_nuevos = 0
    for c in comunicados:
        matches = matchear(c, index)
        if not matches:
            continue
        for slug, palabra in matches:
            if ya_registrado(api_base, slug, c.url):
                continue
            h = Hallazgo(slug=slug, comunicado=c, razon_match=palabra)
            postear_hallazgo(api_base, h, apply)
            hallazgos_nuevos += 1

    print(f"\nResumen: {hallazgos_nuevos} hallazgo(s) nuevo(s) {'posteado(s)' if apply else 'detectado(s) (dry-run)'}.")
    print(
        "Nota: BORA (búsqueda por texto) y RIGI siguen bloqueados — ver "
        "ingestion_fuentes_reales.py. Esta corrida solo cubre BCRA."
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api-base", default=API_BASE_DEFAULT, help="Base URL de la API en vivo")
    parser.add_argument("--apply", action="store_true", help="Postea de verdad (default: dry-run)")
    args = parser.parse_args()
    sys.exit(correr(args.api_base.rstrip("/"), args.apply))


if __name__ == "__main__":
    main()
