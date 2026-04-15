-- =============================================================================
-- FILE: db/snowflake/03_facts.sql
-- Layer: Target DB — Snowflake fact tables (star schema core)
-- Connects to: 02_dimensions.sql (dims must exist), migration scripts (write),
--              Flask ETL service (read/write), FastAPI query layer (read)
-- Goal: Define the large fact tables that hold all price and feature data.
--       Clustered by DATE_KEY + SYMBOL_KEY — the two columns used in 95% of filters.
--       ETL_LOG here tracks Snowflake-side pipeline runs (separate from Azure SQL audit).
-- Run order: 3rd — after 02_dimensions.sql
-- =============================================================================

USE ROLE CMIA_ADMIN;
USE WAREHOUSE CMIA_ETL_WH;
USE DATABASE CMIA_DW;
USE SCHEMA MARTS;


-- =============================================================================
-- FACT_PRICES
-- One row per symbol per trading day. Core analytical table.
-- Denormalised: includes symbol_code, sector_code directly — avoids join on hot path.
-- Migrated FROM: market.daily_prices + ref.symbols (Azure SQL)
--
-- INTERVIEW POINT: "We denormalise symbol_code and sector_code directly into the
--   fact table. In Snowflake this is deliberate — columnar storage compresses
--   repeated strings efficiently, so redundancy costs almost nothing but saves
--   a join on 15,000+ rows per query."
-- =============================================================================
CREATE OR REPLACE TABLE MARTS.FACT_PRICES (
    PRICE_SK            NUMBER(20,0)    NOT NULL AUTOINCREMENT PRIMARY KEY,
    -- Dimension keys (for star schema joins)
    SYMBOL_KEY          NUMBER(10,0)    NOT NULL,
    DATE_KEY            NUMBER(8,0)     NOT NULL,  -- YYYYMMDD — fast integer join to DIM_DATE
    -- Denormalised lookups (avoid join for common filters)
    SYMBOL_CODE         VARCHAR(10)     NOT NULL,
    SECTOR_CODE         VARCHAR(10)     NOT NULL,
    -- Price data
    PRICE_DATE          DATE            NOT NULL,
    OPEN_PRICE          NUMBER(12,4)    NOT NULL,
    HIGH_PRICE          NUMBER(12,4)    NOT NULL,
    LOW_PRICE           NUMBER(12,4)    NOT NULL,
    CLOSE_PRICE         NUMBER(12,4)    NOT NULL,
    VOLUME_QTY          NUMBER(20,0)    NOT NULL,
    -- Derived column: intraday range % — pre-computed to avoid repeated CASE WHEN
    INTRADAY_RANGE_PCT  NUMBER(8,4)     NULL,
    -- Audit / lineage
    SOURCE_SYSTEM       VARCHAR(50)     DEFAULT 'azure_sql',
    BATCH_ID            VARCHAR(50)     NULL,
    LOADED_AT           TIMESTAMP_NTZ   DEFAULT CONVERT_TIMEZONE('UTC', CURRENT_TIMESTAMP()),
    IS_ACTIVE           BOOLEAN         DEFAULT TRUE,

    FOREIGN KEY (SYMBOL_KEY) REFERENCES MARTS.DIM_SYMBOL(SYMBOL_KEY),
    FOREIGN KEY (DATE_KEY)   REFERENCES MARTS.DIM_DATE(DATE_KEY)
)
-- CLUSTER BY: Snowflake micro-partition pruning — filters on date + symbol skip unneeded partitions
-- This is the most important performance decision on a fact table
CLUSTER BY (DATE_KEY, SYMBOL_KEY)
DATA_RETENTION_TIME_IN_DAYS = 1      -- TIME_TRAVEL: rollback up to 7 days
COMMENT = 'Daily OHLCV fact table — 15,040 rows at initial load, ~20 new rows/trading day';


