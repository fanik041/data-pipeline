-- =============================================================================
-- FILE: db/snowflake/02_dimensions.sql
-- Layer: Target DB — Snowflake dimension tables (star schema)
-- Connects to: 01_setup.sql (schemas must exist), 03_facts.sql (FK references)
-- Goal: Define slowly-changing dimension tables — symbols, dates, sectors.
--       Fact tables (prices, features) join to these.
-- Run order: 2nd — after 01_setup.sql
--
-- INTERVIEW POINT: "In the source Azure SQL we had normalised tables with
--   FK joins at query time. In Snowflake we pre-materialise these as dimension
--   tables and denormalise into facts — eliminates expensive joins on billions
--   of rows. That's the OLTP→OLAP schema transformation."
--
-- FIXES APPLIED:
--   - All table references fully qualified as CMIA_DW.MARTS.*
--   - USE ROLE ACCOUNTADMIN (CMIA_ADMIN lacks warehouse grant on first run)
--   - Removed ambiguous USE statements before INSERT
-- =============================================================================

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE CMIA_ETL_WH;
USE DATABASE CMIA_DW;
USE SCHEMA MARTS;


-- =============================================================================
-- DIM_SECTOR — market sectors (Technology, Financial Services, etc.)
-- =============================================================================
CREATE OR REPLACE TABLE CMIA_DW.MARTS.DIM_SECTOR (
    SECTOR_KEY      NUMBER(10,0)  NOT NULL AUTOINCREMENT PRIMARY KEY,
    SECTOR_ID_SRC   NUMBER(10,0)  NOT NULL,  -- matches sector_id in Azure SQL
    SECTOR_NAME     VARCHAR(100)  NOT NULL,
    SECTOR_CODE     VARCHAR(10)   NOT NULL,
    IS_ACTIVE       BOOLEAN       DEFAULT TRUE,
    CREATED_AT      TIMESTAMP_NTZ DEFAULT CONVERT_TIMEZONE('UTC', CURRENT_TIMESTAMP()),
    UPDATED_AT      TIMESTAMP_NTZ DEFAULT CONVERT_TIMEZONE('UTC', CURRENT_TIMESTAMP()),
    SOURCE_SYSTEM   VARCHAR(50)   DEFAULT 'azure_sql',
    UNIQUE (SECTOR_NAME),
    UNIQUE (SECTOR_CODE)
)
COMMENT = 'Market sector dimension — Technology, Financial Services, etc.';


-- =============================================================================
-- DIM_SYMBOL — one row per equity ticker
-- VARIANT column allows flexible JSON metadata without schema changes
-- =============================================================================
CREATE OR REPLACE TABLE CMIA_DW.MARTS.DIM_SYMBOL (
    SYMBOL_KEY       NUMBER(10,0)  NOT NULL AUTOINCREMENT PRIMARY KEY,
    SYMBOL_ID_SRC    NUMBER(10,0)  NOT NULL,  -- source PK from Azure SQL
    SYMBOL_CODE      VARCHAR(10)   NOT NULL,
    COMPANY_NAME     VARCHAR(255)  NOT NULL,
    SECTOR_KEY       NUMBER(10,0)  NOT NULL,  -- FK → DIM_SECTOR
    INDUSTRY         VARCHAR(255)  NOT NULL,
    MARKET_CAP_USD   NUMBER(20,0)  NULL,
    CURRENCY         VARCHAR(3)    DEFAULT 'USD',
    EXCHANGE         VARCHAR(20)   NOT NULL,
    COUNTRY          VARCHAR(100)  NOT NULL,
    IS_BENCHMARK     BOOLEAN       DEFAULT FALSE,
    METADATA_DATE    DATE          NOT NULL,
    EXTRA_ATTRIBUTES VARIANT       NULL,      -- flexible JSON for future fields
    IS_ACTIVE        BOOLEAN       DEFAULT TRUE,
    CREATED_AT       TIMESTAMP_NTZ DEFAULT CONVERT_TIMEZONE('UTC', CURRENT_TIMESTAMP()),
    UPDATED_AT       TIMESTAMP_NTZ DEFAULT CONVERT_TIMEZONE('UTC', CURRENT_TIMESTAMP()),
    SOURCE_SYSTEM    VARCHAR(50)   DEFAULT 'azure_sql',
    UNIQUE (SYMBOL_CODE),
    FOREIGN KEY (SECTOR_KEY) REFERENCES CMIA_DW.MARTS.DIM_SECTOR(SECTOR_KEY)
)
COMMENT = 'Symbol/ticker dimension — one row per equity. Includes VARIANT for flexible metadata.';


