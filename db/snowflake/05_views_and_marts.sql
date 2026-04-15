-- =============================================================================
-- FILE: db/snowflake/05_views_and_marts.sql
-- Layer: Target DB — analytical views and pre-aggregated mart tables
-- Connects to: MARTS.FACT_PRICES, FACT_FEATURES, FACT_BENCHMARKS, DIM_*
--              Flask analytics routes (read), FastAPI query layer (read)
-- Goal: Pre-join and pre-aggregate common query patterns so application code
--       runs fast without complex SQL.
-- Run order: 5th — after 04_rls.sql
--
-- FIXES APPLIED:
--   - All table references fully qualified as CMIA_DW.*.*
--   - REFRESHED_AT default changed to SYSDATE()::TIMESTAMP_NTZ
--   - USE ROLE ACCOUNTADMIN (CMIA_ADMIN lacks warehouse on fresh session)
-- =============================================================================

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE CMIA_ETL_WH;
USE DATABASE CMIA_DW;
USE SCHEMA MARTS;


-- =============================================================================
-- V_PRICES_ENRICHED
-- Daily prices with full dimensional context — main read view for the API.
-- =============================================================================
CREATE OR REPLACE VIEW CMIA_DW.MARTS.V_PRICES_ENRICHED AS
SELECT
    p.PRICE_DATE,
    p.SYMBOL_CODE,
    sym.COMPANY_NAME,
    sec.SECTOR_NAME,
    sec.SECTOR_CODE,
    sym.INDUSTRY,
    p.OPEN_PRICE,
    p.HIGH_PRICE,
    p.LOW_PRICE,
    p.CLOSE_PRICE,
    p.VOLUME_QTY,
    p.INTRADAY_RANGE_PCT,
    d.YEAR_NUM,
    d.QUARTER_NUM,
    d.MONTH_NAME,
    d.IS_MONTH_END,
    d.IS_QUARTER_END
FROM   CMIA_DW.MARTS.FACT_PRICES     p
JOIN   CMIA_DW.MARTS.DIM_SYMBOL      sym ON p.SYMBOL_KEY  = sym.SYMBOL_KEY
JOIN   CMIA_DW.MARTS.DIM_SECTOR      sec ON sym.SECTOR_KEY = sec.SECTOR_KEY
JOIN   CMIA_DW.MARTS.DIM_DATE        d   ON p.DATE_KEY    = d.DATE_KEY
WHERE  p.IS_ACTIVE = TRUE;


-- =============================================================================
-- V_LATEST_FEATURES
-- Most recent feature row per symbol — used for ML inference.
-- QUALIFY + ROW_NUMBER: Snowflake's idiomatic way to get latest-per-group.
-- =============================================================================
CREATE OR REPLACE VIEW CMIA_DW.MARTS.V_LATEST_FEATURES AS
SELECT
    f.SYMBOL_CODE,
    sym.COMPANY_NAME,
    sec.SECTOR_NAME,
    f.PRICE_DATE,
    f.DAILY_RETURN,
    f.MA_5, f.MA_20, f.MA_50,
    f.RSI_14,
    f.MACD, f.MACD_SIGNAL,
    f.VOLATILITY_20D,
    f.BB_UPPER, f.BB_LOWER, f.BB_POSITION,
    f.TARGET_NEXT_DAY_UP
FROM   CMIA_DW.MARTS.FACT_FEATURES   f
JOIN   CMIA_DW.MARTS.DIM_SYMBOL      sym ON f.SYMBOL_KEY  = sym.SYMBOL_KEY
JOIN   CMIA_DW.MARTS.DIM_SECTOR      sec ON sym.SECTOR_KEY = sec.SECTOR_KEY
WHERE  f.IS_ACTIVE = TRUE
QUALIFY ROW_NUMBER() OVER (PARTITION BY f.SYMBOL_KEY ORDER BY f.PRICE_DATE DESC) = 1;


-- =============================================================================
-- V_SECTOR_DAILY_SUMMARY
-- Daily sector-level aggregates.
-- CLOSE_CHECKSUM used for migration validation — must match Azure SQL view.
-- =============================================================================
CREATE OR REPLACE VIEW CMIA_DW.MARTS.V_SECTOR_DAILY_SUMMARY AS
SELECT
    p.PRICE_DATE,
    sec.SECTOR_NAME,
    sec.SECTOR_CODE,
    COUNT(DISTINCT p.SYMBOL_KEY)    AS SYMBOL_COUNT,
    AVG(p.CLOSE_PRICE)              AS AVG_CLOSE,
    SUM(p.VOLUME_QTY)               AS TOTAL_VOLUME,
    MIN(p.CLOSE_PRICE)              AS MIN_CLOSE,
    MAX(p.CLOSE_PRICE)              AS MAX_CLOSE,
    SUM(p.CLOSE_PRICE)              AS CLOSE_CHECKSUM   -- validation: must match Azure SQL
