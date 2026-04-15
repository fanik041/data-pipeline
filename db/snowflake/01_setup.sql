-- =============================================================================
-- FILE: db/snowflake/01_setup.sql
-- Layer: Target DB — Snowflake OLAP warehouse setup
-- Connects to: Azure SQL (migration source), FastAPI service (reads)
-- Goal: Create the warehouse, database, schemas, and roles before any objects.
--       Snowflake separates compute (warehouse) from storage (database) —
--       this is the core architectural difference from Azure SQL / SQL Server.
-- Ref: docs/interview-prep/TRUTH_SOURCE.md — Snowflake as OTPP migration target
-- Run order: 1st — must run as ACCOUNTADMIN
--
-- INTERVIEW POINT: "Snowflake's separation of compute and storage means you
--   can scale queries independently of data size, and multiple workloads
--   (ETL, analytics, ML) can each have their own warehouse without contention."
--
-- FIXES APPLIED:
--   - DATA_RETENTION_TIME_IN_DAYS = 1 (Standard edition max)
--   - GRANT statements split to one role per line (Standard edition syntax)
--   - Removed GO keyword (T-SQL only, not valid in Snowflake)
-- =============================================================================

USE ROLE ACCOUNTADMIN;


-- =============================================================================
-- Warehouse — compute cluster (auto-suspend to avoid idle charges)
-- =============================================================================

CREATE WAREHOUSE IF NOT EXISTS CMIA_WH
    WAREHOUSE_SIZE   = 'X-SMALL'    -- cheapest tier; scale up for bulk loads
    AUTO_SUSPEND     = 60           -- suspend after 60s idle — cost control
    AUTO_RESUME      = TRUE
    INITIALLY_SUSPENDED = TRUE
    COMMENT          = 'Main CMIA warehouse — FastAPI queries + migration loads';

-- Separate warehouse for heavy ETL runs — keeps ETL from competing with API latency
CREATE WAREHOUSE IF NOT EXISTS CMIA_ETL_WH
    WAREHOUSE_SIZE   = 'SMALL'
    AUTO_SUSPEND     = 120
    AUTO_RESUME      = TRUE
    INITIALLY_SUSPENDED = TRUE
    COMMENT          = 'ETL-only warehouse — migration and batch loads';


-- =============================================================================
-- Database and schemas
-- =============================================================================
CREATE DATABASE IF NOT EXISTS CMIA_DW
    DATA_RETENTION_TIME_IN_DAYS = 1   -- Standard edition max is 1 day
    COMMENT = 'CMIA Data Warehouse — target for Azure SQL migration';

USE DATABASE CMIA_DW;

-- RAW      : landing zone — data as-it-arrived from source, no transformation
-- STAGING  : cleaned, typed, deduplicated — intermediate layer
-- MARTS    : denormalised star schema — what APIs and analysts query
-- ACCESS_CONTROL : RLS tables (row access policies, masking policies)
-- AUDIT    : ETL logs, pipeline metadata

CREATE SCHEMA IF NOT EXISTS RAW             DATA_RETENTION_TIME_IN_DAYS = 1;
CREATE SCHEMA IF NOT EXISTS STAGING         DATA_RETENTION_TIME_IN_DAYS = 1;
CREATE SCHEMA IF NOT EXISTS MARTS           DATA_RETENTION_TIME_IN_DAYS = 1;
CREATE SCHEMA IF NOT EXISTS ACCESS_CONTROL  DATA_RETENTION_TIME_IN_DAYS = 1;
CREATE SCHEMA IF NOT EXISTS AUDIT           DATA_RETENTION_TIME_IN_DAYS = 1;


-- =============================================================================
-- Roles — Snowflake RBAC (role-based access control)
-- =============================================================================

-- CMIA_ADMIN   : full access, bypasses row access policies
-- CMIA_ANALYST : read-only on MARTS, subject to row access policies
-- CMIA_ETL     : write access to RAW and STAGING, read on ref tables
-- CMIA_API     : read-only on MARTS — used by FastAPI service account

CREATE ROLE IF NOT EXISTS CMIA_ADMIN;
CREATE ROLE IF NOT EXISTS CMIA_ANALYST;
CREATE ROLE IF NOT EXISTS CMIA_ETL;
CREATE ROLE IF NOT EXISTS CMIA_API;

-- Role hierarchy
GRANT ROLE CMIA_ADMIN   TO ROLE SYSADMIN;
GRANT ROLE CMIA_ANALYST TO ROLE CMIA_ADMIN;
GRANT ROLE CMIA_API     TO ROLE CMIA_ADMIN;

-- Warehouse usage grants
GRANT USAGE ON WAREHOUSE CMIA_WH     TO ROLE CMIA_ANALYST;
GRANT USAGE ON WAREHOUSE CMIA_WH     TO ROLE CMIA_API;
GRANT USAGE ON WAREHOUSE CMIA_ETL_WH TO ROLE CMIA_ETL;
GRANT USAGE ON WAREHOUSE CMIA_ETL_WH TO ROLE CMIA_ADMIN;

-- Database grants — one role per line (Standard edition requirement)
GRANT USAGE ON DATABASE CMIA_DW TO ROLE CMIA_ANALYST;
GRANT USAGE ON DATABASE CMIA_DW TO ROLE CMIA_ETL;
GRANT USAGE ON DATABASE CMIA_DW TO ROLE CMIA_API;
GRANT USAGE ON DATABASE CMIA_DW TO ROLE CMIA_ADMIN;

-- Schema grants for ETL role
GRANT USAGE      ON SCHEMA CMIA_DW.RAW     TO ROLE CMIA_ETL;
GRANT CREATE TABLE ON SCHEMA CMIA_DW.RAW   TO ROLE CMIA_ETL;
GRANT CREATE VIEW  ON SCHEMA CMIA_DW.RAW   TO ROLE CMIA_ETL;
GRANT USAGE      ON SCHEMA CMIA_DW.STAGING TO ROLE CMIA_ETL;
GRANT CREATE TABLE ON SCHEMA CMIA_DW.STAGING TO ROLE CMIA_ETL;
GRANT CREATE VIEW  ON SCHEMA CMIA_DW.STAGING TO ROLE CMIA_ETL;

-- Schema grants for read roles
GRANT USAGE ON SCHEMA CMIA_DW.MARTS TO ROLE CMIA_ANALYST;
GRANT USAGE ON SCHEMA CMIA_DW.MARTS TO ROLE CMIA_API;
GRANT SELECT ON ALL TABLES IN SCHEMA CMIA_DW.MARTS TO ROLE CMIA_ANALYST;
GRANT SELECT ON ALL TABLES IN SCHEMA CMIA_DW.MARTS TO ROLE CMIA_API;
GRANT SELECT ON FUTURE TABLES IN SCHEMA CMIA_DW.MARTS TO ROLE CMIA_ANALYST;
GRANT SELECT ON FUTURE TABLES IN SCHEMA CMIA_DW.MARTS TO ROLE CMIA_API;

-- Admin gets everything
GRANT ALL PRIVILEGES ON DATABASE CMIA_DW TO ROLE CMIA_ADMIN;
GRANT ALL PRIVILEGES ON ALL SCHEMAS IN DATABASE CMIA_DW TO ROLE CMIA_ADMIN;
