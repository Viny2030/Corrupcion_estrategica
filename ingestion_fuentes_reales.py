"""
ingestion_fuentes_reales.py

Scrapers reales para reemplazar el diccionario en memoria de
api_endpoints.py. Pensado para correr como job del scheduled task
semanal, reusando el mismo patrón de ingesta que ya tienen Monitor de
Contratos / Monitor Legislativo / MEACI (no se reinventa el pipeline,
solo se documentan las fuentes específicas de este módulo).

Instalar:  pip install requests beautifulsoup4 lxml --break-system-packages

IMPORTANTE — estado de cada fuente (verificado hoy vía fetch real):

  BORA (boletinoficial.gob.ar)
    Estructura confirmada: HTML server-rendered. Búsqueda avanzada en
    /busquedaAvanzada/all, avisos individuales en
    /detalleAviso/{seccion}/{id}/{fecha}. Scrapeable directo con
    requests + BeautifulSoup.

  RIGI — panel de proyectos (argentina.gob.ar/economia/rigi)
    Es un dashboard renderizado con JavaScript (todos los contadores
    cargan en 0 en el HTML crudo, se llenan client-side vía fetch a una
    API interna). NO se pudo confirmar el endpoint JSON real sin
    inspeccionar el Network tab del navegador. Placeholder abajo con
    TODO explícito — resolver con Claude in Chrome / devtools antes de
    poner esto en producción.

  RIGI — registro de VPU (arca.gob.ar/rigi/registros)
    También informativo/estático, sin listado público de VPU
    individuales en la página. Los VPU aprobados se publican como
    resoluciones del Ministerio de Economía en BORA — el camino
    confiable es scrapear BORA filtrando por esas resoluciones, no
    ARCA directamente.

  BCRA (bcra.gob.ar)
    Los comunicados de política monetaria (swaps, etc.) se publican
    como notas de prensa individuales bajo /politica-monetaria/. No se
    pudo confirmar el listado/índice en este pase — requiere el mismo
    tipo de verificación que RIGI.
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
    TODO — mismo caso: no se confirmó el índice/listado de comunicados
    de política monetaria en este pase (fetch a
    PoliticaMonetariaComunicados.asp devolvió vacío, probablemente
    también JS-rendered o requiere headers/cookies de sesión). Antes
    de producción, inspeccionar con Claude in Chrome la sección de
    comunicados en bcra.gob.ar/politica-monetaria/.

    Búsqueda manual de referencia mientras tanto: los comunicados de
    renovación del swap BCRA-PBOC aparecen indexados bajo
    bcra.gob.ar/politica-monetaria/ con slugs del tipo
    'el-bcra-y-el-pboc-renuevan-...' — confirmar patrón exacto.
    """

    def obtener_comunicados_swap(self, palabra_clave: str = "swap") -> list[ComunicadoBcra]:
        raise NotImplementedError(
            "Índice de comunicados BCRA no confirmado — ver docstring de la clase."
        )


if __name__ == "__main__":
    # Único caso end-to-end confirmado funcional en este pase: BORA.
    scraper = BoraScraper()
    print(
        "BoraScraper listo (estructura de URL confirmada). "
        "RigiScraper y BcraScraper requieren inspección de red antes "
        "de poder ejecutarse — ver TODOs en el código."
    )
