"""
narrative_analysis_module.py

Módulo E del framework NEST — Análisis Narrativo y Discursivo. Es la
pieza que seguía vacía en el ecosistema (ningún monitor la toca hoy).
El caso "China Watch / El Cronista" (ver seed_vectores.json, slug
medios-china-daily-china-watch) es la primera entrada cargada a mano;
este módulo es el intento de sistematizar la detección en vez de
depender de hallazgos manuales.

Qué detecta, según el framework:
  1. Repetición de talking points alineados con intereses externos
     entre voceros/medios distintos en ventanas de tiempo cortas.
  2. Cambios súbitos de encuadre — un tema pasa de tratarse como
     "seguridad nacional" a describirse como "cuestión meramente
     técnica/económica".
  3. Campañas de descalificación o litigios estratégicos (SLAPP)
     contra periodistas u organismos de control que investigan alguno
     de los vectores ya cargados en la tabla madre.

Fuentes reales a conectar (no scrapeadas en este pase — requiere
inspección de red / permisos por fuente):
  - Diputados: versiones taquigráficas en hcdn.gob.ar
  - Senado: versiones taquigráficas en senado.gob.ar
  - Prensa: RSS de medios nacionales + medios especializados en
    relaciones China-América Latina (ya usados en el scheduled task
    semanal: "China en las Américas", "Diálogo Chino")

Este archivo define el modelo de datos y la lógica de detección sobre
texto ya ingerido (parámetro de entrada), para que se pueda enchufar
cualquier scraper de las fuentes de arriba sin tocar la lógica.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from itertools import combinations
from typing import Optional


# ------------------------------------------------------------------
# Modelo de datos
# ------------------------------------------------------------------
@dataclass
class MuestraNarrativa:
    fuente: str                 # 'diputados', 'senado', 'prensa:<medio>'
    tipo: str                   # 'discurso_parlamentario' | 'articulo_prensa' | 'comunicado'
    autor: str                  # orador o medio
    fecha: date
    texto: str
    url: str
    vector_relacionado: Optional[str] = None  # slug de vectores_influencia_extranjera, si aplica


@dataclass
class AlertaTalkingPoint:
    frase_clave: str
    apariciones: list[MuestraNarrativa]
    ventana_dias: int
    autores_distintos: int
    detalle: str


@dataclass
class AlertaCambioEncuadre:
    tema: str
    periodo_antes: tuple[date, date]
    periodo_despues: tuple[date, date]
    frecuencia_seguridad_antes: int
    frecuencia_tecnico_despues: int
    detalle: str


@dataclass
class AlertaSlapp:
    objetivo: str                 # periodista/organismo atacado
    vector_investigado: Optional[str]
    muestras: list[MuestraNarrativa]
    detalle: str


# ------------------------------------------------------------------
# 1. Detección de talking points repetidos
# ------------------------------------------------------------------
STOPWORDS_ES = {
    "el", "la", "los", "las", "un", "una", "de", "del", "en", "y", "a",
    "que", "es", "por", "con", "para", "se", "su", "sus", "no", "lo",
    "como", "más", "pero", "al", "o", "esta", "este", "estos", "estas",
}


def _shingles(texto: str, n: int = 4) -> set[str]:
    """N-gramas de palabras (shingles), ignorando stopwords, para comparar frases sin depender de coincidencia exacta."""
    palabras = [w for w in re.findall(r"[a-záéíóúñ]+", texto.lower()) if w not in STOPWORDS_ES]
    return {" ".join(palabras[i : i + n]) for i in range(len(palabras) - n + 1)}


def detectar_talking_points(
    muestras: list[MuestraNarrativa],
    ventana_dias: int = 14,
    min_autores_distintos: int = 3,
    n_gram: int = 4,
) -> list[AlertaTalkingPoint]:
    """
    Agrupa muestras en ventanas móviles de N días y busca shingles
    (frases de 4 palabras, sin stopwords) que se repiten entre al
    menos `min_autores_distintos` autores/medios distintos — proxy de
    "talking points" coordinados en vez de coincidencia casual.
    """
    muestras_ordenadas = sorted(muestras, key=lambda m: m.fecha)
    alertas = []

    if not muestras_ordenadas:
        return alertas

    inicio = muestras_ordenadas[0].fecha
    fin = muestras_ordenadas[-1].fecha
    cursor = inicio

    while cursor <= fin:
        ventana = [
            m for m in muestras_ordenadas
            if cursor <= m.fecha < cursor + timedelta(days=ventana_dias)
        ]
        if len(ventana) >= min_autores_distintos:
            shingle_a_muestras: dict[str, list[MuestraNarrativa]] = defaultdict(list)
            for m in ventana:
                for sh in _shingles(m.texto, n_gram):
                    shingle_a_muestras[sh].append(m)

            for frase, muestras_frase in shingle_a_muestras.items():
                autores = {m.autor for m in muestras_frase}
                if len(autores) >= min_autores_distintos:
                    alertas.append(
                        AlertaTalkingPoint(
                            frase_clave=frase,
                            apariciones=muestras_frase,
                            ventana_dias=ventana_dias,
                            autores_distintos=len(autores),
                            detalle=(
                                f"Frase repetida por {len(autores)} autores/medios "
                                f"distintos en una ventana de {ventana_dias} días."
                            ),
                        )
                    )
        cursor += timedelta(days=ventana_dias)

    return alertas


# ------------------------------------------------------------------
# 2. Detección de cambio de encuadre (framing shift)
# ------------------------------------------------------------------
PALABRAS_SEGURIDAD = {"seguridad nacional", "soberanía", "estratégico", "defensa", "geopolítico", "geopolítica"}
PALABRAS_TECNICO = {"cuestión técnica", "meramente administrativo", "trámite", "económico", "comercial", "procedimiento"}


def detectar_cambio_encuadre(
    muestras: list[MuestraNarrativa],
    tema_regex: str,
    fecha_corte: date,
    ventana_dias: int = 60,
) -> Optional[AlertaCambioEncuadre]:
    """
    Compara, para un tema dado (ej. 'Neuquén|espacio|CLTC'), la
    frecuencia de encuadre en términos de seguridad ANTES de una fecha
    de corte contra la frecuencia de encuadre técnico/económico
    DESPUÉS. Un salto marcado es la señal que describe el framework:
    "framing repentino de temas de seguridad nacional como asuntos
    meramente técnicos/económicos".
    """
    regex = re.compile(tema_regex, re.I)
    relevantes = [m for m in muestras if regex.search(m.texto)]
    if not relevantes:
        return None

    antes = [m for m in relevantes if fecha_corte - timedelta(days=ventana_dias) <= m.fecha < fecha_corte]
    despues = [m for m in relevantes if fecha_corte <= m.fecha < fecha_corte + timedelta(days=ventana_dias)]

    freq_seguridad_antes = sum(
        1 for m in antes if any(p in m.texto.lower() for p in PALABRAS_SEGURIDAD)
    )
    freq_tecnico_despues = sum(
        1 for m in despues if any(p in m.texto.lower() for p in PALABRAS_TECNICO)
    )

    if freq_seguridad_antes >= 2 and freq_tecnico_despues >= 2:
        return AlertaCambioEncuadre(
            tema=tema_regex,
            periodo_antes=(fecha_corte - timedelta(days=ventana_dias), fecha_corte),
            periodo_despues=(fecha_corte, fecha_corte + timedelta(days=ventana_dias)),
            frecuencia_seguridad_antes=freq_seguridad_antes,
            frecuencia_tecnico_despues=freq_tecnico_despues,
            detalle=(
                f"El tema se encuadraba en términos de seguridad "
                f"({freq_seguridad_antes} menciones) antes de {fecha_corte}, "
                f"y pasó a encuadrarse en términos técnicos/económicos "
                f"({freq_tecnico_despues} menciones) después."
            ),
        )
    return None


# ------------------------------------------------------------------
# 3. Detección de campañas de descalificación / SLAPP
# ------------------------------------------------------------------
PALABRAS_SLAPP = {
    "demanda", "querella", "difamación", "calumnias", "injurias",
    "operador", "operación de prensa", "desestabilizar", "campaña sucia",
}


def detectar_slapp(
    muestras: list[MuestraNarrativa],
    objetivos_a_vigilar: list[str],
    vector_slug: Optional[str] = None,
) -> list[AlertaSlapp]:
    """
    Busca menciones agresivas (litigios, descalificación) dirigidas a
    periodistas/organismos que investigan alguno de los vectores de la
    tabla madre. `objetivos_a_vigilar` es una lista de nombres/alias a
    trackear (periodistas, ONGs, organismos de control).
    """
    alertas = []
    for objetivo in objetivos_a_vigilar:
        objetivo_regex = re.compile(re.escape(objetivo), re.I)
        muestras_relevantes = [
            m for m in muestras
            if objetivo_regex.search(m.texto)
            and any(p in m.texto.lower() for p in PALABRAS_SLAPP)
        ]
        if muestras_relevantes:
            alertas.append(
                AlertaSlapp(
                    objetivo=objetivo,
                    vector_investigado=vector_slug,
                    muestras=muestras_relevantes,
                    detalle=(
                        f"{len(muestras_relevantes)} muestras con lenguaje de "
                        f"descalificación/litigio dirigidas a '{objetivo}'."
                    ),
                )
            )
    return alertas


if __name__ == "__main__":
    # Ejemplo mínimo con datos sintéticos para validar la lógica sin
    # depender de scrapers reales todavía.
    muestras_demo = [
        MuestraNarrativa(
            fuente="prensa:medio_a", tipo="articulo_prensa", autor="Medio A",
            fecha=date(2026, 6, 1),
            texto="El proyecto es una cuestión meramente técnica y administrativa, sin implicancias de seguridad nacional.",
            url="https://ejemplo.com/a",
            vector_relacionado="espacio-doble-uso-neuquen-rio-gallegos",
        ),
        MuestraNarrativa(
            fuente="prensa:medio_b", tipo="articulo_prensa", autor="Medio B",
            fecha=date(2026, 6, 3),
            texto="Se trata de una cuestión meramente técnica y administrativa, no un tema de seguridad nacional.",
            url="https://ejemplo.com/b",
            vector_relacionado="espacio-doble-uso-neuquen-rio-gallegos",
        ),
        MuestraNarrativa(
            fuente="diputados", tipo="discurso_parlamentario", autor="Diputado X",
            fecha=date(2026, 6, 5),
            texto="Insisto: esto es una cuestión meramente técnica y administrativa, alejada de cualquier debate de seguridad nacional.",
            url="https://ejemplo.com/c",
            vector_relacionado="espacio-doble-uso-neuquen-rio-gallegos",
        ),
    ]

    alertas_tp = detectar_talking_points(muestras_demo, ventana_dias=14, min_autores_distintos=3)
    print(f"Talking points detectados: {len(alertas_tp)}")
    for a in alertas_tp:
        print(f"  - '{a.frase_clave}' ({a.autores_distintos} autores) — {a.detalle}")
