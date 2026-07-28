"""
seed.py

Carga ../seed_vectores.json a la base. Se puede correr standalone
(`python seed.py`) o llamar a cargar_seed(db) desde el startup de la
app (ver main.py).
"""

import json
from pathlib import Path

from sqlalchemy.orm import Session

import models
from scoring import clasificar

SEED_PATH = Path(__file__).parent.parent / "seed_vectores.json"


def cargar_seed(db: Session, forzar: bool = False) -> int:
    """Carga el seed si la tabla está vacía (o siempre, si forzar=True). Devuelve cuántos vectores insertó."""
    if not forzar and db.query(models.VectorInfluencia).count() > 0:
        return 0

    if not SEED_PATH.exists():
        return 0

    with open(SEED_PATH, encoding="utf-8") as f:
        vectores_raw = json.load(f)

    insertados = 0
    for raw in vectores_raw:
        if db.query(models.VectorInfluencia).filter(models.VectorInfluencia.slug == raw["slug"]).first():
            continue

        vinculo = models.VinculoExterno(raw["vinculo_externo"])
        resultado = clasificar(
            raw["score_induccion"], raw["score_abuso_autoridad"],
            raw["score_efecto_estrategico"], vinculo,
        )

        # capa: se infiere heurísticamente si no viene en el seed —
        # Layer I si hay indicio de inducción/abuso, Layer II si no.
        capa = (
            models.CapaMecanismo.capa_1_directo
            if (raw["score_induccion"] > 0 or raw["score_abuso_autoridad"] > 0)
            else models.CapaMecanismo.capa_2_habilitante
        )

        vector = models.VectorInfluencia(
            slug=raw["slug"],
            sector=raw["sector"],
            actor_extranjero=raw["actor_extranjero"],
            pais_origen=raw["pais_origen"],
            contraparte_argentina=raw.get("contraparte_argentina"),
            mecanismo=raw["mecanismo"],
            regimen_legal=raw.get("regimen_legal"),
            capa=capa,
            score_induccion=raw["score_induccion"],
            score_abuso_autoridad=raw["score_abuso_autoridad"],
            score_efecto_estrategico=raw["score_efecto_estrategico"],
            vinculo_externo=vinculo,
            clasificacion=resultado.clasificacion,
            nivel_alerta=resultado.nivel_alerta,
            detalle_clasificacion=resultado.detalle,
            notas=raw.get("notas", ""),
        )
        db.add(vector)
        insertados += 1

    db.commit()
    return insertados


if __name__ == "__main__":
    from database import SessionLocal, Base, engine

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        n = cargar_seed(db, forzar=False)
        print(f"{n} vectores insertados desde {SEED_PATH.name}")
    finally:
        db.close()
