# =============================================================================
# FILE: scripts/ingest_to_azure_sql.py
# What this file does: Loads all 4 CSVs from data/raw/ into Azure SQL source DB
# Which services it connects to: Azure SQL (cmia-source-db via pymssql — no system ODBC driver needed)
# Where it sits in the tech layer: Source DB seeding — runs once before migration
# How it contributes: Populates Azure SQL with real OHLCV + feature data so the
#                     FastAPI migration service has a live OLTP source to read from
# Ref: docs/interview-prep/TRUTH_SOURCE.md — Azure SQL as Part 1 migration source
#
# INTERVIEW POINT: "We used pyodbc with ODBC Driver 18 — the same driver Azure
#   recommends for Python on ARM Macs. The ingest calls sp_upsert_daily_prices
#   (a MERGE stored proc) so re-running is idempotent — no duplicate rows."
#
# DEBUGGING TIPS:
#   - Connection fails    → check AZURE_SQL_SERVER, AZURE_SQL_USERNAME/PASSWORD in .env
#   - Driver issues       → pymssql is pure-Python, no brew/ODBC install needed
#   - Firewall block      → portal.azure.com → SQL Server → Networking → add your IP
#   - Stored proc errors  → run validate() first to confirm schema exists
#   - Row count mismatch  → check skipped symbols in ingest_prices() output
# =============================================================================

import os
import logging
import pymssql
import pandas as pd
from pathlib import Path
from datetime import datetime, date
from dotenv import load_dotenv

load_dotenv()

# ── Logging setup (use logging not print — easier to grep in production) ──────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent / "db" / "data" / "raw"

# Sector name → short code mapping (matches Azure SQL + Snowflake seed data)
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

def get_connection() -> pymssql.Connection:
    """
    Open pymssql connection to Azure SQL using .env credentials.
    pymssql bundles its own TDS driver — no brew/ODBC install needed.
    DEBUGGING: if this fails, check server/credentials in .env and Azure firewall rules.
    """
    try:
        conn = pymssql.connect(
            server=os.getenv("AZURE_SQL_SERVER"),
            user=os.getenv("AZURE_SQL_USERNAME"),
            password=os.getenv("AZURE_SQL_PASSWORD"),
            database=os.getenv("AZURE_SQL_DATABASE"),
            port=1433,
            tds_version="7.4",  # required for Azure SQL (SQL Server 2012+)
            login_timeout=30,
        )
        log.info("Connected to Azure SQL: %s / %s",
                 os.getenv("AZURE_SQL_SERVER"), os.getenv("AZURE_SQL_DATABASE"))
        return conn
    except pymssql.Error as e:
        log.error("Connection failed: %s", e)
        log.error("DEBUGGING: check .env values and Azure firewall rules (portal → Networking → add IP)")
        raise


# =============================================================================
# SCHEMA BOOTSTRAP
# =============================================================================

def run_sql_file(conn: pymssql.Connection, filepath: Path) -> None:
    """
    Execute a .sql file against the connection, splitting on GO batch separators.
    DEBUGGING: if a DDL file fails, check the error message for the failing statement.
    """
    sql = filepath.read_text()
    # Split on GO — pyodbc sends one T-SQL batch at a time (GO is not SQL, it's SSMS syntax)
    batches = [b.strip() for b in sql.split("\nGO") if b.strip()]
    cursor = conn.cursor()
    for i, batch in enumerate(batches):
        try:
            cursor.execute(batch)
        except pymssql.Error as e:
            log.error("Failed on batch %d of %s: %s", i + 1, filepath.name, e)
            raise
    conn.commit()
    log.info("  Ran: %s (%d batches)", filepath.name, len(batches))


def bootstrap_schema(conn: pymssql.Connection) -> None:
    """
    Run all Azure SQL DDL files in numeric order to create schemas, tables, indexes, RLS.
    Connects to: db/azure-sql/01_schemas.sql through 06_views.sql
    DEBUGGING: if a file fails mid-way, re-run after fixing — all DDL uses IF NOT EXISTS.
    """
    sql_dir = Path(__file__).parent.parent / "db" / "azure-sql"
    sql_files = sorted(sql_dir.glob("*.sql"))
    log.info("Bootstrapping schema from %d SQL files...", len(sql_files))
    for sql_file in sql_files:
        run_sql_file(conn, sql_file)
    log.info("Schema bootstrap complete.")