-- =============================================================================
-- FACT_FEATURES
-- Technical indicator features per symbol per day.
-- Same grain as FACT_PRICES (one row per symbol per day).
-- Kept separate from FACT_PRICES — different consumers (ML vs analytics).
-- =============================================================================
CREATE OR REPLACE TABLE MARTS.FACT_FEATURES (
    FEATURE_SK          NUMBER(20,0)    NOT NULL AUTOINCREMENT PRIMARY KEY,
    SYMBOL_KEY          NUMBER(10,0)    NOT NULL,
    DATE_KEY            NUMBER(8,0)     NOT NULL,
    SYMBOL_CODE         VARCHAR(10)     NOT NULL,
    PRICE_DATE          DATE            NOT NULL,

    -- Returns
    DAILY_RETURN        NUMBER(10,6)    NULL,      -- NULL for first row per symbol

    -- Moving averages
    MA_5                NUMBER(12,4)    NULL,
    MA_20               NUMBER(12,4)    NULL,
    MA_50               NUMBER(12,4)    NULL,

    -- Volatility + momentum
    VOLATILITY_20D      NUMBER(10,6)    NULL,
    RSI_14              NUMBER(6,2)     NULL,      -- 0–100 bounded

    -- MACD
    MACD                NUMBER(14,6)    NOT NULL,  -- EWM-based, never NULL
    MACD_SIGNAL         NUMBER(14,6)    NOT NULL,

    -- Bollinger Bands
    BB_UPPER            NUMBER(12,4)    NULL,
    BB_LOWER            NUMBER(12,4)    NULL,
    BB_POSITION         NUMBER(10,6)    NULL,      -- 0=at lower, 1=at upper

    -- ML label
    TARGET_NEXT_DAY_UP  NUMBER(1,0)     NOT NULL,  -- 0 or 1 (BOOLEAN not used — sklearn compat)

    -- Audit
    SOURCE_SYSTEM       VARCHAR(50)     DEFAULT 'azure_sql',
    BATCH_ID            VARCHAR(50)     NULL,
    LOADED_AT           TIMESTAMP_NTZ   DEFAULT CONVERT_TIMEZONE('UTC', CURRENT_TIMESTAMP()),
    IS_ACTIVE           BOOLEAN         DEFAULT TRUE,

    FOREIGN KEY (SYMBOL_KEY) REFERENCES MARTS.DIM_SYMBOL(SYMBOL_KEY),
    FOREIGN KEY (DATE_KEY)   REFERENCES MARTS.DIM_DATE(DATE_KEY)
)
CLUSTER BY (DATE_KEY, SYMBOL_KEY)
DATA_RETENTION_TIME_IN_DAYS = 1
COMMENT = 'Technical indicator features — used as ML predictor inputs';


-- =============================================================================
-- FACT_BENCHMARKS
-- Daily close for SPY, QQQ, IEF, GLD, TLT.
-- Joined to FACT_PRICES by date for market-context features in the predictor.
-- =============================================================================
CREATE OR REPLACE TABLE MARTS.FACT_BENCHMARKS (
    BENCHMARK_SK        NUMBER(20,0)    NOT NULL AUTOINCREMENT PRIMARY KEY,
    SYMBOL_KEY          NUMBER(10,0)    NOT NULL,
    DATE_KEY            NUMBER(8,0)     NOT NULL,
    SYMBOL_CODE         VARCHAR(10)     NOT NULL,
    PRICE_DATE          DATE            NOT NULL,
    CLOSE_PRICE         NUMBER(12,4)    NOT NULL,
    SOURCE_SYSTEM       VARCHAR(50)     DEFAULT 'yfinance',
    BATCH_ID            VARCHAR(50)     NULL,
    LOADED_AT           TIMESTAMP_NTZ   DEFAULT CONVERT_TIMEZONE('UTC', CURRENT_TIMESTAMP()),
    IS_ACTIVE           BOOLEAN         DEFAULT TRUE,

    FOREIGN KEY (SYMBOL_KEY) REFERENCES MARTS.DIM_SYMBOL(SYMBOL_KEY),
    FOREIGN KEY (DATE_KEY)   REFERENCES MARTS.DIM_DATE(DATE_KEY)
)
CLUSTER BY (DATE_KEY)
COMMENT = 'Market index benchmarks — SPY, QQQ, IEF, GLD, TLT daily close';


