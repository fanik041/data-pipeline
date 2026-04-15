# =============================================================================
# FILE: app/queries.py
# What this file does: Backend-aware SQL query functions — same logical query,
#                      different SQL depending on Azure SQL vs Snowflake schema.
# Which services: Azure SQL (reports.v_* views), Snowflake (CMIA_DW.MARTS.V_*)
# Tech layer: API query layer — sits between FastAPI routes and the DB connection
# Project goal: Lets FastAPI compare OLTP (Azure SQL) vs OLAP (Snowflake) response
#               times using identical query logic — the migration payoff story.
#
# INTERVIEW POINT: "Azure SQL views use lowercase snake_case columns; Snowflake
#   returns uppercase. We normalise to lowercase in _fetch() so the route layer
#   is DB-agnostic — the same Pydantic model works for both backends."
# =============================================================================

import time
import logging
from datetime import date, timedelta
from typing import Optional

import snowflake.connector
from app.db import is_snowflake

log = logging.getLogger(__name__)


# =============================================================================
# INTERNAL: row fetcher — normalises column names to lowercase for both backends
# =============================================================================

def _fetch(conn, sql: str, params: tuple = ()) -> list[dict]:
    """
    Execute SQL and return rows as list of lowercase-keyed dicts.
    Handles pymssql (as_dict cursor) and Snowflake (DictCursor + lowercase).
    DEBUGGING: if rows come back empty, check SQL and params — not the connection.
    """
    t0 = time.perf_counter()
    if is_snowflake(conn):
        # DictCursor returns uppercase keys — normalise to lowercase
        cur = conn.cursor(snowflake.connector.DictCursor)
        cur.execute(sql, params)
        rows = [{k.lower(): v for k, v in row.items()} for row in cur.fetchall()]
    else:
        # pymssql with as_dict=True returns lowercase keys matching the view/table column names
        cur = conn.cursor(as_dict=True)
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
    elapsed_ms = (time.perf_counter() - t0) * 1000
    log.info("Query [%.1f ms]: %d rows returned", elapsed_ms, len(rows))
    return rows


# =============================================================================
# HEALTH — simple connectivity ping
# =============================================================================

def ping(conn, backend: str) -> bool:
    """Execute a trivial SELECT to verify DB connectivity; returns True on success."""
    rows = _fetch(conn, "SELECT 1 AS ok")
    return bool(rows)


# =============================================================================
# /symbols — all active non-benchmark tickers with sector info
# =============================================================================

def get_symbols(conn, backend: str) -> list[dict]:
    """
    Query all active equity symbols with sector/industry metadata.
    Azure SQL: ref.symbols + ref.sectors. Snowflake: DIM_SYMBOL + DIM_SECTOR.
    Returns: list of dicts with keys symbol_code, company_name, sector_name,
             industry, exchange, country.
    """
    if backend == "azure":
        sql = """
            SELECT
                s.symbol_code,
                s.company_name,
                sec.sector_name,
                s.industry,
                s.exchange,
                s.country
            FROM ref.symbols s
            JOIN ref.sectors sec ON s.sector_id = sec.sector_id
            WHERE s.is_active = 1 AND s.is_benchmark = 0
            ORDER BY s.symbol_code
        """
        return _fetch(conn, sql)
    else:
        sql = """
            SELECT
                s.SYMBOL_CODE,
                s.COMPANY_NAME,
                sec.SECTOR_NAME,
                s.INDUSTRY,
                s.EXCHANGE,
                s.COUNTRY
            FROM CMIA_DW.MARTS.DIM_SYMBOL s
            JOIN CMIA_DW.MARTS.DIM_SECTOR sec ON s.SECTOR_KEY = sec.SECTOR_KEY
            WHERE s.IS_ACTIVE = TRUE AND s.IS_BENCHMARK = FALSE
            ORDER BY s.SYMBOL_CODE
        """
        return _fetch(conn, sql)


# =============================================================================
# /prices/{symbol} — OHLCV history with optional date range
# =============================================================================

def get_prices(
    conn, backend: str, symbol: str,
    start: Optional[date], end: Optional[date]
) -> list[dict]:
    """
    Query OHLCV price rows for a symbol, defaulting to the last 14 calendar days.
    Azure SQL: reports.v_daily_prices_enriched. Snowflake: V_PRICES_ENRICHED.
    Returns: list of dicts with normalised column names (volume not volume_qty).
    """
    end = end or date.today()
    start = start or (end - timedelta(days=14))

    if backend == "azure":
        sql = """
            SELECT
                price_date,
                symbol_code,
                company_name,
                sector_name,
                open_price,
                high_price,
                low_price,
                close_price,
                volume,
                intraday_range_pct
            FROM reports.v_daily_prices_enriched
            WHERE symbol_code = %s
              AND price_date BETWEEN %s AND %s
            ORDER BY price_date DESC
        """
        return _fetch(conn, sql, (symbol.upper(), start, end))
    else:
        # VOLUME_QTY aliased to VOLUME so normalised keys are identical to Azure SQL
        sql = """
            SELECT
                PRICE_DATE,
                SYMBOL_CODE,
                COMPANY_NAME,
                SECTOR_NAME,
                OPEN_PRICE,
                HIGH_PRICE,
                LOW_PRICE,
                CLOSE_PRICE,
                VOLUME_QTY AS VOLUME,
                INTRADAY_RANGE_PCT
            FROM CMIA_DW.MARTS.V_PRICES_ENRICHED
            WHERE SYMBOL_CODE = %s
              AND PRICE_DATE BETWEEN %s AND %s
            ORDER BY PRICE_DATE DESC
        """
        return _fetch(conn, sql, (symbol.upper(), start, end))