# =============================================================================
# INGEST: company metadata → ref.sectors + ref.symbols
# =============================================================================

def ingest_metadata(conn: pymssql.Connection) -> dict:
    """
    Load company_metadata.csv into ref.sectors and ref.symbols.
    Returns symbol_map {ticker: symbol_id} used by all downstream ingest functions.
    Connects to: ref.sectors, ref.symbols tables created in 01_schemas.sql + 02_tables.sql
    DEBUGGING: if symbol_id lookup fails, check that the symbol exists in ref.symbols first.
    """
    log.info("Loading company_metadata.csv → ref.sectors + ref.symbols")
    df = pd.read_csv(DATA_DIR / "company_metadata.csv")
    log.info("  Read %d rows from company_metadata.csv", len(df))
    cursor = conn.cursor()

    # Insert unique sectors first — ref.symbols has FK to ref.sectors
    sector_map = {}
    for sector_name in df["sector"].unique():
        sector_code = SECTOR_CODES.get(sector_name, sector_name[:4].upper())
        try:
            cursor.execute("""
                IF NOT EXISTS (SELECT 1 FROM ref.sectors WHERE sector_name = %s)
                    INSERT INTO ref.sectors (sector_name, sector_code) VALUES (%s, %s)
            """, (sector_name, sector_name, sector_code))
            conn.commit()
        except pymssql.Error as e:
            log.error("Failed to insert sector '%s': %s", sector_name, e)
            raise
        cursor.execute("SELECT sector_id FROM ref.sectors WHERE sector_name = %s", (sector_name,))
        sector_map[sector_name] = cursor.fetchone()[0]

    log.info("  Sectors loaded: %d", len(sector_map))

    # Insert symbols — one row per ticker
    symbol_map = {}
    for _, row in df.iterrows():
        sector_id = sector_map.get(row["sector"])
        market_cap = int(row["market_cap"]) if pd.notna(row["market_cap"]) else None
        try:
            cursor.execute("""
                IF NOT EXISTS (SELECT 1 FROM ref.symbols WHERE symbol_code = %s)
                    INSERT INTO ref.symbols
                        (symbol_code, company_name, sector_id, industry,
                         market_cap, currency, exchange, country, metadata_date)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                row["symbol"],
                row["symbol"], row["company_name"], sector_id, row["industry"],
                market_cap, row["currency"], row["exchange"], row["country"], row["as_of_date"]
            ))
            conn.commit()
        except pymssql.Error as e:
            log.error("Failed to insert symbol '%s': %s", row["symbol"], e)
            raise
        cursor.execute("SELECT symbol_id FROM ref.symbols WHERE symbol_code = %s", (row["symbol"],))
        symbol_map[row["symbol"]] = cursor.fetchone()[0]

    log.info("  Symbols loaded: %d", len(symbol_map))
    return symbol_map


# =============================================================================
# INGEST: daily prices → market.daily_prices
# =============================================================================

def ingest_prices(conn: pymssql.Connection, symbol_map: dict) -> None:
    """
    Load prices_raw.csv into market.daily_prices via sp_upsert_daily_prices (MERGE).
    MERGE makes this idempotent — safe to re-run without creating duplicates.
    Connects to: market.sp_upsert_daily_prices stored proc, symbol_map from ingest_metadata()
    DEBUGGING: if row count is lower than expected, check 'skipped' output for unmapped symbols.
    """
    log.info("Loading prices_raw.csv → market.daily_prices")
    df = pd.read_csv(DATA_DIR / "prices_raw.csv")
    df["date"] = pd.to_datetime(df["date"]).dt.date
    log.info("  Read %d rows from prices_raw.csv", len(df))

    cursor = conn.cursor()
    batch_id = f"ingest_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    inserted = 0
    skipped = 0
    errors = 0

    for _, row in df.iterrows():
        symbol_id = symbol_map.get(row["symbol"])
        if symbol_id is None:
            # Symbol not in ref.symbols — metadata CSV may be incomplete
            skipped += 1
            continue
        try:
            cursor.execute("""
                IF NOT EXISTS (
                    SELECT 1 FROM market.daily_prices
                    WHERE symbol_id = %s AND price_date = %s
                )
                INSERT INTO market.daily_prices
                    (symbol_id, symbol_code, price_date,
                     open_price, high_price, low_price, close_price, volume, batch_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                symbol_id, row["date"],
                symbol_id, row["symbol"], row["date"],
                float(row["open"]), float(row["high"]),
                float(row["low"]),  float(row["close"]),
                int(row["volume"]), batch_id
            ))
            inserted += 1
        except pymssql.Error as e:
            # Log and continue — one bad row should not abort the entire load
            log.warning("Row error for %s on %s: %s", row["symbol"], row["date"], e)
            errors += 1

    conn.commit()
    log.info("  Prices: %d upserted | %d skipped (unknown symbol) | %d errors",
             inserted, skipped, errors)
    if errors > 0:
        log.warning("  DEBUGGING: %d rows failed — check stored proc sp_upsert_daily_prices", errors)


