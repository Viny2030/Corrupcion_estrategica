"""
scoring_engine.py

Motor de clasificación del módulo "Vectores de Influencia Estatal Extranjera".
Implementa el classification test de 4 elementos del framework NEST
(Analytical Framework for Detecting, Assessing and Responding to
Strategic Corruption) como rúbrica de scoring 0-3, igual estilo a como
Monitor DDJJ clasifica CRÍTICO/ALTO/MEDIO/BAJO.

Escala por elemento:
  0 = sin evidencia
  1 = indicio / proxy débil
  2 = moderado
  3 = fuerte / confirmado

IMPORTANTE (ver Cap. 1 del libro): esto es un indicador algorítmico de
triage, NO una determinación de responsabilidad legal ni una acusación.
"""

from dataclasses import dataclass, field
from enum import Enum
from datetime import date
from typing import Optional


class VinculoExterno(str, Enum):
    EXOGENO_DIRECTO = "exogeno_directo"       # score 3
    PROXY_HIBRIDO = "proxy_hibrido"           # score 2
    ENDOGENO_ALINEADO = "endogeno_alineado"   # score 1
    MIMETICO = "mimetico"                     # score 1
    SIN_VINCULO = "sin_vinculo"               # score 0


VINCULO_SCORE = {
    VinculoExterno.EXOGENO_DIRECTO: 3,
    VinculoExterno.PROXY_HIBRIDO: 2,
    VinculoExterno.ENDOGENO_ALINEADO: 1,
    VinculoExterno.MIMETICO: 1,
    VinculoExterno.SIN_VINCULO: 0,
}


class Clasificacion(str, Enum):
    CONFIRMADO = "confirmado"                          # Confirmed Strategic Corruption
    ENTORNO_DEPENDENCIA_FUERTE = "entorno_dependencia_fuerte"  # Strategic Corruption Environment / Strong Dependency Case
    ZONA_GRIS = "zona_gris"                             # Grey-Zone Strategic Influence
    FUERA_DE_ALCANCE = "fuera_de_alcance"                # Ordinary/Domestic Corruption o sin dimensión geopolítica


class NivelAlerta(str, Enum):
    CRITICO = "CRITICO"
    ALTO = "ALTO"
    MEDIO = "MEDIO"
    BAJO = "BAJO"
    VIGILAR = "VIGILAR"


@dataclass
class Vector:
    slug: str
    sector: str
    actor_extranjero: str
    pais_origen: str
    mecanismo: str
    contraparte_argentina: Optional[str] = None
    regimen_legal: Optional[str] = None

    # Elementos del classification test (0-3, ver docstring)
    score_induccion: int = 0
    score_abuso_autoridad: int = 0
    score_efecto_estrategico: int = 0
    vinculo_externo: VinculoExterno = VinculoExterno.SIN_VINCULO

    fecha_deteccion: date = field(default_factory=date.today)
    notas: str = ""

    def __post_init__(self):
        for campo, valor in [
            ("score_induccion", self.score_induccion),
            ("score_abuso_autoridad", self.score_abuso_autoridad),
            ("score_efecto_estrategico", self.score_efecto_estrategico),
        ]:
            if not 0 <= valor <= 3:
                raise ValueError(f"{campo} debe estar entre 0 y 3, recibido {valor}")

    @property
    def score_vinculo_externo(self) -> int:
        return VINCULO_SCORE[self.vinculo_externo]


@dataclass
class ResultadoClasificacion:
    vector_slug: str
    clasificacion: Clasificacion
    nivel_alerta: NivelAlerta
    detalle: str
    scores: dict