# =============================================================================
# /predict/{symbol} — latest ML signal (features + prediction label)
# =============================================================================

def get_prediction(conn, backend: str, symbol: str) -> Optional[dict]:
    """
    Query the most recent feature row for a symbol including the ML target label.
    Azure SQL: reports.v_latest_features. Snowflake: V_LATEST_FEATURES.
    Returns: single dict or None if symbol not found.
    """
    if backend == "azure":
        sql = """
            SELECT
                symbol_code,
                company_name,
                sector_name,
                price_date,
                rsi_14,
                macd,
                macd_signal,
                bb_position,
                ma_5,
                ma_20,
                volatility_20d,
                target_next_day_up
            FROM reports.v_latest_features
            WHERE symbol_code = %s
        """
    else:
        sql = """
            SELECT
                SYMBOL_CODE,
                COMPANY_NAME,
                SECTOR_NAME,
                PRICE_DATE,
                RSI_14,
                MACD,
                MACD_SIGNAL,
                BB_POSITION,
                MA_5,
                MA_20,
                VOLATILITY_20D,
                TARGET_NEXT_DAY_UP
            FROM CMIA_DW.MARTS.V_LATEST_FEATURES
            WHERE SYMBOL_CODE = %s
        """
    rows = _fetch(conn, sql, (symbol.upper(),))
    return rows[0] if rows else None


# =============================================================================
# /sector/{sector} — latest prediction for all symbols in a sector
# =============================================================================

def get_sector_symbols(conn, backend: str, sector: str) -> list[dict]:
    """
    Query the latest prediction row for every symbol in the given sector.
    Case-insensitive sector match. Returns empty list if sector not found.
    """
    if backend == "azure":
        sql = """
            SELECT symbol_code, company_name, price_date, target_next_day_up, rsi_14
            FROM reports.v_latest_features
            WHERE LOWER(sector_name) = LOWER(%s)
            ORDER BY symbol_code
        """
    else:
        sql = """
            SELECT SYMBOL_CODE, COMPANY_NAME, PRICE_DATE, TARGET_NEXT_DAY_UP, RSI_14
            FROM CMIA_DW.MARTS.V_LATEST_FEATURES
            WHERE LOWER(SECTOR_NAME) = LOWER(%s)
            ORDER BY SYMBOL_CODE
        """
    return _fetch(conn, sql, (sector,))


# =============================================================================
# /summary/{symbol} — combined latest price + prediction in one response
# =============================================================================

def get_summary(conn, backend: str, symbol: str) -> Optional[dict]:
    """
    Combine latest close price and ML signal into one summary row per symbol.
    Joins v_latest_features to the prices table/view on (symbol, date).
    Returns: single dict or None if symbol not found.
    """
    if backend == "azure":
        sql = """
            SELECT
                f.symbol_code,
                f.company_name,
                f.sector_name  AS sector,
                s.industry,
                p.close_price  AS latest_close,
                f.price_date   AS latest_date,
                f.target_next_day_up,
                f.rsi_14,
                f.macd,
                f.bb_position
            FROM reports.v_latest_features f
            JOIN ref.symbols s
              ON s.symbol_code = f.symbol_code
             AND s.is_active   = 1
            JOIN market.daily_prices p
              ON p.symbol_code = f.symbol_code
             AND p.price_date  = f.price_date
             AND p.is_active   = 1
            WHERE f.symbol_code = %s
        """
    else:
        sql = """
            SELECT
                f.SYMBOL_CODE,
                f.COMPANY_NAME,
                f.SECTOR_NAME  AS SECTOR,
                s.INDUSTRY,
                p.CLOSE_PRICE  AS LATEST_CLOSE,
                f.PRICE_DATE   AS LATEST_DATE,
                f.TARGET_NEXT_DAY_UP,
                f.RSI_14,
                f.MACD,
                f.BB_POSITION
            FROM CMIA_DW.MARTS.V_LATEST_FEATURES f
            JOIN CMIA_DW.MARTS.DIM_SYMBOL s
              ON s.SYMBOL_CODE = f.SYMBOL_CODE
             AND s.IS_ACTIVE   = TRUE
            JOIN CMIA_DW.MARTS.V_PRICES_ENRICHED p
              ON p.SYMBOL_CODE = f.SYMBOL_CODE
             AND p.PRICE_DATE  = f.PRICE_DATE
            WHERE f.SYMBOL_CODE = %s
        """
    rows = _fetch(conn, sql, (symbol.upper(),))
    return rows[0] if rows else None
