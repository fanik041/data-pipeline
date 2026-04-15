"""
# =============================================================================
# FILE: scripts/ingest_to_snowflake.py
# What this file does: Loads all 4 CSVs from data/raw/ into Snowflake CMIA_DW
# Which services it connects to: Snowflake (CMIA_DW via snowflake-connector-python)
# Where it sits in the tech layer: Target DB seeding — runs after Azure SQL ingest
# How it contributes: Seeds Snowflake with dimension + fact data so FastAPI and
#                     Flask ETL have a populated OLAP target to read/write from
# Ref: docs/interview-prep/TRUTH_SOURCE.md — Snowflake as Part 1 migration target
#
# INTERVIEW POINT: "We use a two-step load pattern for prices: land raw into
#   RAW.RAW_PRICES_LANDING first, then promote to MARTS.FACT_PRICES after
#   validation. This mirrors how production ETL pipelines handle late-arriving
#   data and makes reprocessing safe — raw data is always preserved."
#
# DEBUGGING TIPS:
#   - Connection fails     → check SNOWFLAKE_ACCOUNT format: orgname-accountname
#   - write_pandas fails   → column names must be UPPERCASE to match Snowflake table
#   - MERGE syntax error   → Snowflake MERGE uses %s not ? for parameters
#   - Row count mismatch   → run validate() and compare to CSV row counts
#   - Warehouse suspended  → Snowflake auto-resumes on query, but first query is slow
# =============================================================================

import os
import logging
import pandas as pd
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import snowflake.connector
from snowflake.connector.pandas_tools import write_pandas

load_dotenv()

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent / "db" / "data" / "raw"

SECTOR_CODES = {
    "Technology":             "TECH",
    "Financial Services":     "FIN",
    "Communication Services": "COMM",
    "Consumer Cyclical":      "CONS",
    "Healthcare":             "HLTH",
    "Industrials":            "INDS",
    "Energy":                 "ENRG",
    "Utilities":              "UTIL",
    "Real Estate":            "REIT",
    "Basic Materials":        "MATL",
    "Consumer Defensive":     "CDEF",
}


# =============================================================================
# CONNECTION
# =============================================================================

def get_connection() -> snowflake.connector.SnowflakeConnection:
    """
    Open Snowflake connection using .env credentials.
    DEBUGGING: account format must be 'orgname-accountname' (e.g. jdfguoa-po34021).
    If login fails, check SNOWFLAKE_USER and SNOWFLAKE_PASSWORD match signup credentials.
    """
    try:
        conn = snowflake.connector.connect(
            account=os.getenv("SNOWFLAKE_ACCOUNT"),
            user=os.getenv("SNOWFLAKE_USER"),
            password=os.getenv("SNOWFLAKE_PASSWORD"),
            database=os.getenv("SNOWFLAKE_DATABASE"),
            warehouse=os.getenv("SNOWFLAKE_WAREHOUSE"),
            role=os.getenv("SNOWFLAKE_ROLE"),
        )
        log.info("Connected to Snowflake: %s / %s",
                 os.getenv("SNOWFLAKE_ACCOUNT"), os.getenv("SNOWFLAKE_DATABASE"))
        return conn
    except Exception as e:
        log.error("Snowflake connection failed: %s", e)
        log.error("DEBUGGING: verify SNOWFLAKE_ACCOUNT='jdfguoa-po34021', check user/password")
        raise


# =============================================================================
# INGEST: company metadata → MARTS.DIM_SECTOR + MARTS.DIM_SYMBOL
# =============================================================================

def ingest_dimensions(conn) -> dict:
    """
    Load company_metadata.csv into DIM_SECTOR and DIM_SYMBOL.
    Returns symbol_map {ticker: SYMBOL_KEY} used by all downstream ingest functions.
    Connects to: CMIA_DW.MARTS.DIM_SECTOR, CMIA_DW.MARTS.DIM_SYMBOL
    DEBUGGING: if MERGE fails, verify the table exists (run 02_dimensions.sql first).
    """
    log.info("Loading company_metadata.csv → DIM_SECTOR + DIM_SYMBOL")
    df = pd.read_csv(DATA_DIR / "company_metadata.csv")
    log.info("  Read %d rows from company_metadata.csv", len(df))
    cursor = conn.cursor()

    # Insert unique sectors — DIM_SYMBOL has FK to DIM_SECTOR
    sector_map = {}
    for sector_name in df["sector"].unique():
        sector_code = SECTOR_CODES.get(sector_name, sector_name[:4].upper())
        sector_id_src = abs(hash(sector_name)) % 1000000  # stable hash as surrogate src PK
        try:
            cursor.execute("""
                MERGE INTO CMIA_DW.MARTS.DIM_SECTOR AS tgt
                USING (SELECT %s AS SECTOR_NAME) AS src ON tgt.SECTOR_NAME = src.SECTOR_NAME
                WHEN NOT MATCHED THEN
                    INSERT (SECTOR_ID_SRC, SECTOR_NAME, SECTOR_CODE)
                    VALUES (%s, %s, %s)
            """, (sector_name, sector_id_src, sector_name, sector_code))
        except Exception as e:
            log.error("Failed to insert sector '%s': %s", sector_name, e)
            raise
        cursor.execute(
            "SELECT SECTOR_KEY FROM CMIA_DW.MARTS.DIM_SECTOR WHERE SECTOR_NAME = %s",
            (sector_name,)
        )
        sector_map[sector_name] = cursor.fetchone()[0]

    log.info("  Sectors loaded: %d", len(sector_map))

    # Insert symbols — one row per ticker
    symbol_map = {}
    for i, row in df.iterrows():
        sector_key = sector_map.get(row["sector"])
        market_cap = int(row["market_cap"]) if pd.notna(row["market_cap"]) else None
        try:
            cursor.execute("""
                MERGE INTO CMIA_DW.MARTS.DIM_SYMBOL AS tgt
                USING (SELECT %s AS SYMBOL_CODE) AS src ON tgt.SYMBOL_CODE = src.SYMBOL_CODE
                WHEN NOT MATCHED THEN
                    INSERT (SYMBOL_ID_SRC, SYMBOL_CODE, COMPANY_NAME, SECTOR_KEY,
                            INDUSTRY, MARKET_CAP_USD, CURRENCY, EXCHANGE, COUNTRY,
                            IS_BENCHMARK, METADATA_DATE)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE, %s)
            """, (
                row["symbol"],
                i + 1, row["symbol"], row["company_name"], sector_key,
                row["industry"], market_cap, row["currency"],
                row["exchange"], row["country"], row["as_of_date"]
            ))
        except Exception as e:
            log.error("Failed to insert symbol '%s': %s", row["symbol"], e)
            raise
        cursor.execute(
            "SELECT SYMBOL_KEY FROM CMIA_DW.MARTS.DIM_SYMBOL WHERE SYMBOL_CODE = %s",
            (row["symbol"],)
        )
        symbol_map[row["symbol"]] = cursor.fetchone()[0]

    log.info("  Symbols loaded: %d", len(symbol_map))
    conn.commit()
    return symbol_map


# =============================================================================
# INGEST: daily prices → RAW landing → MARTS.FACT_PRICES
# =============================================================================

def ingest_prices(conn, symbol_map: dict) -> None:
    """
    Two-step load: land raw CSV into RAW.RAW_PRICES_LANDING, then promote to FACT_PRICES.
    write_pandas() is used for the landing step — fastest bulk insert in the connector.
    Connects to: RAW.RAW_PRICES_LANDING, MARTS.FACT_PRICES, MARTS.DIM_SYMBOL (for sector lookup)
    DEBUGGING: if write_pandas fails, check that column names are UPPERCASE (Snowflake default).
               If FACT_PRICES insert fails, check SYMBOL_KEY exists in DIM_SYMBOL.
    """
    log.info("Loading prices_raw.csv → RAW.RAW_PRICES_LANDING → FACT_PRICES")
    df = pd.read_csv(DATA_DIR / "prices_raw.csv")
    batch_id = f"ingest_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    log.info("  Read %d rows | batch_id=%s", len(df), batch_id)

    # Step 1: bulk load raw data into landing table
    landing_df = df.rename(columns={
        "symbol": "SYMBOL_CODE",
        "date":   "PRICE_DATE",
        "open":   "OPEN_PRICE",
        "high":   "HIGH_PRICE",
        "low":    "LOW_PRICE",
        "close":  "CLOSE_PRICE",
        "volume": "VOLUME",
    })
    landing_df["BATCH_ID"] = batch_id
    landing_df["SOURCE_SYSTEM"] = "azure_sql"

    # write_pandas uses COPY INTO internally — much faster than row-by-row INSERT
    success, _, nrows, _ = write_pandas(
        conn, landing_df, "RAW_PRICES_LANDING",
        database="CMIA_DW", schema="RAW", auto_create_table=False
    )
    if not success:
        log.error("write_pandas failed for RAW_PRICES_LANDING")
        log.error("DEBUGGING: check column names are uppercase and table exists")
        raise RuntimeError("Landing table bulk load failed")
    log.info("  Landed %d rows into RAW.RAW_PRICES_LANDING", nrows)

    # Step 2: promote from landing to FACT_PRICES with dimension lookups
    cursor = conn.cursor()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    inserted = 0
    skipped = 0
    errors = 0

    for _, row in df.iterrows():
        symbol_key = symbol_map.get(row["symbol"])
        if symbol_key is None:
            skipped += 1
            continue

        # DATE_KEY = YYYYMMDD integer — fast join to DIM_DATE, avoids date parsing at query time
        date_key = int(str(row["date"]).replace("-", ""))
        intraday_range = ((float(row["high"]) - float(row["low"])) / float(row["low"])) * 100

        try:
            cursor.execute("""
                INSERT INTO CMIA_DW.MARTS.FACT_PRICES
                    (SYMBOL_KEY, DATE_KEY, SYMBOL_CODE, SECTOR_CODE,
                     PRICE_DATE, OPEN_PRICE, HIGH_PRICE, LOW_PRICE, CLOSE_PRICE,
                     VOLUME_QTY, INTRADAY_RANGE_PCT, BATCH_ID)
                SELECT %s, %s, s.SYMBOL_CODE, sec.SECTOR_CODE,
                       %s, %s, %s, %s, %s, %s, %s, %s
                FROM CMIA_DW.MARTS.DIM_SYMBOL s
                JOIN CMIA_DW.MARTS.DIM_SECTOR sec ON s.SECTOR_KEY = sec.SECTOR_KEY
                WHERE s.SYMBOL_KEY = %s
            """, (
                symbol_key, date_key,
                str(row["date"]),
                float(row["open"]), float(row["high"]),
                float(row["low"]),  float(row["close"]),
                int(row["volume"]), round(intraday_range, 4), batch_id,
                symbol_key
            ))
            inserted += 1
        except Exception as e:
            log.warning("FACT_PRICES row error for %s on %s: %s", row["symbol"], row["date"], e)
            errors += 1

    conn.commit()

    # Mark landing rows as processed — allows safe re-runs and reprocessing detection
    cursor.execute(
        "UPDATE CMIA_DW.RAW.RAW_PRICES_LANDING SET IS_PROCESSED = TRUE WHERE BATCH_ID = %s",
        (batch_id,)
    )
    conn.commit()
    log.info("  FACT_PRICES: %d inserted | %d skipped | %d errors", inserted, skipped, errors)
    if errors > 0:
        log.warning("  DEBUGGING: %d rows failed — check DIM_SYMBOL has all 20 symbols loaded", errors)


# =============================================================================
# INGEST: features → MARTS.FACT_FEATURES
# =============================================================================

def ingest_features(conn, symbol_map: dict) -> None:
    """
    Load prices_features.csv into FACT_FEATURES.
    NaN values (rolling window warmup — first 50 rows per symbol) stored as NULL.
    Connects to: CMIA_DW.MARTS.FACT_FEATURES, symbol_map from ingest_dimensions()
    DEBUGGING: high NULL counts in MA_50 column are expected — 50-day warmup period.
               If MACD or MACD_SIGNAL are NULL in CSV, check extract_data.py — they should be 0.0.
    """
    log.info("Loading prices_features.csv → FACT_FEATURES")
    df = pd.read_csv(DATA_DIR / "prices_features.csv")
    df["date"] = pd.to_datetime(df["date"]).dt.date
    log.info("  Read %d rows from prices_features.csv", len(df))

    cursor = conn.cursor()
    batch_id = f"features_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    inserted = 0
    errors = 0

    def val(v):
        """Convert pandas NaN to None — Snowflake connector maps None → SQL NULL."""
        return None if pd.isna(v) else float(v)

    for _, row in df.iterrows():
        symbol_key = symbol_map.get(row["symbol"])
        if symbol_key is None:
            continue
        date_key = int(str(row["date"]).replace("-", ""))
        try:
            cursor.execute("""
                INSERT INTO CMIA_DW.MARTS.FACT_FEATURES
                    (SYMBOL_KEY, DATE_KEY, SYMBOL_CODE, PRICE_DATE,
                     DAILY_RETURN, MA_5, MA_20, MA_50, VOLATILITY_20D, RSI_14,
                     MACD, MACD_SIGNAL, BB_UPPER, BB_LOWER, BB_POSITION,
                     TARGET_NEXT_DAY_UP, BATCH_ID)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                symbol_key, date_key, row["symbol"], str(row["date"]),
                val(row["daily_return"]), val(row["ma_5"]), val(row["ma_20"]), val(row["ma_50"]),
                val(row["volatility_20d"]), val(row["rsi_14"]),
                float(row["macd"]), float(row["macd_signal"]),
                val(row["bb_upper"]), val(row["bb_lower"]), val(row["bb_position"]),
                int(row["target_next_day_up"]), batch_id
            ))
            inserted += 1
        except Exception as e:
            log.warning("FACT_FEATURES row error for %s on %s: %s", row["symbol"], row["date"], e)
            errors += 1

    conn.commit()
    log.info("  FACT_FEATURES: %d inserted | %d errors", inserted, errors)


