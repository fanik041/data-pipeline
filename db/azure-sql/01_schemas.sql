-- =============================================================================
-- FILE: db/azure-sql/01_schemas.sql
-- Layer: Source DB — Azure SQL (OLTP, simulates legacy SQL Server)
-- Connects to: yfinance CSVs (ingest), Snowflake migration (output)
-- Goal: Create logical schema namespaces before any tables are created.
--       Separates concerns so objects don't collide and permissions are clean.
-- Ref: docs/interview-prep/TRUTH_SOURCE.md — "SQL Server / Oracle (legacy source)"
-- Run order: 1st — must run before any other script in this folder
-- =============================================================================

-- dbo       : default schema, kept for backwards compat with legacy tooling
-- market    : all price and trading data (OHLCV, features, benchmarks)
-- ref       : reference / dimension data (symbols, sectors, metadata)
-- audit     : ETL logs, change history, batch tracking
-- rls       : row-level security objects (functions, policies, access tables)
-- reports   : views consumed by downstream tools (Power BI, FastAPI)

CREATE SCHEMA market    AUTHORIZATION dbo;
CREATE SCHEMA ref       AUTHORIZATION dbo;
CREATE SCHEMA audit     AUTHORIZATION dbo;
CREATE SCHEMA rls       AUTHORIZATION dbo;
CREATE SCHEMA reports   AUTHORIZATION dbo;
GO
