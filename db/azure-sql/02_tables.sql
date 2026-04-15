-- =============================================================================
-- FILE: db/azure-sql/02_tables.sql
-- Layer: Source DB — Azure SQL (OLTP)
-- Connects to: 01_schemas.sql (schemas must exist), ingest scripts (write),
--              FastAPI routers (read), migration scripts (extract)
-- Goal: Define all OLTP tables normalised to 3NF. Data types chosen from
--       actual CSV analysis — no guessing. Audit columns on every table.
-- Ref: docs/interview-prep/TRUTH_SOURCE.md — OLTP source design
-- Run order: 2nd — after 01_schemas.sql
-- =============================================================================

-- =============================================================================
-- DATA TYPE DECISIONS (from CSV analysis)
-- symbol       : NVARCHAR(10)   — max observed 5 chars (GOOGL), 10 gives headroom
-- price        : DECIMAL(12,4)  — range 11.21–1038.08; 12,4 handles up to $99M/share
-- volume       : BIGINT         — max observed 1,543,911,000 → INT overflows, use BIGINT
-- market_cap   : BIGINT         — max observed 3.9 trillion → INT/BIGINT needed
-- pct_return   : DECIMAL(10,6)  — daily returns e.g. -0.026600 → 6 decimal places
-- indicator    : DECIMAL(14,6)  — MACD can be large-magnitude; RSI 0–100
-- rsi          : DECIMAL(6,2)   — bounded 0–100, 2 decimals sufficient
-- target_label : BIT            — binary 0/1 (next-day-up predictor label)
-- date         : DATE           — no time component needed for daily data
-- =============================================================================


-- =============================================================================
-- ref.sectors
-- Master list of market sectors. FK target for ref.symbols.
-- =============================================================================
CREATE TABLE ref.sectors (
    sector_id       INT IDENTITY(1,1)   NOT NULL,
    sector_name     NVARCHAR(100)       NOT NULL,   -- e.g. "Technology", "Financial Services"
    sector_code     NVARCHAR(10)        NOT NULL,   -- short code for joins: "TECH", "FIN"
    created_at      DATETIME2(0)        NOT NULL    CONSTRAINT df_sectors_created  DEFAULT GETUTCDATE(),
    updated_at      DATETIME2(0)        NOT NULL    CONSTRAINT df_sectors_updated  DEFAULT GETUTCDATE(),
    is_active       BIT                 NOT NULL    CONSTRAINT df_sectors_active   DEFAULT 1,

    CONSTRAINT pk_sectors               PRIMARY KEY CLUSTERED (sector_id),
    CONSTRAINT uq_sectors_name          UNIQUE (sector_name),
    CONSTRAINT uq_sectors_code          UNIQUE (sector_code)
);
GO

-- =============================================================================
-- ref.symbols
-- One row per ticker. Master reference for all price and feature tables.
-- Populated from company_metadata.csv (20 rows).
-- =============================================================================
CREATE TABLE ref.symbols (
    symbol_id       INT IDENTITY(1,1)   NOT NULL,
    symbol_code     NVARCHAR(10)        NOT NULL,   -- e.g. "AAPL" — matches CSV column
    company_name    NVARCHAR(255)       NOT NULL,
    sector_id       INT                 NOT NULL,   -- FK → ref.sectors
    industry        NVARCHAR(255)       NOT NULL,
    market_cap      BIGINT              NULL,       -- nullable: can change, may be stale
    currency        NVARCHAR(3)         NOT NULL    CONSTRAINT df_symbols_currency DEFAULT 'USD',
    exchange        NVARCHAR(20)        NOT NULL,
    country         NVARCHAR(100)       NOT NULL,
    is_benchmark    BIT                 NOT NULL    CONSTRAINT df_symbols_bench    DEFAULT 0, -- 1 = SPY/QQQ etc
    source_system   NVARCHAR(50)        NOT NULL    CONSTRAINT df_symbols_source   DEFAULT 'yfinance',
    metadata_date   DATE                NOT NULL,   -- as_of_date from CSV — when metadata was snapshotted
    created_at      DATETIME2(0)        NOT NULL    CONSTRAINT df_symbols_created  DEFAULT GETUTCDATE(),
    updated_at      DATETIME2(0)        NOT NULL    CONSTRAINT df_symbols_updated  DEFAULT GETUTCDATE(),
    is_active       BIT                 NOT NULL    CONSTRAINT df_symbols_active   DEFAULT 1,

    CONSTRAINT pk_symbols               PRIMARY KEY CLUSTERED (symbol_id),
    CONSTRAINT uq_symbols_code          UNIQUE (symbol_code),
    CONSTRAINT fk_symbols_sector        FOREIGN KEY (sector_id) REFERENCES ref.sectors(sector_id)
);
GO

