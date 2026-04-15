-- =============================================================================
-- FILE: db/snowflake/04_rls.sql
-- Layer: Target DB — Access control table + object-level grants
-- Connects to: ACCESS_CONTROL schema, MARTS fact and dimension tables
-- Goal: Enforce sector-based access control and grant object-level permissions.
-- Run order: 4th — after 03_facts.sql
--
-- INTERVIEW POINT: "Row Access Policies and Column Masking Policies are
--   Enterprise-only features in Snowflake. On Standard edition, sector-based
--   filtering is enforced at the application layer — the FastAPI service checks
--   USER_SECTOR_ACCESS before issuing queries. This is equivalent to what the
--   Azure SQL inline TVF predicate does, just enforced one layer up."
--
-- FIXES APPLIED:
--   - Removed ROW ACCESS POLICY (Enterprise only — not supported on Standard)
--   - Removed MASKING POLICY (Enterprise only)
--   - All GRANTs split to one role per line
--   - TIMESTAMP default changed to SYSDATE()::TIMESTAMP_NTZ
--   - All table references fully qualified as CMIA_DW.*.*
-- =============================================================================

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE CMIA_ETL_WH;
USE DATABASE CMIA_DW;


-- =============================================================================
-- Access control table
-- Maps Snowflake user → sector(s) they can see.
-- Mirrors rls.user_sector_access in Azure SQL.
-- Application layer reads this table to enforce row-level filtering.
-- =============================================================================
CREATE OR REPLACE TABLE CMIA_DW.ACCESS_CONTROL.USER_SECTOR_ACCESS (
    ACCESS_ID       NUMBER(10,0)    NOT NULL AUTOINCREMENT PRIMARY KEY,
    LOGIN_NAME      VARCHAR(128)    NOT NULL,   -- CURRENT_USER() value
    SECTOR_CODE     VARCHAR(10)     NOT NULL,   -- matches DIM_SECTOR.SECTOR_CODE
    GRANTED_BY      VARCHAR(128)    NOT NULL,
    GRANTED_AT      TIMESTAMP_NTZ   DEFAULT SYSDATE()::TIMESTAMP_NTZ,
    REVOKED_AT      TIMESTAMP_NTZ   NULL,
    IS_ACTIVE       BOOLEAN         DEFAULT TRUE,
    UNIQUE (LOGIN_NAME, SECTOR_CODE)
)
COMMENT = 'User→sector access grants. Read by FastAPI to enforce row-level filtering.';

-- Seed demo access grants
INSERT INTO CMIA_DW.ACCESS_CONTROL.USER_SECTOR_ACCESS (LOGIN_NAME, SECTOR_CODE, GRANTED_BY) VALUES
('TECH_ANALYST',  'TECH',  'CMIA_ADMIN'),
('TECH_ANALYST',  'COMM',  'CMIA_ADMIN'),
('FIN_ANALYST',   'FIN',   'CMIA_ADMIN'),
('FULL_ANALYST',  'TECH',  'CMIA_ADMIN'),
('FULL_ANALYST',  'FIN',   'CMIA_ADMIN'),
('FULL_ANALYST',  'COMM',  'CMIA_ADMIN'),
('FULL_ANALYST',  'CONS',  'CMIA_ADMIN');


-- =============================================================================
-- Object-level grants — defence in depth
-- =============================================================================

GRANT SELECT ON TABLE CMIA_DW.MARTS.FACT_PRICES     TO ROLE CMIA_ANALYST;
GRANT SELECT ON TABLE CMIA_DW.MARTS.FACT_PRICES     TO ROLE CMIA_API;
GRANT SELECT ON TABLE CMIA_DW.MARTS.FACT_FEATURES   TO ROLE CMIA_ANALYST;
GRANT SELECT ON TABLE CMIA_DW.MARTS.FACT_FEATURES   TO ROLE CMIA_API;
GRANT SELECT ON TABLE CMIA_DW.MARTS.FACT_BENCHMARKS TO ROLE CMIA_ANALYST;
GRANT SELECT ON TABLE CMIA_DW.MARTS.FACT_BENCHMARKS TO ROLE CMIA_API;
GRANT SELECT ON TABLE CMIA_DW.MARTS.DIM_SYMBOL      TO ROLE CMIA_ANALYST;
GRANT SELECT ON TABLE CMIA_DW.MARTS.DIM_SYMBOL      TO ROLE CMIA_API;
GRANT SELECT ON TABLE CMIA_DW.MARTS.DIM_SECTOR      TO ROLE CMIA_ANALYST;
GRANT SELECT ON TABLE CMIA_DW.MARTS.DIM_SECTOR      TO ROLE CMIA_API;
GRANT SELECT ON TABLE CMIA_DW.MARTS.DIM_DATE        TO ROLE CMIA_ANALYST;
GRANT SELECT ON TABLE CMIA_DW.MARTS.DIM_DATE        TO ROLE CMIA_API;

GRANT SELECT, INSERT, UPDATE ON TABLE CMIA_DW.RAW.RAW_PRICES_LANDING            TO ROLE CMIA_ETL;
GRANT SELECT, INSERT, UPDATE ON TABLE CMIA_DW.AUDIT.ETL_LOG                     TO ROLE CMIA_ETL;
GRANT SELECT, INSERT, UPDATE ON TABLE CMIA_DW.ACCESS_CONTROL.USER_SECTOR_ACCESS TO ROLE CMIA_ADMIN;
