"""routers/vectores.py — CRUD de vectores + evidencia + novedades semanales."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import models
import schemas
from database import get_db
from scoring import clasificar

router = APIRouter(prefix="/api/vectores", tags=["vectores"])


@router.get("", response_model=list[schemas.VectorOut])
def listar_vectores(
    sector: Optional[str] = None,
    clasificacion: Optional[models.Clasificacion] = None,
    activo: bool = True,
    db: Session = Depends(get_db),
):
    query = db.query(models.VectorInfluencia).filter(models.VectorInfluencia.activo == activo)
    if sector:
        query = query.filter(models.VectorInfluencia.sector == sector)
    if clasificacion:
        query = query.filter(models.VectorInfluencia.clasificacion == clasificacion)
    return query.all()


@router.get("/{slug}", response_model=schemas.VectorOut)
def obtener_vector(slug: str, db: Session = Depends(get_db)):
    v = db.query(models.VectorInfluencia).filter(models.VectorInfluencia.slug == slug).first()
    if not v:
        raise HTTPException(404, "Vector no encontrado")
    return v


@router.post("", response_model=schemas.VectorOut, status_code=201)
def crear_vector(payload: schemas.VectorCreate, db: Session = Depends(get_db)):
    existente = db.query(models.VectorInfluencia).filter(models.VectorInfluencia.slug == payload.slug).first()
    if existente:
        raise HTTPException(409, "El vector ya existe, usar PATCH /api/vectores/{slug}")

    resultado = clasificar(
        payload.score_induccion, payload.score_abuso_autoridad,
        payload.score_efecto_estrategico, payload.vinculo_externo,
    )

    vector = models.VectorInfluencia(
        **payload.model_dump(),
        clasificacion=resultado.clasificacion,
        nivel_alerta=resultado.nivel_alerta,
        detalle_clasificacion=resultado.detalle,
        fecha_deteccion=date.today(),
    )
    db.add(vector)
    db.commit()
    db.refresh(vector)
    return vector


@router.patch("/{slug}", response_model=schemas.VectorOut)
def actualizar_scores(slug: str, payload: schemas.VectorUpdateScore, db: Session = Depends(get_db)):
    """Actualiza uno o más scores y recalcula clasificación automáticamente."""
    v = db.query(models.VectorInfluencia).filter(models.VectorInfluencia.slug == slug).first()
    if not v:
        raise HTTPException(404, "Vector no encontrado")

    for campo, valor in payload.model_dump(exclude_unset=True).items():
        setattr(v, campo, valor)

    resultado = clasificar(v.score_induccion, v.score_abuso_autoridad, v.score_efecto_estrategico, v.vinculo_externo)
    v.clasificacion = resultado.clasificacion
    v.nivel_alerta = resultado.nivel_alerta
    v.detalle_clasificacion = resultado.detalle

    db.commit()
    db.refresh(v)
    return v


@router.get("/{slug}/score")
def recalcular_score(slug: str, db: Session = Depends(get_db)):
    v = db.query(models.VectorInfluencia).filter(models.VectorInfluencia.slug == slug).first()
    if not v:
        raise HTTPException(404, "Vector no encontrado")
    resultado = clasificar(v.score_induccion, v.score_abuso_autoridad, v.score_efecto_estrategico, v.vinculo_externo)
    return {
        "slug": v.slug,
        "clasificacion": resultado.clasificacion,
        "nivel_alerta": resultado.nivel_alerta,
        "detalle": resultado.detalle,
        "scores": resultado.scores,
    }


@router.post("/{slug}/evidencia", response_model=schemas.EvidenciaOut, status_code=201)
def agregar_evidencia(slug: str, payload: schemas.EvidenciaCreate, db: Session = Depends(get_db)):
    v = db.query(models.VectorInfluencia).filter(models.VectorInfluencia.slug == slug).first()
    if not v:
        raise HTTPException(404, "Vector no encontrado")
    evidencia = models.VectorEvidencia(vector_id=v.id, **payload.model_dump())
    db.add(evidencia)
    db.commit()
    db.refresh(evidencia)
    return evidencia


@router.post("/{slug}/actualizacion", status_code=201)
def registrar_novedad(slug: str, novedad: schemas.NovedadIn, db: Session = Depends(get_db)):
    """
    Usado por la tarea semanal programada (búsqueda automatizada) para
    registrar hallazgos. Si es_vector_nuevo=True, el slug puede no
    existir todavía — queda en vector_actualizaciones con vector_id
    nulo, pendiente de alta manual.
    """
    v = db.query(models.VectorInfluencia).filter(models.VectorInfluencia.slug == slug).first()
    if not v and not novedad.es_vector_nuevo:
        raise HTTPException(404, "Vector no encontrado y no está marcado como nuevo")

    actualizacion = models.VectorActualizacion(
        vector_id=v.id if v else None,
        es_vector_nuevo=novedad.es_vector_nuevo,
        resumen=novedad.resumen,
        cambio_clasificacion=novedad.cambio_clasificacion,
        fuentes_json=novedad.fuentes,
        fecha_corrida=date.today(),
    )
    db.add(actualizacion)
    db.commit()
    db.refresh(actualizacion)
    return {"id": actualizacion.id, "slug": slug, "registrado": True}