-- =============================================================================
-- market.daily_prices
-- Core OHLCV table. One row per symbol per trading day.
-- 15,040 rows at load; grows by ~20 rows/trading day as new data arrives.
-- Partitioned by year for scalable range-scans (see 03_indexes.sql).
-- =============================================================================
CREATE TABLE market.daily_prices (
    price_id        BIGINT IDENTITY(1,1) NOT NULL,
    symbol_id       INT                 NOT NULL,   -- FK → ref.symbols
    symbol_code     NVARCHAR(10)        NOT NULL,   -- denormalised for query perf without join
    price_date      DATE                NOT NULL,
    open_price      DECIMAL(12,4)       NOT NULL,
    high_price      DECIMAL(12,4)       NOT NULL,
    low_price       DECIMAL(12,4)       NOT NULL,
    close_price     DECIMAL(12,4)       NOT NULL,
    adj_close       DECIMAL(12,4)       NULL,       -- split/dividend adjusted close (future use)
    volume          BIGINT              NOT NULL,
    source_system   NVARCHAR(50)        NOT NULL    CONSTRAINT df_prices_source    DEFAULT 'yfinance',
    batch_id        NVARCHAR(50)        NULL,        -- ETL batch that loaded this row
    created_at      DATETIME2(0)        NOT NULL    CONSTRAINT df_prices_created   DEFAULT GETUTCDATE(),
    is_active       BIT                 NOT NULL    CONSTRAINT df_prices_active    DEFAULT 1,

    CONSTRAINT pk_daily_prices          PRIMARY KEY CLUSTERED (price_id),
    CONSTRAINT uq_daily_prices_sym_date UNIQUE (symbol_id, price_date),  -- natural key
    CONSTRAINT fk_daily_prices_symbol   FOREIGN KEY (symbol_id) REFERENCES ref.symbols(symbol_id),
    CONSTRAINT ck_prices_ohlc           CHECK (
        low_price  <= open_price  AND
        low_price  <= close_price AND
        high_price >= open_price  AND
        high_price >= close_price AND
        low_price  >= 0           AND
        volume     >= 0
    )
);
GO

-- =============================================================================
-- market.price_features
-- Technical indicator features per symbol per day.
-- NULLs in rolling columns are expected and valid (first N rows per symbol
-- have insufficient history — not data quality issues).
-- =============================================================================
CREATE TABLE market.price_features (
    feature_id          BIGINT IDENTITY(1,1) NOT NULL,
    symbol_id           INT                  NOT NULL,   -- FK → ref.symbols
    symbol_code         NVARCHAR(10)         NOT NULL,
    price_date          DATE                 NOT NULL,

    -- Returns
    daily_return        DECIMAL(10,6)        NULL,   -- NULL on first row per symbol (no prior close)

    -- Moving averages — NULL for first (window-1) rows per symbol
    ma_5                DECIMAL(12,4)        NULL,
    ma_20               DECIMAL(12,4)        NULL,
    ma_50               DECIMAL(12,4)        NULL,

    -- Volatility
    volatility_20d      DECIMAL(10,6)        NULL,   -- annualised, NULL for first 20 rows

    -- RSI (0–100 oscillator)
    rsi_14              DECIMAL(6,2)         NULL,   -- NULL for first 14 rows

    -- MACD components
    macd                DECIMAL(14,6)        NOT NULL,  -- EMA difference, never NULL (EWM handles warmup)
    macd_signal         DECIMAL(14,6)        NOT NULL,

    -- Bollinger Bands
    bb_upper            DECIMAL(12,4)        NULL,
    bb_lower            DECIMAL(12,4)        NULL,
    bb_position         DECIMAL(10,6)        NULL,   -- 0=at lower band, 1=at upper band

    -- ML target label
    target_next_day_up  BIT                  NOT NULL,  -- 1 if close(t+1) > close(t)

    -- Audit
    source_system       NVARCHAR(50)         NOT NULL  CONSTRAINT df_features_source  DEFAULT 'yfinance',
    batch_id            NVARCHAR(50)         NULL,
    created_at          DATETIME2(0)         NOT NULL  CONSTRAINT df_features_created DEFAULT GETUTCDATE(),
    is_active           BIT                  NOT NULL  CONSTRAINT df_features_active  DEFAULT 1,

    CONSTRAINT pk_price_features            PRIMARY KEY CLUSTERED (feature_id),
    CONSTRAINT uq_features_sym_date         UNIQUE (symbol_id, price_date),
    CONSTRAINT fk_features_symbol           FOREIGN KEY (symbol_id) REFERENCES ref.symbols(symbol_id)
);
GO

