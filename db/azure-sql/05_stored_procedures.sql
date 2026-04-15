-- =============================================================================
-- FILE: db/azure-sql/05_stored_procedures.sql
-- Layer: Source DB — business logic layer (OLTP)
-- Connects to: market.daily_prices, market.price_features, ref.symbols,
--              audit.etl_log, FastAPI migration router
-- Goal: Encapsulate repeatable business logic in procs — mirrors what CMIA
--       would have in a real SQL Server environment. The migration challenge is
--       rewriting these into Snowflake-native SQL/JavaScript UDFs.
-- Run order: 5th — after 04_rls.sql
-- =============================================================================


-- =============================================================================
-- sp_upsert_daily_prices
-- Idempotent load: INSERT new rows, UPDATE changed rows, skip unchanged.
-- Called by the FastAPI /migrate endpoint and the ingest script.
-- Uses MERGE (T-SQL) — Snowflake equivalent is MERGE INTO ... USING ...
-- =============================================================================
CREATE OR ALTER PROCEDURE market.sp_upsert_daily_prices
    @symbol_code    NVARCHAR(10),
    @price_date     DATE,
    @open_price     DECIMAL(12,4),
    @high_price     DECIMAL(12,4),
    @low_price      DECIMAL(12,4),
    @close_price    DECIMAL(12,4),
    @volume         BIGINT,
    @batch_id       NVARCHAR(50)    = NULL,
    @source_system  NVARCHAR(50)    = 'yfinance'
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @symbol_id INT;

    -- Resolve symbol_code → symbol_id (fail loudly if symbol not in ref table)
    SELECT @symbol_id = symbol_id
    FROM   ref.symbols
    WHERE  symbol_code = @symbol_code AND is_active = 1;

    IF @symbol_id IS NULL
        THROW 50001, 'Symbol not found in ref.symbols — load ref data first.', 1;

    -- MERGE: single statement for insert-or-update; avoids race condition vs INSERT+UPDATE
    MERGE market.daily_prices AS target
    USING (
        SELECT @symbol_id AS symbol_id, @symbol_code AS symbol_code,
               @price_date AS price_date, @open_price AS open_price,
               @high_price AS high_price, @low_price AS low_price,
               @close_price AS close_price, @volume AS volume
    ) AS source
    ON target.symbol_id = source.symbol_id AND target.price_date = source.price_date

    WHEN MATCHED AND (                              -- only update if values actually changed
        target.close_price <> source.close_price OR
        target.volume      <> source.volume
    ) THEN UPDATE SET
        open_price   = source.open_price,
        high_price   = source.high_price,
        low_price    = source.low_price,
        close_price  = source.close_price,
        volume       = source.volume,
        batch_id     = @batch_id,
        updated_at   = GETUTCDATE()                -- explicit updated_at on change

    WHEN NOT MATCHED BY TARGET THEN INSERT
        (symbol_id, symbol_code, price_date, open_price, high_price,
         low_price, close_price, volume, batch_id, source_system)
    VALUES
        (source.symbol_id, source.symbol_code, source.price_date, source.open_price,
         source.high_price, source.low_price, source.close_price, source.volume,
         @batch_id, @source_system);
END;
GO


-- =============================================================================
-- sp_get_symbol_time_series
-- Returns OHLCV + features for a symbol over a date range.
-- Used by FastAPI /prices endpoint. JOIN is pre-optimised via indexes.
-- =============================================================================
CREATE OR ALTER PROCEDURE market.sp_get_symbol_time_series
    @symbol_code    NVARCHAR(10),
    @date_from      DATE,
    @date_to        DATE
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        p.symbol_code,
        p.price_date,
        p.open_price,
        p.high_price,
        p.low_price,
        p.close_price,
        p.volume,
        f.daily_return,
        f.ma_5,
        f.ma_20,
        f.ma_50,
        f.rsi_14,
        f.macd,
        f.volatility_20d,
        f.bb_position,
        f.target_next_day_up
    FROM   market.daily_prices  p
    LEFT JOIN market.price_features f           -- LEFT JOIN: features can be null for recent rows
        ON  p.symbol_id  = f.symbol_id
        AND p.price_date = f.price_date
    WHERE  p.symbol_code = @symbol_code
    AND    p.price_date  BETWEEN @date_from AND @date_to
    AND    p.is_active   = 1
    ORDER BY p.price_date ASC;
END;
GO


-- =============================================================================
-- sp_get_migration_extract
-- Returns all price rows modified after a given watermark timestamp.
-- Used by the migration script to do incremental extracts — not full dumps.
-- Watermark pattern: store last successful batch's max(created_at) in audit.etl_log.
-- =============================================================================
CREATE OR ALTER PROCEDURE market.sp_get_migration_extract
    @watermark_ts   DATETIME2(0),               -- extract rows newer than this
    @batch_size     INT             = 50000      -- pagination guard: don't pull everything at once
AS
BEGIN
    SET NOCOUNT ON;

    SELECT TOP (@batch_size)
        p.symbol_id,
        p.symbol_code,
        p.price_date,
        p.open_price,
        p.high_price,
        p.low_price,
        p.close_price,
        p.volume,
        s.sector_id,
        s.company_name,
        s.industry,
        p.created_at
    FROM   market.daily_prices  p
    INNER JOIN ref.symbols      s ON p.symbol_id = s.symbol_id
    WHERE  p.created_at > @watermark_ts
    AND    p.is_active  = 1
    ORDER BY p.created_at ASC;   -- consistent order for watermark advancement
END;
GO


-- =============================================================================
-- sp_log_etl_start / sp_log_etl_end
-- Called by ETL script to open and close audit rows.
-- Returns batch_id so the script can stamp all rows it inserts.
-- =============================================================================
CREATE OR ALTER PROCEDURE audit.sp_log_etl_start
    @pipeline_name  NVARCHAR(100),
    @source_system  NVARCHAR(100),
    @target_table   NVARCHAR(100),
    @batch_id       NVARCHAR(50)    OUTPUT      -- returns generated batch ID
AS
BEGIN
    SET NOCOUNT ON;
    SET @batch_id = CONVERT(NVARCHAR(50), NEWID());   -- UUID as batch ID

    INSERT INTO audit.etl_log
        (batch_id, pipeline_name, source_system, target_table, status)
    VALUES
        (@batch_id, @pipeline_name, @source_system, @target_table, 'RUNNING');
END;
GO

CREATE OR ALTER PROCEDURE audit.sp_log_etl_end
    @batch_id       NVARCHAR(50),
    @status         NVARCHAR(20),               -- 'SUCCESS', 'FAILED', 'PARTIAL'
    @rows_extracted BIGINT          = NULL,
    @rows_inserted  BIGINT          = NULL,
    @rows_updated   BIGINT          = NULL,
    @rows_rejected  BIGINT          = 0,
    @error_message  NVARCHAR(MAX)   = NULL
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE audit.etl_log SET
        status          = @status,
        rows_extracted  = @rows_extracted,
        rows_inserted   = @rows_inserted,
        rows_updated    = @rows_updated,
        rows_rejected   = @rows_rejected,
        error_message   = @error_message,
        completed_at    = GETUTCDATE()          -- duration_ms computed column auto-calculates
    WHERE batch_id = @batch_id;
END;
GO
