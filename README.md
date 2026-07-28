# Vectores de Influencia Estatal Extranjera

Módulo satélite del ecosistema **Mapa_Transparencia** (+ 9 monitores: Jefatura de
Gabinete, Monitor de Contratos, Monitor Legislativo Diputados/Senadores, Monitor
Judicial, Monitor DDJJ, Monitor IRI, Monitor de Ajuste Presupuestario, MEACI).

Operacionaliza el *Analytical Framework for Detecting, Assessing and Responding to
Strategic Corruption* del NEST Institute para detectar y clasificar casos en los que
estados extranjeros — primero China y Rusia — usan inversión, financiamiento o
infraestructura como palanca sobre decisiones públicas argentinas.

Alimenta la dimensión `R_Internacional` del IRI vía `/api/alertas?plataforma=iri`, con
el mismo patrón de integración que ya usa MEACI.

## Qué es esto y qué no es

Es un motor de triage: aplica una rúbrica de scoring reproducible a casos ya
investigados con fuentes públicas, para priorizar cuáles ameritan seguimiento y con qué
nivel de urgencia. **No** es una herramienta de acusación ni una determinación de
responsabilidad legal — el libro lo aclara explícitamente y el motor de scoring lo
repite en su docstring. Los cuatro elementos del classification test (inducción, abuso
de autoridad, efecto estratégico, vínculo externo) se puntúan 0-3 sobre evidencia
documentada, con fuente citada en `notas`.

## Cómo está organizado

### 1. Capa de datos — la tabla madre

- **`schema_vectores_influencia.sql`** — DDL Postgres. Cuatro tablas:
  `vectores_influencia_extranjera` (la tabla madre), `vector_evidencia` (fuentes por
  vector), `vector_actualizaciones` (historial de la corrida semanal),
  `vector_monitor_origen` (trazabilidad de qué monitor del ecosistema aportó el dato).
  Incluye los ENUMs `capa_mecanismo`, `tipo_vinculo_externo`, `mecanismo_libro` (los 10
  mecanismos con nombre propio del libro, Tablas 4 y 5), `clasificacion_final`,
  `nivel_alerta`.
- **`seed_vectores.json`** — los 16 vectores investigados y clasificados hasta ahora,
  cada uno con sector, actor extranjero, país de origen, mecanismo (texto libre +
  `mecanismo_libro` normalizado), régimen legal, los 4 scores del classification test,
  notas con las fuentes que sostienen cada score, y `activo` (uno cerrado: Sinopec
  Golfo San Jorge, divestment 2026).
- **`padron_soes_extranjeras.json`** — registro de empresas estatales/vinculadas a
  estados extranjeros con CUIT verificado (Ganfeng, Zijin/Liex, Huawei, CNNC vía NA-SA,
  Ascentio/Emposat, Alpha Lithium/Uranium One-Rosatom, ICBC Argentina, COFCO, Sinopec
  histórico).
- **`schema_enablers_ecosistema.sql`** + **`seed_enablers.json`** — extensión para el
  "enabling ecosystem" del libro (abogados, auditoras, bancos, academia, medios). Usa
  un campo `nivel_confianza` (confirmado/reportado/inferido/descartado) porque, a
  diferencia de los vectores, la representación legal de estas empresas casi nunca es
  pública — solo hay un caso confirmado hasta ahora (ver más abajo).

### 2. Motor de clasificación

- **`scoring_engine.py`** — implementación standalone del classification test de 4
  elementos. `clasificar(Vector) -> ResultadoClasificacion` con las 4 reglas de
  decisión (confirmado / entorno de dependencia fuerte / zona gris / fuera de alcance)
  y el mapeo de `vinculo_externo` a score, incluida la corrección de `mimetico` → 0
  (el libro lo excluye explícitamente del alcance de strategic corruption, p.15 — no es
  un vínculo débil, es una exclusión categórica). Corrible standalone:
  `python scoring_engine.py` imprime la clasificación de los 13 vectores del seed.
- **`vectores_api/scoring.py`** — mismo motor, reimplementado sin imports cruzados para
  que el paquete `vectores_api/` sea autocontenido.

### 3. Matcher CUIT/AFIP

- **`matcher_cuit_rigi.py`** — cruza solicitudes de VPU (Vehículo de Proyecto Único,
  RIGI) contra el padrón de SOEs. Match exacto por CUIT normalizado + fallback de
  similitud de nombre (`difflib.SequenceMatcher`) con `STOPWORDS_SECTOR` para filtrar
  términos genéricos de sector/forma societaria — sin ese filtro, el matcher confundía
  falsamente "Galán Lithium" (australiana) con "Ganfeng Litio" solo por compartir
  "Argentina"/"Litio" en el nombre.

### 4. Ingesta

- **`ingestion_fuentes_reales.py`** — scrapers para BORA (confirmado: HTML
  server-rendered, scrapeable directo), y placeholders documentados con TODO explícito
  para el panel RIGI (JavaScript client-side, requiere inspección de Network tab antes
  de producción) y BCRA (índice de comunicados no confirmado en este pase). No inventa
  endpoints que no verificó.
- **`narrative_analysis_module.py`** — Módulo E del framework (Análisis Narrativo).
  Detecta repetición de talking points entre voceros/medios en ventanas de tiempo
  cortas, cambios súbitos de encuadre, y campañas de descalificación/litigios
  estratégicos contra periodistas u organismos de control. El caso semilla es
  `medios-china-daily-china-watch` (China Daily/"China Watch" insertado en El Cronista
  y La Capital desde 2016). Fuentes a conectar: taquigráficas de Diputados/Senado, RSS
  de prensa especializada.

### 5. API — `vectores_api/`

