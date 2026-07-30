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


@app.get("/", tags=["health"])
def root():
    return {"status": "ok", "modulo": "vectores-influencia-estatal-extranjera"}


@app.get("/dashboard", tags=["dashboard"])
def dashboard():
    return FileResponse(STATIC_DIR / "index.html")