FROM   CMIA_DW.MARTS.FACT_PRICES     p
JOIN   CMIA_DW.MARTS.DIM_SYMBOL      sym ON p.SYMBOL_KEY  = sym.SYMBOL_KEY
JOIN   CMIA_DW.MARTS.DIM_SECTOR      sec ON sym.SECTOR_KEY = sec.SECTOR_KEY
WHERE  p.IS_ACTIVE = TRUE
GROUP BY p.PRICE_DATE, sec.SECTOR_NAME, sec.SECTOR_CODE;


-- =============================================================================
-- MART_ROLLING_RETURNS (pre-aggregated table, not a view)
-- Pre-computes 5/20/60-day returns per symbol per date.
-- Stored as table — query time is O(1) scan, not O(N) recompute.
-- =============================================================================
CREATE OR REPLACE TABLE CMIA_DW.MARTS.MART_ROLLING_RETURNS (
    SYMBOL_KEY      NUMBER(10,0)    NOT NULL,
    DATE_KEY        NUMBER(8,0)     NOT NULL,
    SYMBOL_CODE     VARCHAR(10)     NOT NULL,
    PRICE_DATE      DATE            NOT NULL,
    CLOSE_PRICE     NUMBER(12,4)    NOT NULL,
    RETURN_5D       NUMBER(10,6)    NULL,
    RETURN_20D      NUMBER(10,6)    NULL,
    RETURN_60D      NUMBER(10,6)    NULL,
    RETURN_YTD      NUMBER(10,6)    NULL,
    REFRESHED_AT    TIMESTAMP_NTZ   DEFAULT SYSDATE()::TIMESTAMP_NTZ,
    PRIMARY KEY (SYMBOL_KEY, DATE_KEY)
)
CLUSTER BY (DATE_KEY)
COMMENT = 'Pre-computed rolling returns — refreshed by ETL task after market close.';


-- =============================================================================
-- Snowflake Task: auto-refresh MART_ROLLING_RETURNS daily after market close
-- Runs weekdays 8pm UTC (~4pm EST + buffer). Starts SUSPENDED.
-- Resume with: ALTER TASK CMIA_DW.AUDIT.TASK_REFRESH_ROLLING_RETURNS RESUME;
-- =============================================================================
CREATE OR REPLACE TASK CMIA_DW.AUDIT.TASK_REFRESH_ROLLING_RETURNS
    WAREHOUSE = CMIA_ETL_WH
    SCHEDULE  = 'USING CRON 0 20 * * MON-FRI UTC'
    COMMENT   = 'Refresh MART_ROLLING_RETURNS after market close'
AS
INSERT OVERWRITE INTO CMIA_DW.MARTS.MART_ROLLING_RETURNS
SELECT
    p.SYMBOL_KEY,
    p.DATE_KEY,
    p.SYMBOL_CODE,
    p.PRICE_DATE,
    p.CLOSE_PRICE,
    (p.CLOSE_PRICE - LAG(p.CLOSE_PRICE, 5)  OVER (PARTITION BY p.SYMBOL_KEY ORDER BY p.PRICE_DATE))
        / NULLIF(LAG(p.CLOSE_PRICE, 5)  OVER (PARTITION BY p.SYMBOL_KEY ORDER BY p.PRICE_DATE), 0) AS RETURN_5D,
    (p.CLOSE_PRICE - LAG(p.CLOSE_PRICE, 20) OVER (PARTITION BY p.SYMBOL_KEY ORDER BY p.PRICE_DATE))
        / NULLIF(LAG(p.CLOSE_PRICE, 20) OVER (PARTITION BY p.SYMBOL_KEY ORDER BY p.PRICE_DATE), 0) AS RETURN_20D,
    (p.CLOSE_PRICE - LAG(p.CLOSE_PRICE, 60) OVER (PARTITION BY p.SYMBOL_KEY ORDER BY p.PRICE_DATE))
        / NULLIF(LAG(p.CLOSE_PRICE, 60) OVER (PARTITION BY p.SYMBOL_KEY ORDER BY p.PRICE_DATE), 0) AS RETURN_60D,
    (p.CLOSE_PRICE - FIRST_VALUE(p.CLOSE_PRICE) OVER (
        PARTITION BY p.SYMBOL_KEY, d.YEAR_NUM ORDER BY p.PRICE_DATE
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING))
        / NULLIF(FIRST_VALUE(p.CLOSE_PRICE) OVER (
        PARTITION BY p.SYMBOL_KEY, d.YEAR_NUM ORDER BY p.PRICE_DATE
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING), 0) AS RETURN_YTD,
    SYSDATE()::TIMESTAMP_NTZ AS REFRESHED_AT
FROM CMIA_DW.MARTS.FACT_PRICES  p
JOIN CMIA_DW.MARTS.DIM_DATE     d ON p.DATE_KEY = d.DATE_KEY
WHERE p.IS_ACTIVE = TRUE;