-- =============================================================================
-- DIM_DATE — exploded calendar dimension, one row per day 2021–2027
-- Pre-computed attributes eliminate date functions at query time.
-- Populated via GENERATOR — no ETL needed, it's static.
-- =============================================================================
CREATE OR REPLACE TABLE CMIA_DW.MARTS.DIM_DATE (
    DATE_KEY         NUMBER(8,0)  NOT NULL PRIMARY KEY,  -- YYYYMMDD integer — fast join
    FULL_DATE        DATE         NOT NULL,
    YEAR_NUM         NUMBER(4,0)  NOT NULL,
    QUARTER_NUM      NUMBER(1,0)  NOT NULL,
    MONTH_NUM        NUMBER(2,0)  NOT NULL,
    MONTH_NAME       VARCHAR(10)  NOT NULL,
    WEEK_NUM         NUMBER(2,0)  NOT NULL,
    DAY_OF_WEEK_NUM  NUMBER(1,0)  NOT NULL,
    DAY_OF_WEEK_NAME VARCHAR(10)  NOT NULL,
    DAY_OF_MONTH     NUMBER(2,0)  NOT NULL,
    IS_WEEKEND       BOOLEAN      NOT NULL,
    IS_TRADING_DAY   BOOLEAN      DEFAULT NULL,  -- updated by ingest script
    IS_MONTH_END     BOOLEAN      NOT NULL,
    IS_QUARTER_END   BOOLEAN      NOT NULL,
    IS_YEAR_END      BOOLEAN      NOT NULL,
    FISCAL_YEAR      NUMBER(4,0)  NULL,
    UNIQUE (FULL_DATE)
)
COMMENT = 'Calendar dimension — pre-computed date attributes. No ETL needed.';

-- Populate DIM_DATE using GENERATOR — creates 2557 rows (7 years) without loops
INSERT INTO CMIA_DW.MARTS.DIM_DATE
SELECT
    TO_NUMBER(TO_CHAR(dt, 'YYYYMMDD'))        AS DATE_KEY,
    dt                                         AS FULL_DATE,
    YEAR(dt)                                   AS YEAR_NUM,
    QUARTER(dt)                                AS QUARTER_NUM,
    MONTH(dt)                                  AS MONTH_NUM,
    MONTHNAME(dt)                              AS MONTH_NAME,
    WEEKOFYEAR(dt)                             AS WEEK_NUM,
    DAYOFWEEK(dt)                              AS DAY_OF_WEEK_NUM,
    DAYNAME(dt)                                AS DAY_OF_WEEK_NAME,
    DAY(dt)                                    AS DAY_OF_MONTH,
    DAYOFWEEK(dt) IN (0, 6)                    AS IS_WEEKEND,
    NULL                                       AS IS_TRADING_DAY,
    dt = LAST_DAY(dt, 'month')                 AS IS_MONTH_END,
    dt = LAST_DAY(dt, 'quarter')               AS IS_QUARTER_END,
    MONTH(dt) = 12 AND DAY(dt) = 31           AS IS_YEAR_END,
    NULL                                       AS FISCAL_YEAR
FROM (
    SELECT DATEADD('day', SEQ4(), '2021-01-01'::DATE) AS dt
    FROM TABLE(GENERATOR(ROWCOUNT => 2557))
)
WHERE dt <= '2027-12-31';
