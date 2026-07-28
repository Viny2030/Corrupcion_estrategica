-- ============================================================
-- MÓDULO: Vectores de Influencia Estatal Extranjera
-- Tabla madre transversal a los 10 monitores del ecosistema
-- (Mapa_Transparencia + 9 satélites). Alimenta la dimensión
-- R_Internacional del IRI vía /api/alertas?plataforma=iri
-- ============================================================

CREATE TYPE capa_mecanismo AS ENUM (
    'capa_1_directo',       -- soborno político, licitaciones alteradas, revolving doors
    'capa_2_habilitante'    -- infraestructura concentrada, deuda opaca, soft power
);

CREATE TYPE tipo_vinculo_externo AS ENUM (
    'exogeno_directo',      -- instrucción/financiamiento directo del estado origen
    'proxy_hibrido',        -- redes corporativas/oligarcas/fundaciones en terceros países
    'endogeno_alineado',    -- élites locales que alinean decisiones sin orden explícita
    'mimetico',             -- copia local de marcos regulatorios importados
    'sin_vinculo'
);

CREATE TYPE clasificacion_final AS ENUM (
    'confirmado',                  -- Confirmed Strategic Corruption
    'entorno_dependencia_fuerte',  -- Strategic Corruption Environment / Strong Dependency Case
    'zona_gris',                   -- Grey-Zone Strategic Influence
    'fuera_de_alcance'             -- Ordinary/Domestic Corruption o sin dimensión geopolítica
);

CREATE TYPE nivel_alerta AS ENUM ('CRITICO', 'ALTO', 'MEDIO', 'BAJO', 'VIGILAR');

-- ------------------------------------------------------------
-- Tabla madre
-- ------------------------------------------------------------
CREATE TABLE vectores_influencia_extranjera (
    id                      SERIAL PRIMARY KEY,
    slug                    TEXT UNIQUE NOT NULL,          -- ej. 'atucha-iii-cnnc'
    sector                  TEXT NOT NULL,                 -- nuclear, litio, espacio, telecom, financiero, academico, defensa, puertos, medios
    actor_extranjero        TEXT NOT NULL,                 -- CNNC, Zijin, Ganfeng, CLTC, Emposat, Huawei, PBOC, Hanban...
    pais_origen             TEXT NOT NULL,                 -- China, Rusia, EEUU, etc.
    contraparte_argentina   TEXT,                          -- NA-SA, provincia, universidad, organismo
    mecanismo               TEXT NOT NULL,                 -- descripción corta del mecanismo
    regimen_legal           TEXT,                          -- RIGI1, SuperRIGI, tratado bilateral, decreto, ninguno
    capa                    capa_mecanismo NOT NULL,

    -- ---- Classification test NEST (4 elementos) ----
    -- Escala 0-3: 0=sin evidencia, 1=indicio, 2=moderado, 3=fuerte/confirmado
    score_induccion         SMALLINT NOT NULL CHECK (score_induccion BETWEEN 0 AND 3),
    score_abuso_autoridad   SMALLINT NOT NULL CHECK (score_abuso_autoridad BETWEEN 0 AND 3),
    score_efecto_estrategico SMALLINT NOT NULL CHECK (score_efecto_estrategico BETWEEN 0 AND 3),
    vinculo_externo         tipo_vinculo_externo NOT NULL,
    score_vinculo_externo   SMALLINT GENERATED ALWAYS AS (
        CASE vinculo_externo
            WHEN 'exogeno_directo' THEN 3
            WHEN 'proxy_hibrido' THEN 2
            WHEN 'endogeno_alineado' THEN 1
            WHEN 'mimetico' THEN 1
            ELSE 0
        END
    ) STORED,

    clasificacion           clasificacion_final NOT NULL,  -- calculada por scoring_engine.py, persistida
    nivel_alerta            nivel_alerta NOT NULL,

    activo                  BOOLEAN NOT NULL DEFAULT TRUE,
    fecha_deteccion         DATE NOT NULL,
    fecha_actualizacion     TIMESTAMPTZ NOT NULL DEFAULT now(),
    notas                   TEXT
);

-- ------------------------------------------------------------
-- Evidencia / fuentes por vector (N:1)
-- ------------------------------------------------------------
CREATE TABLE vector_evidencia (
    id              SERIAL PRIMARY KEY,
    vector_id       INTEGER NOT NULL REFERENCES vectores_influencia_extranjera(id) ON DELETE CASCADE,
    tipo_fuente     TEXT NOT NULL,      -- oficial_ar, oficial_intl, prensa, informe_congreso_eeuu, ocde, occrp
    titulo          TEXT NOT NULL,
    url             TEXT NOT NULL,
    fecha_publicacion DATE,
    fecha_registro  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------
-- Historial de novedades semanales (alimentado por scheduled task)
-- ------------------------------------------------------------
CREATE TABLE vector_actualizaciones (
    id                  SERIAL PRIMARY KEY,
    vector_id           INTEGER REFERENCES vectores_influencia_extranjera(id) ON DELETE CASCADE,
    -- NULL si es un vector nuevo detectado, aún no confirmado en tabla madre
    es_vector_nuevo      BOOLEAN NOT NULL DEFAULT FALSE,
    resumen             TEXT NOT NULL,
    cambio_clasificacion BOOLEAN NOT NULL DEFAULT FALSE,
    clasificacion_previa clasificacion_final,
    clasificacion_nueva  clasificacion_final,
    fuentes_json         JSONB,          -- [{titulo, url}]
    fecha_corrida        DATE NOT NULL DEFAULT CURRENT_DATE
);

-- ------------------------------------------------------------
-- Cruce con monitores existentes (trazabilidad de qué monitor
-- aportó el dato: Legislativo, Contratos, MEACI, DDJJ, etc.)
-- ------------------------------------------------------------
CREATE TABLE vector_monitor_origen (
    vector_id       INTEGER NOT NULL REFERENCES vectores_influencia_extranjera(id) ON DELETE CASCADE,
    monitor         TEXT NOT NULL,      -- 'monitor_legislativo', 'monitor_contratos', 'meaci', 'monitor_ddjj', 'monitor_ejecutivo', 'iri'
    referencia_id   TEXT,               -- id/CUIT/expediente en el monitor de origen
    PRIMARY KEY (vector_id, monitor, referencia_id)
);

CREATE INDEX idx_vectores_sector ON vectores_influencia_extranjera(sector);
CREATE INDEX idx_vectores_clasificacion ON vectores_influencia_extranjera(clasificacion);
CREATE INDEX idx_vectores_alerta ON vectores_influencia_extranjera(nivel_alerta);
CREATE INDEX idx_actualizaciones_fecha ON vector_actualizaciones(fecha_corrida);
