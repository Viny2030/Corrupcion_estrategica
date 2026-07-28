"""
api_endpoints.py

Skeleton FastAPI del módulo "Vectores de Influencia Estatal Extranjera".
Pensado para montarse junto a los 9 monitores existentes y exponer el
mismo estilo de API (/api/alertas?plataforma=X) que ya usa MEACI para
alimentar la dimensión R_Internacional del IRI.

Instalar:  pip install fastapi uvicorn pydantic --break-system-packages
Correr:    uvicorn api_endpoints:app --reload
"""

from datetime import date, datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from scoring_engine import (
    Vector,
    VinculoExterno,
    Clasificacion,
    clasificar,
)

app = FastAPI(
    title="Vectores de Influencia Estatal Extranjera",
    description="Módulo satélite del ecosistema Mapa_Transparencia — "
    "detección de corrupción estratégica bajo el framework NEST",
    version="0.1.0",
)

# ------------------------------------------------------------------
# En memoria para el esqueleto. Reemplazar por el repositorio real
# (Postgres, ver schema_vectores_influencia.sql) en producción.
# ------------------------------------------------------------------
_DB: dict[str, dict] = {}


class VectorIn(BaseModel):
    slug: str
    sector: str
    actor_extranjero: str
    pais_origen: str
    mecanismo: str
    contraparte_argentina: Optional[str] = None
    regimen_legal: Optional[str] = None
    score_induccion: int
    score_abuso_autoridad: int
    score_efecto_estrategico: int
    vinculo_externo: VinculoExterno
    notas: str = ""


class NovedadIn(BaseModel):
    resumen: str
    es_vector_nuevo: bool = False
    cambio_clasificacion: bool = False
    fuentes: list[dict] = []  # [{"titulo": ..., "url": ...}]


# ------------------------------------------------------------------
# CRUD de vectores
# ------------------------------------------------------------------
@app.get("/api/vectores")
def listar_vectores(
    sector: Optional[str] = None,
    clasificacion: Optional[Clasificacion] = None,
    activo: bool = True,
):
    """Lista todos los vectores, filtrable por sector/clasificación."""
    resultados = [v for v in _DB.values() if v.get("activo", True) == activo]
    if sector:
        resultados = [v for v in resultados if v["sector"] == sector]
    if clasificacion:
        resultados = [v for v in resultados if v["clasificacion"] == clasificacion]
    return resultados


@app.get("/api/vectores/{slug}")
def obtener_vector(slug: str):
    v = _DB.get(slug)
    if not v:
        raise HTTPException(404, "Vector no encontrado")
    return v


@app.post("/api/vectores")
def crear_vector(payload: VectorIn):
    """Alta de un nuevo vector. Calcula clasificación automáticamente."""
    if payload.slug in _DB:
        raise HTTPException(409, "El vector ya existe, usar PATCH /api/vectores/{slug}/score")

    vector = Vector(
        slug=payload.slug,
        sector=payload.sector,
        actor_extranjero=payload.actor_extranjero,
        pais_origen=payload.pais_origen,
        mecanismo=payload.mecanismo,
        contraparte_argentina=payload.contraparte_argentina,
        regimen_legal=payload.regimen_legal,
        score_induccion=payload.score_induccion,
        score_abuso_autoridad=payload.score_abuso_autoridad,
        score_efecto_estrategico=payload.score_efecto_estrategico,
        vinculo_externo=payload.vinculo_externo,
        notas=payload.notas,
    )
    resultado = clasificar(vector)

    registro = {
        **payload.dict(),
        "clasificacion": resultado.clasificacion.value,
        "nivel_alerta": resultado.nivel_alerta.value,
        "detalle_clasificacion": resultado.detalle,
        "activo": True,
        "fecha_deteccion": date.today().isoformat(),
        "fecha_actualizacion": datetime.utcnow().isoformat(),
    }
    _DB[payload.slug] = registro
    return registro


