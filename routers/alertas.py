"""
routers/alertas.py

Endpoint de integración consumido por el resto del ecosistema
(Mapa_Transparencia + 9 monitores), mismo patrón que ya usa MEACI
para alimentar la dimensión R_Internacional del IRI.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import models
from database import get_db

router = APIRouter(prefix="/api/alertas", tags=["alertas"])

ORDEN_ALERTA = ["VIGILAR", "BAJO", "MEDIO", "ALTO", "CRITICO"]


@router.get("")
def alertas(
    plataforma: str = Query("general", description="ej. 'iri', 'monitor_legislativo', 'monitor_contratos'"),
    nivel_minimo: str = Query("MEDIO", description="CRITICO|ALTO|MEDIO|BAJO|VIGILAR"),
    db: Session = Depends(get_db),
):
    nivel_minimo = nivel_minimo.upper()
    if nivel_minimo not in ORDEN_ALERTA:  # antes: ValueError → error 500
        raise HTTPException(422, f"nivel_minimo debe ser uno de {ORDEN_ALERTA}")
    idx_minimo = ORDEN_ALERTA.index(nivel_minimo)

    vectores = (
        db.query(models.VectorInfluencia)
        .filter(models.VectorInfluencia.activo.is_(True))
        .all()
    )

    salida = [
        {
            "slug": v.slug,
            "sector": v.sector,
            "actor_extranjero": v.actor_extranjero,
            "clasificacion": v.clasificacion,
            "nivel_alerta": v.nivel_alerta,
            "plataforma_consultante": plataforma,
        }
        for v in vectores
        if ORDEN_ALERTA.index(v.nivel_alerta.value) >= idx_minimo
    ]
    return {"plataforma": plataforma, "count": len(salida), "alertas": salida}
