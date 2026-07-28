"""
models.py — ORM equivalente a schema_vectores_influencia.sql

Se usa SQLAlchemy Enum (en vez de los tipos ENUM nativos de Postgres
del .sql) para que el mismo modelo corra igual en SQLite (desarrollo
local) y Postgres (producción, DATABASE_URL apuntando al mismo motor
que ya usan los otros monitores).
"""

import enum
from datetime import date, datetime

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Enum, ForeignKey, Integer,
    String, Text, JSON,
)
from sqlalchemy.orm import relationship

from database import Base


class CapaMecanismo(str, enum.Enum):
    capa_1_directo = "capa_1_directo"
    capa_2_habilitante = "capa_2_habilitante"


class VinculoExterno(str, enum.Enum):
    exogeno_directo = "exogeno_directo"
    proxy_hibrido = "proxy_hibrido"
    endogeno_alineado = "endogeno_alineado"
    mimetico = "mimetico"  # el libro (p.15) lo excluye del alcance — ver scoring.py
    sin_vinculo = "sin_vinculo"


class MecanismoLibro(str, enum.Enum):
    """Los 10 mecanismos con nombre propio del libro (Tablas 4 y 5, cap. 1)."""
    # Layer I — mecanismos directos
    layer1_political_bribery_elite_inducement = "layer1_political_bribery_elite_inducement"
    layer1_legislative_manipulation = "layer1_legislative_manipulation"
    layer1_procurement_manipulation = "layer1_procurement_manipulation"
    layer1_revolving_doors = "layer1_revolving_doors"
    layer1_dependency_arrangements = "layer1_dependency_arrangements"
    # Layer II — entorno habilitante
    layer2_media_narrative_capture = "layer2_media_narrative_capture"
    layer2_infrastructure_investments = "layer2_infrastructure_investments"
    layer2_soft_power_projects = "layer2_soft_power_projects"
    layer2_lawfare_strategic_litigation = "layer2_lawfare_strategic_litigation"
    layer2_external_loans_grants = "layer2_external_loans_grants"
    # sin mecanismo materializado todavía
    vigilar_sin_mecanismo_confirmado = "vigilar_sin_mecanismo_confirmado"


class Clasificacion(str, enum.Enum):
    confirmado = "confirmado"
    entorno_dependencia_fuerte = "entorno_dependencia_fuerte"
    zona_gris = "zona_gris"
    fuera_de_alcance = "fuera_de_alcance"


class NivelAlerta(str, enum.Enum):
    CRITICO = "CRITICO"
    ALTO = "ALTO"
    MEDIO = "MEDIO"
    BAJO = "BAJO"
    VIGILAR = "VIGILAR"


class VectorInfluencia(Base):
    __tablename__ = "vectores_influencia_extranjera"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String, unique=True, index=True, nullable=False)
    sector = Column(String, nullable=False)
    actor_extranjero = Column(String, nullable=False)
    pais_origen = Column(String, nullable=False)
    contraparte_argentina = Column(String, nullable=True)
    mecanismo = Column(Text, nullable=False)
    mecanismo_libro = Column(Enum(MecanismoLibro), nullable=False)
    mecanismo_libro_secundario = Column(Enum(MecanismoLibro), nullable=True)
    regimen_legal = Column(String, nullable=True)
    capa = Column(Enum(CapaMecanismo), nullable=False)

    score_induccion = Column(Integer, nullable=False)
    score_abuso_autoridad = Column(Integer, nullable=False)
    score_efecto_estrategico = Column(Integer, nullable=False)
    vinculo_externo = Column(Enum(VinculoExterno), nullable=False)

    clasificacion = Column(Enum(Clasificacion), nullable=False)
    nivel_alerta = Column(Enum(NivelAlerta), nullable=False)
    detalle_clasificacion = Column(Text, nullable=True)

    activo = Column(Boolean, default=True, nullable=False)
    fecha_deteccion = Column(Date, default=date.today, nullable=False)
    fecha_actualizacion = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    notas = Column(Text, default="")

    evidencias = relationship("VectorEvidencia", back_populates="vector", cascade="all, delete-orphan")
    actualizaciones = relationship("VectorActualizacion", back_populates="vector", cascade="all, delete-orphan")


class VectorEvidencia(Base):
    __tablename__ = "vector_evidencia"

    id = Column(Integer, primary_key=True, index=True)
    vector_id = Column(Integer, ForeignKey("vectores_influencia_extranjera.id"), nullable=False)
    tipo_fuente = Column(String, nullable=False)
    titulo = Column(String, nullable=False)
    url = Column(String, nullable=False)
    fecha_publicacion = Column(Date, nullable=True)
    fecha_registro = Column(DateTime, default=datetime.utcnow)

    vector = relationship("VectorInfluencia", back_populates="evidencias")


class VectorActualizacion(Base):
    __tablename__ = "vector_actualizaciones"

    id = Column(Integer, primary_key=True, index=True)
    vector_id = Column(Integer, ForeignKey("vectores_influencia_extranjera.id"), nullable=True)
    es_vector_nuevo = Column(Boolean, default=False, nullable=False)
    resumen = Column(Text, nullable=False)
    cambio_clasificacion = Column(Boolean, default=False, nullable=False)
    clasificacion_previa = Column(Enum(Clasificacion), nullable=True)
    clasificacion_nueva = Column(Enum(Clasificacion), nullable=True)
    fuentes_json = Column(JSON, nullable=True)
    fecha_corrida = Column(Date, default=date.today, nullable=False)

    vector = relationship("VectorInfluencia", back_populates="actualizaciones")