-- =============================================================================
-- market.benchmark_prices
-- Daily close for market indices (SPY, QQQ, IEF, GLD, TLT).
-- Separate table: different schema from equities (no OHLCV, only close).
-- Used as market-context features for the stock predictor.
-- =============================================================================
CREATE TABLE market.benchmark_prices (
    benchmark_id    BIGINT IDENTITY(1,1) NOT NULL,
    symbol_id       INT                 NOT NULL,   -- FK → ref.symbols (is_benchmark = 1)
    symbol_code     NVARCHAR(10)        NOT NULL,
    price_date      DATE                NOT NULL,
    close_price     DECIMAL(12,4)       NOT NULL,
    source_system   NVARCHAR(50)        NOT NULL    CONSTRAINT df_bench_source  DEFAULT 'yfinance',
    batch_id        NVARCHAR(50)        NULL,
    created_at      DATETIME2(0)        NOT NULL    CONSTRAINT df_bench_created DEFAULT GETUTCDATE(),
    is_active       BIT                 NOT NULL    CONSTRAINT df_bench_active  DEFAULT 1,

    CONSTRAINT pk_benchmark_prices      PRIMARY KEY CLUSTERED (benchmark_id),
    CONSTRAINT uq_benchmark_sym_date    UNIQUE (symbol_id, price_date),
    CONSTRAINT fk_benchmark_symbol      FOREIGN KEY (symbol_id) REFERENCES ref.symbols(symbol_id),
    CONSTRAINT ck_bench_price           CHECK (close_price >= 0)
);
GO

-- =============================================================================
-- rls.user_sector_access
-- Maps database login → sector(s) they are allowed to read.
-- Used by the RLS predicate function (see 04_rls.sql).
-- Admins: not in this table — bypass handled in predicate function.
-- =============================================================================
CREATE TABLE rls.user_sector_access (
    access_id       INT IDENTITY(1,1)   NOT NULL,
    login_name      NVARCHAR(128)       NOT NULL,   -- DATABASE_PRINCIPAL_ID / USER_NAME()
    sector_id       INT                 NOT NULL,   -- FK → ref.sectors
    granted_by      NVARCHAR(128)       NOT NULL,
    granted_at      DATETIME2(0)        NOT NULL    CONSTRAINT df_rls_granted DEFAULT GETUTCDATE(),
    revoked_at      DATETIME2(0)        NULL,        -- NULL = still active
    is_active       BIT                 NOT NULL    CONSTRAINT df_rls_active  DEFAULT 1,

    CONSTRAINT pk_user_sector_access    PRIMARY KEY CLUSTERED (access_id),
    CONSTRAINT uq_user_sector           UNIQUE (login_name, sector_id),
    CONSTRAINT fk_rls_sector            FOREIGN KEY (sector_id) REFERENCES ref.sectors(sector_id)
);
GO

-- =============================================================================
-- audit.etl_log
-- One row per ETL batch run. Records source, row counts, status, duration.
-- Used to track migrations, debug failures, and prove idempotency.
-- =============================================================================
CREATE TABLE audit.etl_log (
    log_id          BIGINT IDENTITY(1,1) NOT NULL,
    batch_id        NVARCHAR(50)         NOT NULL,   -- UUID assigned by ETL script
    pipeline_name   NVARCHAR(100)        NOT NULL,   -- e.g. "yfinance_to_azure_sql"
    source_system   NVARCHAR(100)        NOT NULL,
    target_table    NVARCHAR(100)        NOT NULL,
    rows_extracted  BIGINT               NULL,
    rows_inserted   BIGINT               NULL,
    rows_updated    BIGINT               NULL,
    rows_rejected   BIGINT               NULL        CONSTRAINT df_log_rejected DEFAULT 0,
    status          NVARCHAR(20)         NOT NULL,   -- 'RUNNING', 'SUCCESS', 'FAILED', 'PARTIAL'
    error_message   NVARCHAR(MAX)        NULL,
    started_at      DATETIME2(3)         NOT NULL    CONSTRAINT df_log_started  DEFAULT GETUTCDATE(),
    completed_at    DATETIME2(3)         NULL,
    duration_ms     AS DATEDIFF(MILLISECOND, started_at, completed_at),  -- computed column

    CONSTRAINT pk_etl_log               PRIMARY KEY CLUSTERED (log_id),
    CONSTRAINT ck_log_status            CHECK (status IN ('RUNNING','SUCCESS','FAILED','PARTIAL'))
);
GO
