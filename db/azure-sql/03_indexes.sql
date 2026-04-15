-- =============================================================================
-- FILE: db/azure-sql/03_indexes.sql
-- Layer: Source DB — Azure SQL performance layer
-- Connects to: 02_tables.sql (tables must exist)
-- Goal: Cover the three dominant query patterns without over-indexing.
--       Every index here has a specific query it serves — no speculative indexes.
-- Run order: 3rd — after 02_tables.sql
-- =============================================================================

-- =============================================================================
-- QUERY PATTERN ANALYSIS (what the FastAPI routers and migration scripts run)
--
-- Pattern 1: "Give me all prices for symbol X between date A and B"
--   SELECT * FROM market.daily_prices WHERE symbol_code = ? AND price_date BETWEEN ? AND ?
--   → needs: (symbol_code, price_date) covering index
--
-- Pattern 2: "Give me latest features for symbol X"
--   SELECT TOP 1 * FROM market.price_features WHERE symbol_id = ? ORDER BY price_date DESC
--   → needs: (symbol_id, price_date DESC)
--
-- Pattern 3: "Migration extract — give me all rows newer than last batch"
--   SELECT * FROM market.daily_prices WHERE created_at >= ?
--   → needs: (created_at) index
--
-- Pattern 4: "Portfolio view — all symbols for a given date"
--   SELECT * FROM market.daily_prices WHERE price_date = ?
--   → needs: (price_date) index
--
-- Pattern 5: "Analytical — sector-wide aggregates" (hits RLS predicate too)
--   SELECT sector, AVG(close) FROM ... JOIN ref.symbols ON ... GROUP BY sector
--   → needs: columnstore index for range scans
-- =============================================================================


-- ── market.daily_prices indexes ───────────────────────────────────────────────

-- Pattern 1: time-series query by symbol — most common API query
CREATE NONCLUSTERED INDEX ix_daily_prices_symbol_date
ON market.daily_prices (symbol_code, price_date)
INCLUDE (open_price, high_price, low_price, close_price, volume);  -- covering: no key lookup needed
GO

-- Pattern 4: cross-symbol snapshot for a given date (portfolio view)
CREATE NONCLUSTERED INDEX ix_daily_prices_date
ON market.daily_prices (price_date)
INCLUDE (symbol_code, close_price, volume);
GO

-- Pattern 3: incremental migration extract by load time
CREATE NONCLUSTERED INDEX ix_daily_prices_created_at
ON market.daily_prices (created_at)
WHERE is_active = 1;   -- filtered: skip soft-deleted rows
GO

-- Pattern 5: analytical — columnstore for range aggregations
-- Columnstore is read-optimised, columnar compression. Same table, different access path.
-- SQL Server picks this automatically for aggregation queries.
CREATE NONCLUSTERED COLUMNSTORE INDEX cix_daily_prices_analytics
ON market.daily_prices (symbol_id, price_date, close_price, volume, symbol_code);
GO


-- ── market.price_features indexes ─────────────────────────────────────────────

-- Pattern 2: latest features for a symbol — predictor inference
CREATE NONCLUSTERED INDEX ix_features_symbol_date
ON market.price_features (symbol_id, price_date DESC)
INCLUDE (daily_return, ma_5, ma_20, rsi_14, macd, target_next_day_up);
GO

-- Batch extract: get all features updated after a given timestamp
CREATE NONCLUSTERED INDEX ix_features_created_at
ON market.price_features (created_at)
WHERE is_active = 1;
GO


-- ── market.benchmark_prices indexes ───────────────────────────────────────────

-- Join benchmarks to equity prices by date (predictor feature join)
CREATE NONCLUSTERED INDEX ix_benchmark_date_symbol
ON market.benchmark_prices (price_date, symbol_code)
INCLUDE (close_price);
GO


-- ── ref.symbols indexes ────────────────────────────────────────────────────────

-- Symbol lookup by code — most joins go through symbol_code
CREATE NONCLUSTERED INDEX ix_symbols_code
ON ref.symbols (symbol_code)
INCLUDE (symbol_id, sector_id, company_name, is_benchmark, is_active);
GO

-- Sector filter — used by RLS predicate and analytical group-bys
CREATE NONCLUSTERED INDEX ix_symbols_sector
ON ref.symbols (sector_id)
INCLUDE (symbol_id, symbol_code, is_active);
GO


-- ── rls.user_sector_access indexes ────────────────────────────────────────────

-- RLS predicate lookup: "does this user have access to this sector?"
-- This runs on EVERY query hitting a secured table — must be fast
CREATE NONCLUSTERED INDEX ix_rls_login_sector
ON rls.user_sector_access (login_name, sector_id)
WHERE is_active = 1 AND revoked_at IS NULL;  -- filtered: only active grants
GO


-- ── audit.etl_log indexes ─────────────────────────────────────────────────────

-- Debug queries: find all batches for a pipeline in time order
CREATE NONCLUSTERED INDEX ix_etl_log_pipeline_started
ON audit.etl_log (pipeline_name, started_at DESC)
INCLUDE (status, rows_inserted, rows_rejected, error_message);
GO
