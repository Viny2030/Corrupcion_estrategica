"""
main.py — entrypoint FastAPI del módulo Vectores de Influencia Estatal
Extranjera.

Correr local (con el venv activado):
    pip install -r requirements.txt
    uvicorn main:app --reload

Docs interactivas: http://127.0.0.1:8000/docs

Para apuntar a Postgres en vez de SQLite local:
    export DATABASE_URL=postgresql://usuario:pass@host:5432/mapa_transparencia
"""
import os
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse

from database import Base, SessionLocal, engine
from routers import alertas, vectores
from seed import cargar_seed

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        n = cargar_seed(db, forzar=False)
        if n:
            print(f"[startup] {n} vectores cargados desde seed_vectores.json")
    finally:
        db.close()
    yield


app = FastAPI(
    title="Vectores de Influencia Estatal Extranjera",
    description=(
        "Módulo satélite del ecosistema Mapa_Transparencia — detección "
        "de corrupción estratégica bajo el framework NEST. Alimenta la "
        "dimensión R_Internacional del IRI vía /api/alertas."
    ),
    version="0.2.0",
    lifespan=lifespan,
)

app.include_router(vectores.router)
app.include_router(alertas.router)


@app.get("/", tags=["dashboard"])
def root():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health", tags=["health"])
def health():
    from database import DATABASE_URL
    return {
        "status": "ok",
        "modulo": "vectores-influencia-estatal-extranjera",
        "base": "postgres" if DATABASE_URL.startswith("postgres") else "sqlite (se borra en cada deploy)",
        "escritura_habilitada": bool(os.getenv("ROBOT_TOKEN")),
    }


@app.get("/frescura.js", include_in_schema=False)
def frescura_js():
    return FileResponse(STATIC_DIR / "frescura.js", media_type="application/javascript")


@app.get("/api/frescura", tags=["health"])
def frescura():
    """Ficha de frescura (formato común del ecosistema, ver frescura.py): de
    dónde sale cada dato, qué período cubre, cuándo se cargó y si está atrasado."""
    from sqlalchemy import func
    from frescura import evaluar
    from models import VectorActualizacion, VectorInfluencia

    db = SessionLocal()
    try:
        vectores = db.query(func.count(VectorInfluencia.id)).scalar() or 0
        ultima = db.query(func.max(VectorActualizacion.fecha_corrida)).scalar()
    finally:
        db.close()
    return evaluar("corrupcion", [
        {"id": "vectores", "dato": "Vectores de influencia estatal extranjera", "fuente": "Relevamiento propio sobre fuentes públicas",
         "periodo": f"{vectores} vectores", "ultima_carga": None, "frecuencia": "manual"},
        {"id": "novedades", "dato": "Novedades detectadas por el robot", "fuente": "BCRA · Boletín Oficial",
         "periodo": f"última registrada el {ultima}" if ultima else "sin novedades registradas", "ultima_carga": ultima,
         "frecuencia": "semanal",
         "nota": "Una corrida sin novedades no deja registro: por eso no tiene plazo y no detecta si el robot dejó de correr."},
    ])


@app.get("/dashboard", tags=["dashboard"])
def dashboard():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/libro", tags=["dashboard"])
def libro():
    return FileResponse(
        STATIC_DIR / "strategic_corruption.pdf",
        media_type="application/pdf",
        filename="static/strategic_corruption.pdf",
    )
