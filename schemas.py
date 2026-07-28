"""schemas.py — modelos Pydantic para request/response de la API."""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from models import CapaMecanismo, Clasificacion, NivelAlerta, VinculoExterno


class VectorCreate(BaseModel):
    slug: str
    sector: str
    actor_extranjero: str
    pais_origen: str
    mecanismo: str
    contraparte_argentina: Optional[str] = None
    regimen_legal: Optional[str] = None
    capa: CapaMecanismo
    score_induccion: int = Field(ge=0, le=3)
    score_abuso_autoridad: int = Field(ge=0, le=3)
    score_efecto_estrategico: int = Field(ge=0, le=3)
    vinculo_externo: VinculoExterno
    notas: str = ""


class VectorUpdateScore(BaseModel):
    """Para recalcular clasificación tras una novedad (ej. detectada por la corrida semanal)."""
    score_induccion: Optional[int] = Field(default=None, ge=0, le=3)
    score_abuso_autoridad: Optional[int] = Field(default=None, ge=0, le=3)
    score_efecto_estrategico: Optional[int] = Field(default=None, ge=0, le=3)
    vinculo_externo: Optional[VinculoExterno] = None
    notas: Optional[str] = None


class VectorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    sector: str
    actor_extranjero: str
    pais_origen: str
    contraparte_argentina: Optional[str]
    mecanismo: str
    regimen_legal: Optional[str]
    capa: CapaMecanismo
    score_induccion: int
    score_abuso_autoridad: int
    score_efecto_estrategico: int
    vinculo_externo: VinculoExterno
    clasificacion: Clasificacion
    nivel_alerta: NivelAlerta
    detalle_clasificacion: Optional[str]
    activo: bool
    fecha_deteccion: date
    fecha_actualizacion: Optional[datetime]
    notas: Optional[str]


class EvidenciaCreate(BaseModel):
    tipo_fuente: str
    titulo: str
    url: str
    fecha_publicacion: Optional[date] = None


class EvidenciaOut(EvidenciaCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    vector_id: int


class NovedadIn(BaseModel):
    resumen: str
    es_vector_nuevo: bool = False
    cambio_clasificacion: bool = False
    fuentes: list[dict] = []


class AlertaOut(BaseModel):
    slug: str
    sector: str
    actor_extranjero: str
    clasificacion: Clasificacion
    nivel_alerta: NivelAlerta
    plataforma_consultante: str
