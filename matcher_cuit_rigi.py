"""
matcher_cuit_rigi.py

Reutiliza la lógica de matching CUIT/AFIP de MEACI (que cruza el padrón
AFIP contra las 31 resoluciones OCDE/DOJ/SFO/PNF de soborno transnacional),
pero contra un padrón propio de empresas estatales/cuasi-estatales
extranjeras (SOEs), aplicado a los Vehículos de Proyecto Único (VPU)
aprobados bajo RIGI/Súper RIGI.

Fuentes reales a conectar en producción:
  - Registro RIGI (ARCA/AFIP):  https://www.arca.gob.ar/rigi/registros/default.asp
  - Web oficial de proyectos:   https://www.argentina.gob.ar/economia/rigi
  - Boletín Oficial (BORA):     decretos de aprobación de cada VPU

Este script funciona sobre datos ya extraídos (scrapeados) de esas
fuentes — el scraping en sí se resuelve con el mismo pipeline de
ingesta que ya usan Monitor de Contratos / MEACI (no se reinventa acá).
"""

import json
import re
from dataclasses import dataclass, asdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional


def normalizar_cuit(cuit: Optional[str]) -> Optional[str]:
    if not cuit:
        return None
    return re.sub(r"[^0-9]", "", cuit)


# Términos genéricos del sector que inflan artificialmente la similitud
# entre empresas NO relacionadas (ej. "Galan Lithium" vs "Ganfeng Litio"
# comparten "ARGENTINA" + "LITIO/LITHIUM" y sin este filtro rozan el
# umbral pese a no tener ningún vínculo real). Se excluyen del cálculo
# de similitud, no del nombre mostrado en el resultado.
STOPWORDS_SECTOR = {
    "SA", "SRL", "SAU", "ARGENTINA", "ARGENTINO", "ARGENTINA S",
    "LITIO", "LITHIUM", "MINERA", "MINING", "MINERIA", "GROUP",
    "GRUPO", "CO", "LTD", "CORP", "CORPORATION", "COMPANY", "TECH",
    "TECHNOLOGIES", "ENERGY", "ENERGIA",
}


def normalizar_nombre(nombre: str) -> str:
    nombre = nombre.upper()
    for sufijo in [" S.A.", " SA", " S.R.L.", " SRL", " S.A.U.", ".", ","]:
        nombre = nombre.replace(sufijo, "")
    tokens = [t for t in nombre.strip().split() if t not in STOPWORDS_SECTOR]
    return " ".join(tokens) if tokens else nombre.strip()


def similitud(a: str, b: str) -> float:
    return SequenceMatcher(None, normalizar_nombre(a), normalizar_nombre(b)).ratio()


@dataclass
class MatchResultado:
    vpu_empresa: str
    vpu_cuit: Optional[str]
    vpu_proyecto: str
    vpu_regimen: str
    vpu_provincia: str
    padron_razon_social: str
    padron_matriz: str
    padron_pais_origen: str
    tipo_match: str          # "cuit_exacto" | "nombre_similar" | "sin_match"
    score_similitud: float
    alerta: bool