@app.get("/api/vectores/{slug}/score")
def recalcular_score(slug: str):
    """Recalcula la clasificación de un vector con sus scores actuales."""
    v = _DB.get(slug)
    if not v:
        raise HTTPException(404, "Vector no encontrado")

    vector = Vector(
        slug=v["slug"],
        sector=v["sector"],
        actor_extranjero=v["actor_extranjero"],
        pais_origen=v["pais_origen"],
        mecanismo=v["mecanismo"],
        contraparte_argentina=v.get("contraparte_argentina"),
        regimen_legal=v.get("regimen_legal"),
        score_induccion=v["score_induccion"],
        score_abuso_autoridad=v["score_abuso_autoridad"],
        score_efecto_estrategico=v["score_efecto_estrategico"],
        vinculo_externo=VinculoExterno(v["vinculo_externo"]),
    )
    resultado = clasificar(vector)
    return {
        "slug": resultado.vector_slug,
        "clasificacion": resultado.clasificacion.value,
        "nivel_alerta": resultado.nivel_alerta.value,
        "detalle": resultado.detalle,
        "scores": resultado.scores,
    }


# ------------------------------------------------------------------
# Ingesta de novedades (usado por el scheduled task semanal)
# ------------------------------------------------------------------
@app.post("/api/vectores/{slug}/actualizacion")
def registrar_novedad(slug: str, novedad: NovedadIn):
    """
    Registra una novedad semanal detectada por la búsqueda automatizada.
    Si es un vector completamente nuevo (es_vector_nuevo=True), slug
    puede no existir todavía en _DB — queda en cola para alta manual.
    """
    if slug not in _DB and not novedad.es_vector_nuevo:
        raise HTTPException(404, "Vector no encontrado y no está marcado como nuevo")

    return {
        "slug": slug,
        "es_vector_nuevo": novedad.es_vector_nuevo,
        "resumen": novedad.resumen,
        "cambio_clasificacion": novedad.cambio_clasificacion,
        "fuentes": novedad.fuentes,
        "fecha_corrida": date.today().isoformat(),
    }


# ------------------------------------------------------------------
# Hook de integración: alimenta la dimensión R_Internacional del IRI,
# mismo patrón que ya usa MEACI en /api/alertas?plataforma=iri
# ------------------------------------------------------------------
@app.get("/api/alertas")
def alertas(
    plataforma: str = Query(..., description="ej. 'iri', 'monitor_legislativo', 'monitor_contratos'"),
    nivel_minimo: str = Query("MEDIO", description="CRITICO|ALTO|MEDIO|BAJO|VIGILAR"),
):
    """
    Endpoint de integración consumido por otros monitores del ecosistema.
    Devuelve los vectores activos con nivel de alerta >= nivel_minimo,
    en formato compacto para alimentar dashboards externos (ej. IRI).
    """
    orden_alerta = ["VIGILAR", "BAJO", "MEDIO", "ALTO", "CRITICO"]
    idx_minimo = orden_alerta.index(nivel_minimo)

    salida = []
    for v in _DB.values():
        if not v.get("activo", True):
            continue
        if orden_alerta.index(v["nivel_alerta"]) < idx_minimo:
            continue
        salida.append(
            {
                "slug": v["slug"],
                "sector": v["sector"],
                "actor_extranjero": v["actor_extranjero"],
                "clasificacion": v["clasificacion"],
                "nivel_alerta": v["nivel_alerta"],
                "plataforma_consultante": plataforma,
            }
        )
    return {"plataforma": plataforma, "count": len(salida), "alertas": salida}


# ------------------------------------------------------------------
# Vectores nuevos detectados por búsqueda abierta, pendientes de alta
# ------------------------------------------------------------------
@app.get("/api/vectores-candidatos")
def vectores_candidatos():
    """
    Lista de vectores detectados por la búsqueda semanal que todavía
    no fueron dados de alta formalmente en la tabla madre (requieren
    revisión manual antes de clasificar).
    """
    return {"mensaje": "Placeholder — conectar a vector_actualizaciones WHERE es_vector_nuevo=true AND vector_id IS NULL"}
