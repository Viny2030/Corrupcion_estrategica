"""
database.py

Setup de SQLAlchemy. Por default usa SQLite local (vectores.db) para
correr sin dependencias externas. En producción, apuntar
DATABASE_URL a Postgres (mismo motor que usan los otros 9 monitores
del ecosistema) — el esquema es compatible, ver
../schema_vectores_influencia.sql para la versión DDL nativa de
Postgres con ENUMs (acá se modela equivalente con SQLAlchemy Enum,
que funciona en ambos backends).
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./vectores.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
