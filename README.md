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
  estados extranjeros. Con CUIT verificado: Ganfeng, Zijin/Liex, Huawei, Ascentio/Emposat,
  Alpha Lithium/Uranium One-Rosatom, ICBC Argentina, COFCO. Sin CUIT propio (operan vía
  contrato/UTE interestatal, no vía VPU con entidad local): CNNC (Atucha III), China
  Gezhouba (represas Santa Cruz), CMEC (Belgrano Cargas), PowerChina (solar Cauchari) —
  el mismo patrón de "no aplica matching CUIT directo" que ya tenía CNNC. Sinopec queda
  como entrada histórica (cerrada, divestment 2026).
- **`schema_enablers_ecosistema.sql`** + **`seed_enablers.json`** — extensión para el
  "enabling ecosystem" del libro (abogados, auditoras, bancos, academia, medios). Usa
  un campo `nivel_confianza` (confirmado/reportado/inferido/descartado) porque, a
  diferencia de los vectores, la representación legal de estas empresas casi nunca es
  pública. Hoy tiene 4 entradas confirmadas (Marval O'Farrell Mairal / Luis Lucero;
  Beccar Varela y Clifford Chance como asesores de ICBC en la compra a Standard Bank;
  Bruchou Fernández Madero & Lombardi como asesor del vendedor) y 1 reportada (apoderado
  de Huawei, registro BORA vencido en 2021). Zijin, Ganfeng y COFCO siguen sin
  representación legal identificada — ver `pendientes_de_verificar` en el JSON.

### 2. Motor de clasificación

- **`scoring_engine.py`** — implementación standalone del classification test de 4
  elementos. `clasificar(Vector) -> ResultadoClasificacion` con las 4 reglas de
  decisión (confirmado / entorno de dependencia fuerte / zona gris / fuera de alcance)
  y el mapeo de `vinculo_externo` a score, incluida la corrección de `mimetico` → 0
  (el libro lo excluye explícitamente del alcance de strategic corruption, p.15 — no es
  un vínculo débil, es una exclusión categórica). Corrible standalone:
  `python scoring_engine.py` imprime la clasificación de los 16 vectores del seed.
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
  server-rendered, scrapeable directo para avisos individuales; la búsqueda por texto
  libre sigue bloqueada, ver abajo), BCRA (**desbloqueado 18-ago-2026**: el índice de
  noticias en `bcra.gob.ar/Noticias/` es HTML server-rendered y `BcraScraper.
  obtener_comunicados_swap()` ya funciona end-to-end), y RIGI (sigue bloqueado: el panel
  público solo trae proyecciones agregadas por sector/año en un `<script>` inline, sin
  ningún endpoint `/api/*` ni fetch() visible en el HTML crudo — los contadores de
  "Proyectos aprobados" se llenan recién al elegir una provincia, vía AJAX que no se
  puede capturar sin ejecutar JS real). No inventa endpoints que no verificó.
- **`robot_diario.py`** — robot de ingesta diaria, nuevo (18-ago-2026). Trae los
  vectores activos desde la API en vivo, corre `BcraScraper` contra los comunicados más
  recientes, matchea por palabras clave específicas de `actor_extranjero`/
  `contraparte_argentina` (no de `sector`/`pais_origen`, que dan demasiados falsos
  positivos — "China" solo matchea 16/16 vectores), deduplica contra evidencia/
  novedades ya registradas (`GET /api/vectores/{slug}/evidencia` y `/actualizaciones`,
  nuevos endpoints agregados para esto) y postea novedad + evidencia. **Corre en
  dry-run por default** — necesita `--apply` para escribir de verdad en la API pública;
  ver "Estado y próximos pasos" para la política de cuándo usar `--apply` en la corrida
  programada.
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
  (`POST` + `GET /api/vectores/{slug}/evidencia`), novedades de la corrida diaria/semanal
  (`POST` + `GET /api/vectores/{slug}/actualizacion(es)` — los GET son nuevos,
  18-ago-2026, para que `robot_diario.py` pueda deduplicar por URL antes de postear).
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

### 6. Diagrama y panel

- **`arquitectura_modulo_vectores_influencia.svg`** — flujo de 8 capas: Fuentes →
  Ingesta → Padrón/Matcher → Tabla madre → Motor de Scoring → Clasificación → API →
  Consumo (los 9 monitores + IRI).