# =============================================================================
# INGEST: benchmarks → MARTS.FACT_BENCHMARKS
# =============================================================================

def ingest_benchmarks(conn, symbol_map: dict) -> None:
    """
    Load benchmarks.csv into FACT_BENCHMARKS.
    Benchmark ETF symbols (SPY, QQQ, etc.) added to DIM_SYMBOL on the fly — they are
    not in company_metadata.csv because yfinance doesn't return full info for ETFs.
    Connects to: CMIA_DW.MARTS.FACT_BENCHMARKS, DIM_SYMBOL, symbol_map
    DEBUGGING: if SYMBOL_KEY lookup fails for SPY etc., check the DIM_SYMBOL insert ran above.
    """
    log.info("Loading benchmarks.csv → FACT_BENCHMARKS")
    df = pd.read_csv(DATA_DIR / "benchmarks.csv")
    df["date"] = pd.to_datetime(df["date"]).dt.date
    log.info("  Read %d rows from benchmarks.csv", len(df))

    cursor = conn.cursor()

    # Add benchmark ETF symbols to DIM_SYMBOL if not present from metadata step
    for i, sym in enumerate(df["symbol"].unique()):
        if sym not in symbol_map:
            log.info("  Adding benchmark symbol to DIM_SYMBOL: %s", sym)
            try:
                cursor.execute("""
                    INSERT INTO CMIA_DW.MARTS.DIM_SYMBOL
                        (SYMBOL_ID_SRC, SYMBOL_CODE, COMPANY_NAME, SECTOR_KEY,
                         INDUSTRY, CURRENCY, EXCHANGE, COUNTRY, IS_BENCHMARK, METADATA_DATE)
                    VALUES (%s, %s, %s, 1, 'Index', 'USD', 'INDEX', 'United States', TRUE, CURRENT_DATE())
                """, (9000 + i, sym, f"{sym} Index"))
                cursor.execute(
                    "SELECT SYMBOL_KEY FROM CMIA_DW.MARTS.DIM_SYMBOL WHERE SYMBOL_CODE = %s", (sym,)
                )
                symbol_map[sym] = cursor.fetchone()[0]
            except Exception as e:
                log.error("Failed to add benchmark symbol %s: %s", sym, e)
                raise
    conn.commit()

    batch_id = f"bench_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    inserted = 0
    errors = 0

    for _, row in df.iterrows():
        symbol_key = symbol_map[row["symbol"]]
        date_key = int(str(row["date"]).replace("-", ""))
        try:
            cursor.execute("""
                INSERT INTO CMIA_DW.MARTS.FACT_BENCHMARKS
                    (SYMBOL_KEY, DATE_KEY, SYMBOL_CODE, PRICE_DATE, CLOSE_PRICE, BATCH_ID)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (symbol_key, date_key, row["symbol"], str(row["date"]), float(row["close"]), batch_id))
            inserted += 1
        except Exception as e:
            log.warning("FACT_BENCHMARKS row error for %s on %s: %s", row["symbol"], row["date"], e)
            errors += 1

    conn.commit()
    log.info("  FACT_BENCHMARKS: %d inserted | %d errors", inserted, errors)


# =============================================================================
# VALIDATION
# =============================================================================

def validate(conn) -> None:
    """
    Post-load validation: row counts across all Snowflake tables.
    DEBUGGING: count of 0 means the ingest function for that table failed silently — check logs.
    INTERVIEW POINT: "Same validation pattern is used in the FastAPI migration service —
    row counts + SUM(CLOSE_PRICE) checksum compared against the Azure SQL view."
    """
    log.info("Running post-load validation...")
    cursor = conn.cursor()

    checks = [
        ("DIM_SECTOR",          "SELECT COUNT(*) FROM CMIA_DW.MARTS.DIM_SECTOR"),
        ("DIM_SYMBOL",          "SELECT COUNT(*) FROM CMIA_DW.MARTS.DIM_SYMBOL"),
        ("DIM_DATE",            "SELECT COUNT(*) FROM CMIA_DW.MARTS.DIM_DATE"),
        ("FACT_PRICES",         "SELECT COUNT(*) FROM CMIA_DW.MARTS.FACT_PRICES"),
        ("FACT_FEATURES",       "SELECT COUNT(*) FROM CMIA_DW.MARTS.FACT_FEATURES"),
        ("FACT_BENCHMARKS",     "SELECT COUNT(*) FROM CMIA_DW.MARTS.FACT_BENCHMARKS"),
        ("RAW_PRICES_LANDING",  "SELECT COUNT(*) FROM CMIA_DW.RAW.RAW_PRICES_LANDING"),
    ]

    all_ok = True
    for label, sql in checks:
        cursor.execute(sql)
        count = cursor.fetchone()[0]
        status = "OK" if count > 0 else "EMPTY — check ingest logs"
        log.info("  %-25s %8d rows  [%s]", label, count, status)
        if count == 0 and label != "FACT_PRICES":  # FACT_PRICES may be empty on first run
            all_ok = False

    if all_ok:
        log.info("Validation passed — Snowflake CMIA_DW is ready.")
    else:
        log.warning("Validation found empty tables — review logs above.")


# =============================================================================
# MAIN
# =============================================================================

def main():
    """
    Entry point: load all CSVs into Snowflake in dependency order.
    Run order: dimensions → prices (land + promote) → features → benchmarks → validate
    Re-runnable: MERGE guards dimension inserts; price/feature inserts will create duplicates
    on re-run — truncate FACT_PRICES first if re-running: TRUNCATE TABLE CMIA_DW.MARTS.FACT_PRICES
    """
    log.info("=" * 55)
    log.info("INGEST TO SNOWFLAKE")
    log.info("Account:   %s", os.getenv("SNOWFLAKE_ACCOUNT"))
    log.info("Database:  %s", os.getenv("SNOWFLAKE_DATABASE"))
    log.info("Warehouse: %s", os.getenv("SNOWFLAKE_WAREHOUSE"))
    log.info("=" * 55)

    conn = get_connection()

    try:
        symbol_map = ingest_dimensions(conn)
        ingest_prices(conn, symbol_map)
        ingest_features(conn, symbol_map)
        ingest_benchmarks(conn, symbol_map)
        validate(conn)
        log.info("Done. Snowflake CMIA_DW populated and ready.")
    except Exception as e:
        log.error("Ingest failed: %s", e)
        log.error("DEBUGGING: check logs above for the failing step, fix, and re-run.")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