Paquete FastAPI real (no skeleton), con DB vía SQLAlchemy:

- `main.py` — entrypoint, seedea la DB al arrancar si está vacía.
- `database.py` — SQLite local por default (`vectores.db`), o Postgres si se define
  `DATABASE_URL` (mismo motor que el resto del ecosistema).
- `models.py` — ORM equivalente al `.sql`, con `Enum` de SQLAlchemy para compatibilidad
  cross-DB.
- `schemas.py` — Pydantic (`VectorCreate`, `VectorOut`, `VectorUpdateScore`,
  `EvidenciaCreate/Out`, `NovedadIn`, `AlertaOut`).
- `seed.py` — carga `../seed_vectores.json` si la tabla está vacía; normaliza
  `mecanismo_libro`/`mecanismo_libro_secundario` con fallback defensivo a
  `vigilar_sin_mecanismo_confirmado` si algún valor no matchea el enum.
- `routers/vectores.py` — CRUD (`GET/POST /api/vectores`, `GET/PATCH /api/vectores/{slug}`,
  recalcula clasificación automáticamente al actualizar scores), evidencia
  (`POST /api/vectores/{slug}/evidencia`), novedades de la corrida semanal
  (`POST /api/vectores/{slug}/actualizacion`).
- `routers/alertas.py` — `GET /api/alertas?plataforma=X&nivel_minimo=Y`, el endpoint de
  integración que consumen el resto de los monitores (mismo patrón que MEACI).

**Correr localmente:**
```bash
cd vectores_api
pip install -r requirements.txt --break-system-packages
uvicorn main:app --reload
# docs interactivas en http://127.0.0.1:8000/docs
```

Para Postgres: `export DATABASE_URL=postgresql://usuario:pass@host:5432/mapa_transparencia`
antes de levantar. El esquema es el mismo que `schema_vectores_influencia.sql`.

`api_endpoints.py` (raíz) es el skeleton original con dict en memoria — quedó superado
por `vectores_api/`, se conserva como artefacto histórico.

### 6. Diagrama

- **`arquitectura_modulo_vectores_influencia.svg`** — flujo de 8 capas: Fuentes →
  Ingesta → Padrón/Matcher → Tabla madre → Motor de Scoring → Clasificación → API →
  Consumo (los 9 monitores + IRI).

### 7. Marco legal-institucional e investigaciones puntuales

- **`anexo_marco_legal_argentina.md`** — Argentina está alineada en los tres pilares
  clásicos (UNCAC ratificada 2006, GAFI/GAFILAT 4ª ronda aprobada oct-2024, OCDE
  Working Group on Bribery desde 2000), pero **no tiene mecanismo de screening de IED
  por seguridad nacional**: la Ley 21.382 es un régimen liberal de 1976 sin filtro de
  origen de capital, el RIGI está diseñado para atraer inversión no para filtrarla, y la
  única grieta (proyecto de Ley de Tierras, jul-2026, en debate) cubre solo tierras
  rurales — deja afuera litio, nuclear, telecom y puertos.
- **`puertas_giratorias_hallazgos.md`** — sin caso confirmado de puerta giratoria entre
  el Estado argentino y un actor chino/ruso en los tres nodos revisados (RIGI/litio,
  Atucha III/CNNC, ENACOM/Huawei). Sí hay un caso real documentado (secretario de
  Minería Luis Lucero, ex Marval O'Farrell Mairal, excusado de expedientes de mineras
  occidentales) que se registra como antecedente estructural a vigilar porque el mismo
  funcionario integra el comité que decide sobre litio chino.

## Los 10 mecanismos del libro (Tablas 4 y 5, cap. 1)

| Layer | Mecanismo | Vectores cargados hoy |
|---|---|---|
| I | Political bribery / elite inducement | (ninguno activo — `defensa-armamento-rusia-china` a vigilar) |
| I | Legislative manipulation | `litio-rigi-zijin-ganfeng`, `espacio-doble-uso-neuquen-rio-gallegos` |
| I | Procurement manipulation | (ninguno activo — `5g-enacom-huawei`, `hidrovia-parana-paraguay-dragado` a vigilar) |
| I | Revolving doors | (sin vector confirmado — ver `puertas_giratorias_hallazgos.md`) |
| I | Dependency arrangements | — |
| II | Media / narrative capture | `medios-china-daily-china-watch` |
| II | Infrastructure investments | `atucha-iii-cnnc`, `litio-tolillar-rosatom-uranium-one`, `agro-cofco-terminal-timbues`, `petroleo-sinopec-golfo-san-jorge-cerrado` (cerrado), `represas-santa-cruz-gezhouba`, `belgrano-cargas-cmec`, `solar-cauchari-jujuy-powerchina` |
| II | Soft power projects | `institutos-confucio-uba-unlp-unc-mendoza` |
| II | Lawfare / strategic litigation | — |
| II | External loans / grants | `swap-bcra-pboc-tesoro-eeuu`, `banca-icbc-argentina` |

## Estado y próximos pasos

Todo el código de este pase es correcto por trazado manual (revisión línea por línea de
la lógica de scoring, del matcher y de los endpoints) — el sandbox de ejecución estuvo
indisponible durante todo el desarrollo por falta de espacio en disco, así que nada se
corrió de punta a punta con un intérprete real. Antes de producción: correr
`pytest`/`uvicorn` de verdad, resolver los TODOs de `ingestion_fuentes_reales.py`
(endpoint RIGI vía devtools, índice de comunicados BCRA), y completar la verificación
de enablers vía IGJ (pendiente, ver `seed_enablers.json`).

Pendiente de decisión de Vicente: conectar el scheduled task semanal (ya configurado
para correr los lunes 8am) a estos scrapers reales en vez de al placeholder.
