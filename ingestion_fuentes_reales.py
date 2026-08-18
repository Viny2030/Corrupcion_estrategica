"""
ingestion_fuentes_reales.py

Scrapers reales para reemplazar el diccionario en memoria de
api_endpoints.py. Pensado para correr como job del scheduled task
semanal, reusando el mismo patrón de ingesta que ya tienen Monitor de
Contratos / Monitor Legislativo / MEACI (no se reinventa el pipeline,
solo se documentan las fuentes específicas de este módulo).

Instalar:  pip install requests beautifulsoup4 lxml --break-system-packages

IMPORTANTE — estado de cada fuente (última verificación: 2026-08-18, vía
fetch real desde el sandbox — no vía navegador, ver detalle por fuente):

  BORA (boletinoficial.gob.ar)
    Estructura confirmada: HTML server-rendered. Búsqueda avanzada en
    /busquedaAvanzada/all, avisos individuales en
    /detalleAviso/{seccion}/{id}/{fecha}. Scrapeable directo con
    requests + BeautifulSoup para avisos individuales conocidos.
    La búsqueda por texto libre (BoraScraper.buscar) SIGUE bloqueada:
    /busquedaAvanzada/all?texto=... devuelve HTTP 200 pero sin
    resultados embebidos en el HTML (form con action="" — es un SPA
    que arma la consulta vía JS). Sigue pendiente de inspección de
    Network tab con Claude in Chrome/devtools.

  RIGI — panel de proyectos (argentina.gob.ar/economia/rigi)
    Reconfirmado 2026-08-18: el HTML crudo no contiene ningún fetch()/
    axios/XHR ni endpoint /api/*.json embebido — los únicos <script>
    con datos son un `seriesData` de proyecciones de inversión
    AGREGADAS por sector/año (no por proyecto individual), y los
    contadores de "Proyectos aprobados"/"En evaluación" siguen en 0 en
    el HTML estático (se llenan al elegir una provincia, vía AJAX no
    capturable sin ejecutar JS real). Sigue bloqueado — requiere
    Claude in Chrome conectado (Network tab) para capturar la llamada
    real al elegir una provincia.

  RIGI — registro de VPU (arca.gob.ar/rigi/registros)
    También informativo/estático, sin listado público de VPU
    individuales en la página. Los VPU aprobados se publican como
    resoluciones del Ministerio de Economía en BORA — el camino
    confiable sigue siendo BoraScraper.filtrar_resoluciones_rigi()
    sobre resoluciones ya conocidas, no un scrape genérico.

  BCRA (bcra.gob.ar) — DESBLOQUEADO 2026-08-18
    El índice de noticias SÍ es scrapeable directo:
    https://www.bcra.gob.ar/Noticias/ es HTML server-rendered con
    enlaces <a href="https://www.bcra.gob.ar/noticias/{slug}/"> a cada
    comunicado individual (confirmado por fetch real, no requiere JS).
    BcraScraper.obtener_comunicados_swap() ya implementado abajo.
    Limitación conocida: solo expone la página más reciente (~10-15
    ítems); no se confirmó paginación/archivo histórico en este pase.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "MapaTransparencia-VectoresInfluencia/0.1 (+monitoreo transparencia; contacto research)"
}


# ------------------------------------------------------------------
# BORA — Boletín Oficial
# ------------------------------------------------------------------
@dataclass
class AvisoBora:
    id_aviso: str
    seccion: str
    fecha: date
    titulo: str
    url: str
    texto: str


class BoraScraper:
    """
    Scraper de Boletín Oficial. Confirmado funcional contra la
    estructura real del sitio (fetch verificado el 2026-07-28).
    """

    BASE = "https://www.boletinoficial.gob.ar"
    BUSQUEDA_AVANZADA = f"{BASE}/busquedaAvanzada/all"

    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()
        self.session.headers.update(HEADERS)

    def buscar(self, texto: str, fecha_desde: date, fecha_hasta: date, seccion: str = "primera") -> list[AvisoBora]:
        """
        Busca avisos por texto libre en un rango de fechas.

        NOTA: BORA arma la búsqueda avanzada vía POST/AJAX a un
        endpoint interno que no quedó expuesto en el HTML estático
        (mismo problema que el dashboard de RIGI). Este método
        documenta la interfaz esperada; falta capturar el request
        real (Network tab) para completar los parámetros exactos del
        POST antes de correr en producción.
        """
        raise NotImplementedError(
            "Completar parámetros reales del endpoint de búsqueda "
            "(inspeccionar con Claude in Chrome / devtools: Network tab "
            "al usar la 'Búsqueda avanzada' en boletinoficial.gob.ar)"
        )

    def obtener_aviso(self, seccion: str, id_aviso: str, fecha: date) -> AvisoBora:
        """
        Descarga y parsea un aviso individual. Patrón de URL
        confirmado: /detalleAviso/{seccion}/{id}/{YYYYMMDD}
        """
        fecha_str = fecha.strftime("%Y%m%d")
        url = f"{self.BASE}/detalleAviso/{seccion}/{id_aviso}/{fecha_str}"
        resp = self.session.get(url, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        titulo_tag = soup.find("h1") or soup.find("title")
        titulo = titulo_tag.get_text(strip=True) if titulo_tag else ""

        cuerpo = soup.find("div", class_=re.compile("aviso|detalle|contenido", re.I))
        texto = cuerpo.get_text(" ", strip=True) if cuerpo else soup.get_text(" ", strip=True)

        return AvisoBora(
            id_aviso=id_aviso, seccion=seccion, fecha=fecha,
            titulo=titulo, url=url, texto=texto,
        )

    def filtrar_resoluciones_rigi(self, avisos: list[AvisoBora]) -> list[AvisoBora]:
        """Filtra avisos que correspondan a resoluciones de aprobación de VPU bajo RIGI."""
        patrones = [r"\bRIGI\b", r"Vehículo de Proyecto Único", r"Régimen de Incentivo", r"27\.742"]
        regex = re.compile("|".join(patrones), re.I)
        return [a for a in avisos if regex.search(a.titulo) or regex.search(a.texto)]


# ------------------------------------------------------------------
# RIGI — proyectos aprobados
# ------------------------------------------------------------------
@dataclass
class ProyectoRigi:
    empresa: str
    cuit: Optional[str]
    proyecto: str
    sector: str
    provincia: str
    monto_usd_millones: Optional[float]
    regimen: str  # 'RIGI1' | 'SuperRIGI'
    fecha_aprobacion: Optional[date]
    fuente_url: str


class RigiScraper:
    """
    TODO — endpoint no confirmado. El panel público
    (argentina.gob.ar/economia/rigi) es un dashboard JS: el HTML crudo
    trae los contadores en 0 y los datos reales de proyectos/sectores
    se cargan vía fetch client-side a una API que no quedó expuesta al
    hacer requests plano. Antes de producción:

      1. Abrir https://www.argentina.gob.ar/economia/rigi con
         Claude in Chrome (mcp__claude-in-chrome__navigate +
         read_network_requests) para capturar la URL real del JSON.
      2. Si no hay API pública, usar como fuente primaria el filtro de
         BoraScraper.filtrar_resoluciones_rigi() sobre las
         resoluciones de aprobación (más lento pero 100% confiable,
         ya que cada VPU se publica en BORA).
    """

    def obtener_proyectos_aprobados(self) -> list[ProyectoRigi]:
        raise NotImplementedError(
            "Endpoint del dashboard RIGI no confirmado — ver docstring "
            "de la clase. Usar BoraScraper.filtrar_resoluciones_rigi() "
            "como fuente alternativa mientras tanto."
        )


# ------------------------------------------------------------------
# BCRA — swaps de monedas
# ------------------------------------------------------------------
@dataclass
class ComunicadoBcra:
    fecha: date
    titulo: str
    url: str
    texto: str
    monto_usd_millones: Optional[float]


class BcraScraper:
    """
    Índice confirmado 2026-08-18: https://www.bcra.gob.ar/Noticias/ es
    HTML server-rendered con <a href="https://www.bcra.gob.ar/noticias/
    {slug}/"> por cada comunicado. No hace falta JS ni headers
    especiales — un GET con User-Agent de navegador alcanza (probado
    con requests plano desde el sandbox, HTTP 200 y links presentes).

    Ejemplo real capturado en este pase (2026-08-18): el comunicado
    'el-banco-central-de-la-republica-argentina-y-el-banco-de-la-
    republica-popular-de-china-renuevan-su-acuerdo-de-swap-y-
    extienden-el-plazo-de-3-a-5-anos' (5-ago-2026) — swap BCRA-PBOC
    RMB 130.000M, tramo activo RMB 35.000M (~USD 5.000M desde inicios
    de 2023), plazo extendido de 3 a 5 años. Relevante para el vector
    `swap-bcra-pboc-tesoro-eeuu` — no cambia el mecanismo (sigue siendo
    layer2_external_loans_grants) pero sí profundiza el horizonte de
    dependencia del tramo activo.

    Limitación conocida: la página índice solo trae los ítems más
    recientes (no se confirmó archivo histórico paginado en este pase);
    para comunicados más viejos que la ventana visible, usar el motor
    de búsqueda propio de bcra.gob.ar (no automatizado acá todavía).
    """

    BASE = "https://www.bcra.gob.ar"
    INDICE = f"{BASE}/Noticias/"

    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()
        self.session.headers.update(HEADERS)

    def _listar_urls_noticias(self) -> list[str]:
        resp = self.session.get(self.INDICE, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        urls = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/noticias/" in href and href.rstrip("/") != f"{self.BASE}/noticias":
                if href not in urls:
                    urls.append(href)
        return urls

    def _parsear_comunicado(self, url: str) -> Optional[ComunicadoBcra]:
        resp = self.session.get(url, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        titulo_tag = soup.find("h1") or soup.find("title")
        titulo = titulo_tag.get_text(strip=True) if titulo_tag else ""

        cuerpo = soup.find("article") or soup.find("main") or soup.body
        texto = cuerpo.get_text(" ", strip=True) if cuerpo else soup.get_text(" ", strip=True)

        fecha_tag = soup.find("time")
        fecha = None
        if fecha_tag and fecha_tag.get("datetime"):
            try:
                fecha = datetime.fromisoformat(fecha_tag["datetime"][:10]).date()
            except ValueError:
                fecha = None

        monto = None
        match_monto = re.search(r"USD\s?([\d.,]+)\s?(millones|mill)", texto, re.I)
        if match_monto:
            try:
                monto = float(match_monto.group(1).replace(".", "").replace(",", "."))
            except ValueError:
                monto = None

        return ComunicadoBcra(
            fecha=fecha or date.today(), titulo=titulo, url=url, texto=texto,
            monto_usd_millones=monto,
        )

    def obtener_comunicados_swap(self, palabra_clave: str = "swap") -> list[ComunicadoBcra]:
        """Filtra el índice de noticias por palabra clave (default 'swap',
        también matchea 'china'/'pboc' en el slug de la URL) y devuelve
        los comunicados parseados."""
        candidatos = [
            u for u in self._listar_urls_noticias()
            if re.search(palabra_clave, u, re.I) or re.search(r"china|pboc|banco-central", u, re.I)
        ]
        resultados = []
        for url in candidatos:
            try:
                c = self._parsear_comunicado(url)
                if c:
                    resultados.append(c)
            except requests.RequestException:
                continue
        return resultados


if __name__ == "__main__":
    # BoraScraper: estructura de URL confirmada, pero buscar() sigue
    # bloqueada (ver docstring del módulo). BcraScraper: end-to-end
    # funcional desde 2026-08-18, se ejecuta acá como smoke test real.
    print("BoraScraper listo (estructura de URL confirmada; buscar() sigue bloqueada).")
    print("RigiScraper sigue bloqueado — ver TODO en el código.\n")

    print("BcraScraper — corriendo obtener_comunicados_swap() contra bcra.gob.ar...")
    try:
        comunicados = BcraScraper().obtener_comunicados_swap()
        print(f"{len(comunicados)} comunicado(s) encontrados:")
        for c in comunicados:
            print(f"  - [{c.fecha}] {c.titulo}\n    {c.url}")
    except requests.RequestException as exc:
        print(f"  Fallo de red al consultar BCRA: {exc}")