def cargar_padron(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def cruzar_vpu_contra_padron(
    vpus: list[dict],
    padron: list[dict],
    umbral_similitud_nombre: float = 0.75,
) -> list[MatchResultado]:
    """
    Para cada VPU aprobado, intenta matchear contra el padrón de SOEs
    extranjeras primero por CUIT exacto, luego por similitud de nombre
    (fallback para cuando el VPU es una razón social distinta de la
    empresa operativa conocida, ej. sociedades vehículo con otro nombre).
    """
    resultados = []

    for vpu in vpus:
        vpu_cuit_norm = normalizar_cuit(vpu.get("cuit"))
        mejor_match = None
        mejor_score = 0.0
        mejor_tipo = "sin_match"

        for entrada in padron:
            padron_cuit_norm = normalizar_cuit(entrada.get("cuit"))

            # 1. Match exacto por CUIT
            if vpu_cuit_norm and padron_cuit_norm and vpu_cuit_norm == padron_cuit_norm:
                mejor_match = entrada
                mejor_score = 1.0
                mejor_tipo = "cuit_exacto"
                break

            # 2. Match por similitud de nombre (razón social o matriz)
            score_razon = similitud(vpu.get("empresa", ""), entrada.get("razon_social", ""))
            score_matriz = similitud(vpu.get("empresa", ""), entrada.get("matriz", ""))
            score = max(score_razon, score_matriz)

            if score > mejor_score:
                mejor_score = score
                mejor_match = entrada
                mejor_tipo = "nombre_similar"

        if mejor_match and mejor_score >= umbral_similitud_nombre:
            resultados.append(
                MatchResultado(
                    vpu_empresa=vpu.get("empresa", ""),
                    vpu_cuit=vpu.get("cuit"),
                    vpu_proyecto=vpu.get("proyecto", ""),
                    vpu_regimen=vpu.get("regimen", ""),
                    vpu_provincia=vpu.get("provincia", ""),
                    padron_razon_social=mejor_match["razon_social"],
                    padron_matriz=mejor_match["matriz"],
                    padron_pais_origen=mejor_match["pais_origen"],
                    tipo_match=mejor_tipo,
                    score_similitud=round(mejor_score, 3),
                    alerta=True,
                )
            )
        else:
            resultados.append(
                MatchResultado(
                    vpu_empresa=vpu.get("empresa", ""),
                    vpu_cuit=vpu.get("cuit"),
                    vpu_proyecto=vpu.get("proyecto", ""),
                    vpu_regimen=vpu.get("regimen", ""),
                    vpu_provincia=vpu.get("provincia", ""),
                    padron_razon_social="",
                    padron_matriz="",
                    padron_pais_origen="",
                    tipo_match="sin_match",
                    score_similitud=round(mejor_score, 3),
                    alerta=False,
                )
            )

    return resultados


if __name__ == "__main__":
    base = Path(__file__).parent
    padron = cargar_padron(base / "padron_soes_extranjeras.json")

    # Sample de VPUs aprobados — en producción esto viene del scraper
    # del registro RIGI (ARCA/AFIP) + BORA. Incluye los 2 casos reales
    # confirmados por búsqueda (Ganfeng, Zijin/Liex) más 2 controles
    # negativos (proyectos sin vínculo con SOEs extranjeras) para
    # verificar que el matcher no genera falsos positivos.
    vpus_sample = [
        {
            "empresa": "Ganfeng Litio Argentina S.A.",
            "cuit": "30-71642060-0",
            "proyecto": "Mariana / Pastos Grandes",
            "regimen": "RIGI1",
            "provincia": "Salta",
        },
        {
            "empresa": "Liex S.A.",
            "cuit": "30-71513288-1",
            "proyecto": "Tres Quebradas",
            "regimen": "RIGI1",
            "provincia": "Catamarca",
        },
        {
            "empresa": "Galan Lithium Argentina S.A.",
            "cuit": None,
            "proyecto": "El Hombre Muerto Oeste (HMW)",
            "regimen": "RIGI1",
            "provincia": "Catamarca",
        },
        {
            "empresa": "YPF Luz Solar S.A.",
            "cuit": None,
            "proyecto": "Parque Solar Las Heras",
            "regimen": "RIGI1",
            "provincia": "Mendoza",
        },
    ]

    resultados = cruzar_vpu_contra_padron(vpus_sample, padron)

    print(f"{'VPU / EMPRESA':32s} {'MATCH':22s} {'PAIS':10s} {'TIPO':16s} {'SCORE':6s} ALERTA")
    print("-" * 100)
    for r in resultados:
        print(
            f"{r.vpu_empresa:32s} {r.padron_razon_social or '—':22s} "
            f"{r.padron_pais_origen or '—':10s} {r.tipo_match:16s} "
            f"{r.score_similitud:<6} {r.alerta}"
        )

    alertas = [r for r in resultados if r.alerta]
    print(f"\n{len(alertas)}/{len(resultados)} VPUs con match a padrón de SOEs extranjeras.")