def clasificar(v: Vector) -> ResultadoClasificacion:
    """
    Aplica las reglas de clasificación del framework NEST.

    Reglas (en orden de evaluación):

    1. CONFIRMADO — Confirmed Strategic Corruption
       Los 4 elementos presentes con fuerza moderada o mayor:
       inducción >= 2 AND abuso_autoridad >= 2 AND
       efecto_estrategico >= 2 AND vinculo_externo >= 2

    2. ENTORNO_DEPENDENCIA_FUERTE — Strategic Corruption Environment /
       Strong Dependency Case
       Efecto estratégico y vínculo externo claros, pero inducción o
       abuso de autoridad todavía indirectos/no probados:
       efecto_estrategico >= 2 AND vinculo_externo >= 2 AND
       NOT (inducción >= 2 AND abuso_autoridad >= 2)

    3. ZONA_GRIS — Grey-Zone Strategic Influence
       Ajuste legal/político alineado externamente, sin evidencia de
       incentivo transaccional:
       (efecto_estrategico >= 1 OR vinculo_externo >= 1) AND
       inducción == 0 AND abuso_autoridad == 0

    4. FUERA_DE_ALCANCE — Ordinary/Domestic Corruption o sin dimensión
       geopolítica: no cumple ninguna regla anterior (vínculo externo
       nulo/débil y efecto estratégico nulo/débil).
    """
    i = v.score_induccion
    a = v.score_abuso_autoridad
    e = v.score_efecto_estrategico
    ext = v.score_vinculo_externo

    if i >= 2 and a >= 2 and e >= 2 and ext >= 2:
        clasificacion = Clasificacion.CONFIRMADO
        detalle = "Confluencia comprobable de los 4 elementos constitutivos."
    elif e >= 2 and ext >= 2 and not (i >= 2 and a >= 2):
        clasificacion = Clasificacion.ENTORNO_DEPENDENCIA_FUERTE
        detalle = (
            "Efecto estratégico y vínculo externo claros; inducción y/o "
            "abuso de autoridad aún indirectos o sin probar."
        )
    elif (e >= 1 or ext >= 1) and i == 0 and a == 0:
        clasificacion = Clasificacion.ZONA_GRIS
        detalle = (
            "Alineamiento legal/político con actor externo, sin evidencia "
            "de incentivo transaccional ni abuso de autoridad."
        )
    else:
        clasificacion = Clasificacion.FUERA_DE_ALCANCE
        detalle = "Falta dimensión geopolítica sostenida o vínculo con actor externo relevante."

    nivel_alerta = _nivel_alerta(clasificacion, e, ext)

    return ResultadoClasificacion(
        vector_slug=v.slug,
        clasificacion=clasificacion,
        nivel_alerta=nivel_alerta,
        detalle=detalle,
        scores={
            "induccion": i,
            "abuso_autoridad": a,
            "efecto_estrategico": e,
            "vinculo_externo": ext,
        },
    )


def _nivel_alerta(clasificacion: Clasificacion, efecto: int, vinculo: int) -> NivelAlerta:
    if clasificacion == Clasificacion.CONFIRMADO:
        return NivelAlerta.CRITICO
    if clasificacion == Clasificacion.ENTORNO_DEPENDENCIA_FUERTE:
        return NivelAlerta.ALTO if (efecto == 3 or vinculo == 3) else NivelAlerta.MEDIO
    if clasificacion == Clasificacion.ZONA_GRIS:
        return NivelAlerta.MEDIO if (efecto >= 1 and vinculo >= 1) else NivelAlerta.BAJO
    return NivelAlerta.VIGILAR


if __name__ == "__main__":
    import json
    from pathlib import Path

    seed_path = Path(__file__).parent / "seed_vectores.json"
    with open(seed_path, encoding="utf-8") as f:
        vectores_raw = json.load(f)

    print(f"{'VECTOR':35s} {'CLASIFICACION':28s} {'ALERTA':8s} SCORES")
    print("-" * 100)
    for raw in vectores_raw:
        v = Vector(
            slug=raw["slug"],
            sector=raw["sector"],
            actor_extranjero=raw["actor_extranjero"],
            pais_origen=raw["pais_origen"],
            mecanismo=raw["mecanismo"],
            contraparte_argentina=raw.get("contraparte_argentina"),
            regimen_legal=raw.get("regimen_legal"),
            score_induccion=raw["score_induccion"],
            score_abuso_autoridad=raw["score_abuso_autoridad"],
            score_efecto_estrategico=raw["score_efecto_estrategico"],
            vinculo_externo=VinculoExterno(raw["vinculo_externo"]),
        )
        r = clasificar(v)
        print(
            f"{r.vector_slug:35s} {r.clasificacion.value:28s} {r.nivel_alerta.value:8s} {r.scores}"
        )