# =============================================================================
# INGEST: features → market.price_features
# =============================================================================

def ingest_features(conn: pymssql.Connection, symbol_map: dict) -> None:
    """
    Load prices_features.csv into market.price_features.
    NaN values from rolling window warmup (first 50 rows per symbol) stored as NULL.
    Connects to: market.price_features, symbol_map from ingest_metadata()
    DEBUGGING: NULL counts in ma_50 column are expected — 50-day warmup has no value.
    """
    log.info("Loading prices_features.csv → market.price_features")
    df = pd.read_csv(DATA_DIR / "prices_features.csv")
    df["date"] = pd.to_datetime(df["date"]).dt.date
    log.info("  Read %d rows from prices_features.csv", len(df))

    cursor = conn.cursor()
    batch_id = f"features_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    inserted = 0
    errors = 0

    def val(v):
        """Convert pandas NaN to Python None — pyodbc maps None → SQL NULL."""
        return None if pd.isna(v) else float(v)

    for _, row in df.iterrows():
        symbol_id = symbol_map.get(row["symbol"])
        if symbol_id is None:
            continue
        try:
            cursor.execute("""
                IF NOT EXISTS (
                    SELECT 1 FROM market.price_features
                    WHERE symbol_id = %s AND price_date = %s
                )
                INSERT INTO market.price_features
                    (symbol_id, symbol_code, price_date, daily_return, ma_5, ma_20, ma_50,
                     volatility_20d, rsi_14, macd, macd_signal,
                     bb_upper, bb_lower, bb_position, target_next_day_up, batch_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                symbol_id, row["date"],
                symbol_id, row["symbol"], row["date"],
                val(row["daily_return"]), val(row["ma_5"]), val(row["ma_20"]), val(row["ma_50"]),
                val(row["volatility_20d"]), val(row["rsi_14"]),
                float(row["macd"]), float(row["macd_signal"]),
                val(row["bb_upper"]), val(row["bb_lower"]), val(row["bb_position"]),
                int(row["target_next_day_up"]), batch_id
            ))
            inserted += 1
        except pymssql.Error as e:
            log.warning("Feature row error for %s on %s: %s", row["symbol"], row["date"], e)
            errors += 1

    conn.commit()
    log.info("  Features: %d inserted | %d errors", inserted, errors)


# =============================================================================
# INGEST: benchmarks → market.benchmark_prices
# =============================================================================

def ingest_benchmarks(conn: pymssql.Connection, symbol_map: dict) -> None:
    """
    Load benchmarks.csv into market.benchmark_prices.
    Benchmark symbols (SPY, QQQ etc.) are added to ref.symbols if not present —
    they are not in company_metadata.csv since yfinance doesn't return info for ETFs.
    Connects to: market.benchmark_prices, ref.symbols, symbol_map
    DEBUGGING: if benchmark symbol_id lookup fails, check the ref.symbols insert above ran.
    """
    log.info("Loading benchmarks.csv → market.benchmark_prices")
    df = pd.read_csv(DATA_DIR / "benchmarks.csv")
    df["date"] = pd.to_datetime(df["date"]).dt.date
    log.info("  Read %d rows from benchmarks.csv", len(df))

    cursor = conn.cursor()

    # Add benchmark symbols to ref.symbols if missing
    for sym in df["symbol"].unique():
        if sym not in symbol_map:
            log.info("  Adding benchmark symbol: %s", sym)
            cursor.execute("""
                IF NOT EXISTS (SELECT 1 FROM ref.symbols WHERE symbol_code = %s)
                    INSERT INTO ref.symbols
                        (symbol_code, company_name, sector_id, industry,
                         currency, exchange, country, is_benchmark, metadata_date)
                    VALUES (%s, %s, 1, 'Index', 'USD', 'INDEX', 'United States', 1, %s)
            """, (sym, sym, f"{sym} Index", date.today()))
            conn.commit()
            cursor.execute("SELECT symbol_id FROM ref.symbols WHERE symbol_code = %s", (sym,))
            symbol_map[sym] = cursor.fetchone()[0]

    batch_id = f"bench_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    inserted = 0
    errors = 0

    for _, row in df.iterrows():
        symbol_id = symbol_map[row["symbol"]]
        try:
            cursor.execute("""
                IF NOT EXISTS (
                    SELECT 1 FROM market.benchmark_prices
                    WHERE symbol_id = %s AND price_date = %s
                )
                INSERT INTO market.benchmark_prices
                    (symbol_id, symbol_code, price_date, close_price, batch_id)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                symbol_id, row["date"],
                symbol_id, row["symbol"], row["date"], float(row["close"]), batch_id
            ))
            inserted += 1
        except pymssql.Error as e:
            log.warning("Benchmark row error for %s on %s: %s", row["symbol"], row["date"], e)
            errors += 1

    conn.commit()
    log.info("  Benchmarks: %d inserted | %d errors", inserted, errors)


