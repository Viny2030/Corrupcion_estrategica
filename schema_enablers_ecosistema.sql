-- ============================================================
-- Extensión: Ecosistema de Enablers
-- Basado en la lista de "enabling ecosystem" del libro (p.16): abogados,
-- escribanos, auditores, académicos, docentes universitarios,
-- profesionales de medios, empleados bancarios, ingenieros -- y en el
-- Actor Matrix (Tabla 3): actores estatales/no estatales x
-- target-country/source-aligned/intermediary-third-country.
--
-- IMPORTANTE (honestidad metodológica): a diferencia de la tabla madre
-- de vectores, que se construyó sobre casos con fuente pública directa,
-- la relación estudio-jurídico/auditora <-> empresa del padrón casi
-- nunca es pública (representación legal no se declara salvo en
-- litigios o registros societarios). Por eso esta tabla distingue
-- explícitamente nivel_confianza: la mayoría de las filas nuevas van a
-- entrar como 'reportado' o 'inferido', no 'confirmado', y el campo
-- existe justamente para que el módulo no mezcle ambos niveles al
-- calcular alertas.
-- ============================================================

CREATE TYPE tipo_enabler AS ENUM (
    'estudio_juridico',
    'auditora_consultora',
    'banco_entidad_financiera',
    'universidad_centro_academico',
    'medio_comunicacion',
    'escribania_notarial',
    'ingenieria_consultora_tecnica',
    'otro'
);

CREATE TYPE nivel_confianza_enabler AS ENUM (
    'confirmado',      -- fuente pública directa (BORA, expediente judicial, registro societario)
    'reportado',        -- prensa/informe de tercero, sin documento primario
    'inferido',          -- coincidencia sectorial/temporal, sin vínculo declarado
    'descartado'         -- se investigó y no se encontró vínculo (se deja registrado para no reinvestigar)
);

CREATE TABLE enablers_ecosistema (
    id                  SERIAL PRIMARY KEY,
    nombre              TEXT NOT NULL,              -- ej. 'Marval O'Farrell Mairal'
    tipo                tipo_enabler NOT NULL,
    personas_clave      TEXT,                        -- nombres de socios/profesionales relevantes, si son públicos
    descripcion_rol     TEXT NOT NULL,               -- qué hace: asesoría legal, auditoría de estados contables, etc.
    nivel_confianza     nivel_confianza_enabler NOT NULL,
    fuente_verificacion TEXT,                        -- URL o cita del documento/nota que sostiene el vínculo
    notas               TEXT,
    fecha_registro      DATE NOT NULL DEFAULT CURRENT_DATE
);

-- Cruce N:N entre enablers y vectores/empresas del padrón (una firma puede
-- asesorar a más de un actor, y un actor puede tener más de un enabler)
CREATE TABLE enabler_vector (
    enabler_id      INTEGER NOT NULL REFERENCES enablers_ecosistema(id) ON DELETE CASCADE,
    vector_id       INTEGER REFERENCES vectores_influencia_extranjera(id) ON DELETE CASCADE,
    padron_cuit     TEXT,      -- alternativa a vector_id: referencia directa a padron_soes_extranjeras.json por CUIT
    rol_especifico  TEXT,      -- ej. 'asesoró la presentación RIGI', 'representó en litigio X'
    PRIMARY KEY (enabler_id, vector_id, padron_cuit)
);

-- También registra funcionarios con paso por el sector privado relevante,
-- aunque el vínculo con un actor del padrón no esté confirmado (caso
-- Lucero: sí hay excusación formal, pero con mineras occidentales, no
-- con SOEs chinas/rusas -- se registra igual porque el nodo institucional
-- es el mismo que decide sobre litio chino).
CREATE TABLE funcionario_antecedente_privado (
    id                      SERIAL PRIMARY KEY,
    funcionario             TEXT NOT NULL,
    cargo_publico           TEXT NOT NULL,           -- ej. 'Secretario de Minería'
    entidad_privada_previa  TEXT,                     -- ej. 'Marval O'Farrell Mairal'
    clientes_relevantes     TEXT,                     -- lista de clientes conocidos del período privado
    nodo_decisorio          TEXT NOT NULL,            -- ej. 'Comité Evaluador RIGI'
    vinculo_con_padron_soes BOOLEAN NOT NULL DEFAULT FALSE,  -- true solo si hay vínculo verificado con actor China/Rusia
    excusacion_formal       BOOLEAN NOT NULL DEFAULT FALSE,
    excusacion_efectiva     BOOLEAN,                  -- NULL = en disputa/sin determinar
    fuente_verificacion     TEXT,
    notas                   TEXT
);

CREATE INDEX idx_enablers_tipo ON enablers_ecosistema(tipo);
CREATE INDEX idx_enablers_confianza ON enablers_ecosistema(nivel_confianza);
