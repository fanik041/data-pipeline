-- =============================================================================
-- FILE: db/azure-sql/06_views.sql
-- Layer: Source DB — reporting layer (consumed by FastAPI + Power BI)
-- Connects to: market.daily_prices, market.price_features, ref.symbols,
--              ref.sectors — all views go in reports schema
-- Goal: Pre-join common query patterns so application code stays simple.
--       Views inherit RLS from base tables automatically — no extra work needed.
-- Run order: 6th — after 05_stored_procedures.sql
-- =============================================================================


-- =============================================================================
-- reports.v_daily_prices_enriched
-- Daily prices joined with symbol metadata and sector.
-- Used by FastAPI /prices endpoint. RLS on daily_prices auto-filters sector.
-- =============================================================================
CREATE OR ALTER VIEW reports.v_daily_prices_enriched
AS
SELECT
    p.price_date,
    p.symbol_code,
    s.company_name,
    sec.sector_name,
    sec.sector_code,
    s.industry,
    p.open_price,
    p.high_price,
    p.low_price,
    p.close_price,
    p.volume,
    -- intraday range as % of close — useful signal for volatility screening
    CAST(
        (p.high_price - p.low_price) / NULLIF(p.close_price, 0) * 100
        AS DECIMAL(8,4)
    ) AS intraday_range_pct
FROM   market.daily_prices p
INNER JOIN ref.symbols     s   ON p.symbol_id  = s.symbol_id
INNER JOIN ref.sectors     sec ON s.sector_id  = sec.sector_id
WHERE  p.is_active = 1;
GO


-- =============================================================================
-- reports.v_latest_features
-- Most recent feature row per symbol — used for predictor inference (latest state).
-- ROW_NUMBER pattern: returns exactly 1 row per symbol (latest date).
-- =============================================================================
CREATE OR ALTER VIEW reports.v_latest_features
AS
WITH ranked AS (
    SELECT
        f.*,
        s.company_name,
        sec.sector_name,
        ROW_NUMBER() OVER (PARTITION BY f.symbol_id ORDER BY f.price_date DESC) AS rn
                                    -- rn=1 = latest row per symbol; filter below
    FROM   market.price_features f
    INNER JOIN ref.symbols   s   ON f.symbol_id = s.symbol_id
    INNER JOIN ref.sectors   sec ON s.sector_id = sec.sector_id
    WHERE  f.is_active = 1
)
SELECT
    symbol_code,
    company_name,
    sector_name,
    price_date,
    daily_return,
    ma_5, ma_20, ma_50,
    rsi_14,
    macd, macd_signal,
    volatility_20d,
    bb_upper, bb_lower, bb_position,
    target_next_day_up
FROM ranked
WHERE rn = 1;
GO


-- =============================================================================
-- reports.v_sector_summary
-- Daily aggregates by sector — average close, total volume, # symbols.
-- Used for sector-level analytics and migration validation checksums.
-- =============================================================================
CREATE OR ALTER VIEW reports.v_sector_summary
AS
SELECT
    p.price_date,
    sec.sector_name,
    sec.sector_code,
    COUNT(DISTINCT p.symbol_id)         AS symbol_count,
    AVG(p.close_price)                  AS avg_close,
    SUM(p.volume)                       AS total_volume,
    MIN(p.close_price)                  AS min_close,
    MAX(p.close_price)                  AS max_close,
    -- sum of close prices: used as a checksum column in migration validation
    SUM(p.close_price)                  AS close_checksum
FROM   market.daily_prices p
INNER JOIN ref.symbols s   ON p.symbol_id  = s.symbol_id
INNER JOIN ref.sectors sec ON s.sector_id  = sec.sector_id
WHERE  p.is_active = 1
GROUP BY p.price_date, sec.sector_name, sec.sector_code;
GO
