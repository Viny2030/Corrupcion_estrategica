"""
scoring.py

Mismo classification test de 4 elementos del framework NEST que
scoring_engine.py (fuera de este paquete). Se reimplementa acá, sin
imports cruzados, para que vectores_api/ sea un paquete autocontenido
que se pueda copiar/desplegar solo.
"""

from dataclasses import dataclass

from models import Clasificacion, NivelAlerta, VinculoExterno

VINCULO_SCORE = {
    VinculoExterno.exogeno_directo: 3,
    VinculoExterno.proxy_hibrido: 2,
    VinculoExterno.endogeno_alineado: 1,
    VinculoExterno.mimetico: 1,
    VinculoExterno.sin_vinculo: 0,
}


@dataclass
class ResultadoClasificacion:
    clasificacion: Clasificacion
    nivel_alerta: NivelAlerta
    detalle: str
    scores: dict


def clasificar(
    score_induccion: int,
    score_abuso_autoridad: int,
    score_efecto_estrategico: int,
    vinculo_externo: VinculoExterno,
) -> ResultadoClasificacion:
    for nombre, valor in [
        ("score_induccion", score_induccion),
        ("score_abuso_autoridad", score_abuso_autoridad),
        ("score_efecto_estrategico", score_efecto_estrategico),
    ]:
        if not 0 <= valor <= 3:
            raise ValueError(f"{nombre} debe estar entre 0 y 3, recibido {valor}")

    i, a, e = score_induccion, score_abuso_autoridad, score_efecto_estrategico
    ext = VINCULO_SCORE[vinculo_externo]

    if i >= 2 and a >= 2 and e >= 2 and ext >= 2:
        clasificacion = Clasificacion.confirmado
        detalle = "Confluencia comprobable de los 4 elementos constitutivos."
    elif e >= 2 and ext >= 2 and not (i >= 2 and a >= 2):
        clasificacion = Clasificacion.entorno_dependencia_fuerte
        detalle = (
            "Efecto estratégico y vínculo externo claros; inducción y/o "
            "abuso de autoridad aún indirectos o sin probar."
        )
    elif (e >= 1 or ext >= 1) and i == 0 and a == 0:
        clasificacion = Clasificacion.zona_gris
        detalle = (
            "Alineamiento legal/político con actor externo, sin evidencia "
            "de incentivo transaccional ni abuso de autoridad."
        )
    else:
        clasificacion = Clasificacion.fuera_de_alcance
        detalle = "Falta dimensión geopolítica sostenida o vínculo con actor externo relevante."

    nivel_alerta = _nivel_alerta(clasificacion, e, ext)

    return ResultadoClasificacion(
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
    if clasificacion == Clasificacion.confirmado:
        return NivelAlerta.CRITICO
    if clasificacion == Clasificacion.entorno_dependencia_fuerte:
        return NivelAlerta.ALTO if (efecto == 3 or vinculo == 3) else NivelAlerta.MEDIO
    if clasificacion == Clasificacion.zona_gris:
        return NivelAlerta.MEDIO if (efecto >= 1 and vinculo >= 1) else NivelAlerta.BAJO
    return NivelAlerta.VIGILAR