-- =============================================================================
-- RAW.RAW_PRICES_LANDING
-- Landing table: data arrives here first from Azure SQL migration, exactly
-- as extracted — no transformation. Validated and promoted to MARTS after checks.
-- Keeps raw data for reprocessing if transformation logic changes.
-- =============================================================================
CREATE OR REPLACE TABLE RAW.RAW_PRICES_LANDING (
    LANDING_ID          NUMBER(20,0)    NOT NULL AUTOINCREMENT PRIMARY KEY,
    SYMBOL_CODE         VARCHAR(10),
    PRICE_DATE          VARCHAR(20),    -- raw string — type coercion happens in STAGING
    OPEN_PRICE          FLOAT,
    HIGH_PRICE          FLOAT,
    LOW_PRICE           FLOAT,
    CLOSE_PRICE         FLOAT,
    VOLUME              FLOAT,          -- comes as NUMBER from pandas, store as FLOAT
    RAW_PAYLOAD         VARIANT,        -- full source row as JSON — for reprocessing
    SOURCE_SYSTEM       VARCHAR(50)     DEFAULT 'azure_sql',
    BATCH_ID            VARCHAR(50),
    LANDED_AT           TIMESTAMP_NTZ   DEFAULT CONVERT_TIMEZONE('UTC', CURRENT_TIMESTAMP()),
    IS_PROCESSED        BOOLEAN         DEFAULT FALSE  -- flipped to TRUE after STAGING load
)
DATA_RETENTION_TIME_IN_DAYS = 1
COMMENT = 'Raw landing zone — source data before transformation. Do not query directly.';


-- =============================================================================
-- AUDIT.ETL_LOG
-- Snowflake-side equivalent of audit.etl_log in Azure SQL.
-- Tracks every pipeline run: batch_id, row counts, status, duration.
-- =============================================================================
CREATE OR REPLACE TABLE AUDIT.ETL_LOG (
    LOG_ID              NUMBER(20,0)    NOT NULL AUTOINCREMENT PRIMARY KEY,
    BATCH_ID            VARCHAR(50)     NOT NULL,
    PIPELINE_NAME       VARCHAR(100)    NOT NULL,
    SOURCE_SYSTEM       VARCHAR(100)    NOT NULL,
    TARGET_TABLE        VARCHAR(100)    NOT NULL,
    ROWS_EXTRACTED      NUMBER(20,0)    NULL,
    ROWS_INSERTED       NUMBER(20,0)    NULL,
    ROWS_UPDATED        NUMBER(20,0)    NULL,
    ROWS_REJECTED       NUMBER(20,0)    DEFAULT 0,
    STATUS              VARCHAR(20)     NOT NULL,   -- 'RUNNING','SUCCESS','FAILED','PARTIAL'
    ERROR_MESSAGE       VARCHAR(4000)   NULL,
    STARTED_AT          TIMESTAMP_NTZ   NOT NULL DEFAULT CONVERT_TIMEZONE('UTC', CURRENT_TIMESTAMP()),
    COMPLETED_AT        TIMESTAMP_NTZ   NULL,
    DURATION_SECONDS    NUMBER(10,2)    NULL,        -- set by ETL script on completion

    CONSTRAINT ck_etl_status CHECK (STATUS IN ('RUNNING','SUCCESS','FAILED','PARTIAL'))
)
COMMENT = 'Pipeline audit log — one row per ETL run. Used for watermark tracking and debugging.';