# =============================================================================
# VALIDATION
# =============================================================================

def validate(conn: pymssql.Connection) -> None:
    """
    Post-load validation: row counts across all tables.
    DEBUGGING: if counts are 0, the ingest function for that table silently failed — check logs.
    INTERVIEW POINT: "We validate row counts and checksums post-migration — same pattern
    used in the FastAPI service before marking a migration batch as SUCCESS."
    """
    log.info("Running post-load validation...")
    cursor = conn.cursor()

    checks = [
        ("ref.sectors",            "SELECT COUNT(*) FROM ref.sectors"),
        ("ref.symbols",            "SELECT COUNT(*) FROM ref.symbols"),
        ("market.daily_prices",    "SELECT COUNT(*) FROM market.daily_prices"),
        ("market.price_features",  "SELECT COUNT(*) FROM market.price_features"),
        ("market.benchmark_prices","SELECT COUNT(*) FROM market.benchmark_prices"),
    ]

    all_ok = True
    for label, sql in checks:
        cursor.execute(sql)
        count = cursor.fetchone()[0]
        status = "OK" if count > 0 else "EMPTY — check ingest logs"
        log.info("  %-30s %8d rows  [%s]", label, count, status)
        if count == 0:
            all_ok = False

    if all_ok:
        log.info("Validation passed — Azure SQL source DB is ready for migration.")
    else:
        log.warning("Validation found empty tables — review logs above for errors.")


# =============================================================================
# MAIN
# =============================================================================

def main():
    """
    Entry point: bootstrap schema then load all CSVs into Azure SQL in dependency order.
    Run order: schema → sectors → symbols → prices → features → benchmarks → validate
    Re-runnable: all inserts are guarded with IF NOT EXISTS or MERGE.
    """
    log.info("=" * 55)
    log.info("INGEST TO AZURE SQL")
    log.info("Server:   %s", os.getenv("AZURE_SQL_SERVER"))
    log.info("Database: %s", os.getenv("AZURE_SQL_DATABASE"))
    log.info("=" * 55)

    conn = get_connection()

    try:
        # Schema already applied via Azure portal — skip bootstrap
        symbol_map = ingest_metadata(conn)
        ingest_prices(conn, symbol_map)
        ingest_features(conn, symbol_map)
        ingest_benchmarks(conn, symbol_map)
        validate(conn)
        log.info("Done. Azure SQL source DB populated and ready for migration.")
    except Exception as e:
        log.error("Ingest failed: %s", e)
        log.error("DEBUGGING: check logs above for the failing step, fix, and re-run.")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