- **`static/index.html`** — panel visual, autocontenido (abrí el archivo directo en el
  navegador, no necesita servidor). Tiene dos pestañas:
  - **Panel**: KPIs por nivel de alerta, tabla filtrable (sector/clasificación/alerta/
    búsqueda libre), detalle de cada vector al hacer click, sección de enablers y
    resumen del marco legal.
  - **Manual de uso**: explica qué es la plataforma, la diferencia entre "mecanismo"
    (categoría fija asignada a mano) y "clasificación" (calculada sola de los 4
    scores) con ejemplos reales de la base, los 4 niveles de clasificación y 5 de
    alerta, cómo filtrar, el glosario (RIGI, VPU, SOE, Layer I/II, puerta giratoria), y
    una sección de marco legal de la publicación (Ley 27.275, Ley 25.326, doctrina
    Campillay, doctrina de la real malicia — no es asesoramiento legal, es para que lo
    revise un abogado antes de publicar el panel fuera de este entorno).
  - Hoy lee `seed_vectores.json`/`seed_enablers.json` embebidos como array JS y calcula
    la clasificación en el navegador (misma lógica que `vectores_api/scoring.py`, ver
    banner amarillo dentro del panel). Para datos vivos: reemplazar el array `VECTORES`
    por un `fetch('/api/vectores')` una vez que `vectores_api/` esté corriendo.

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

**Actualización 18-ago-2026** — esta corrida sí tuvo sandbox de ejecución real (a
diferencia del pase anterior, bloqueado por espacio en disco): se instalaron las
dependencias, se corrió `uvicorn` de verdad contra SQLite local, se probaron los
endpoints nuevos (`GET .../evidencia`, `GET .../actualizaciones`) con curl, y se corrió
`robot_diario.py` en dry-run y en `--apply` contra el servidor local (incluida una
segunda corrida para confirmar que el dedup funciona: 0 hallazgos reposteados). También
se corrió `python scoring_engine.py` contra el `seed_vectores.json` actualizado (18
entradas, clasifica sin errores). Lo que sigue sin poder probarse de punta a punta es
`ingestion_fuentes_reales.py::BoraScraper.buscar()` y `RigiScraper` (ver abajo — ambos
necesitan un navegador real, no alcanza con requests).

Pendientes concretos, en orden de lo más al menos bloqueado:
- **`BoraScraper.buscar()` y `RigiScraper`**: siguen bloqueados. Confirmado de nuevo hoy
  con fetch real (sin navegador): `/busquedaAvanzada/all?texto=...` devuelve HTTP 200
  sin resultados embebidos (arma la consulta vía JS), y el panel RIGI no expone ningún
  endpoint `/api/*` en el HTML crudo. Requieren la extensión Claude in Chrome conectada
  para inspeccionar el Network tab — no hay ningún navegador conectado a esta cuenta
  todavía.
- **BCRA**: desbloqueado esta corrida — ver `ingestion_fuentes_reales.py` y
  `robot_diario.py` arriba.
- **Enablers vía IGJ**: parcialmente resuelto. Se confirmó representación legal para el
  vector ICBC (Beccar Varela / Clifford Chance). Sigue pendiente para Zijin, Ganfeng,
  COFCO y el apoderado actual de Huawei — ver `pendientes_de_verificar` en
  `seed_enablers.json` para el detalle de qué se buscó y qué falta.
- **Robot diario**: código funcional (`robot_diario.py`), pero **no se dejó corriendo
  automáticamente todavía** — la decisión de si la corrida programada debe usar
  `--apply` (publica novedades solas, sin revisión humana previa, en la base pública que
  alimenta el dashboard) o quedarse en modo reporte/dry-run (junta hallazgos, un humano
  los aplica) queda pendiente de decisión de Vicente. Mientras tanto solo cubre BCRA;
  BORA y RIGI se suman cuando se resuelvan los bloqueos de arriba.
- **Novedades de esta corrida, pendientes de aplicar a la base en vivo**: se investigó y
  redactó (con fuentes citadas) actualizaciones para `swap-bcra-pboc-tesoro-eeuu`
  (extensión del swap BCRA-PBOC de 3 a 5 años, 5-ago-2026), `litio-rigi-zijin-ganfeng`
  (nueva solicitud RIGI de Ganfeng por USD 3.000M vía Lithea/Lithium Argentina, y dato de
  Bloomberg Línea de que ~70% de la capacidad de litio en RIGI es de capital chino) y
  `hidrovia-parana-paraguay-dragado` (denuncia cruzada, no confirmada, sobre presunto
  capital chino oculto en el operador preadjudicado Jan de Nul vía su subcontratista
  Servimagnus). Están en `seed_vectores.json` (campo `notas`) pero **no se postearon
  todavía a la API en vivo** — falta decisión de Vicente sobre aplicarlas.
