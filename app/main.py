# =============================================================================
# FILE: app/main.py
# What this file does: FastAPI application — 6 endpoints for market data and
#                      ML prediction signals, queryable against Azure SQL or Snowflake.
# Which services: Azure SQL (OLTP source), Snowflake (OLAP target via queries.py)
# Tech layer: API — entry point for all client requests (React UI, curl, tests)
# Project goal: Same API compares OLTP vs OLAP query performance; demonstrates
#               migration payoff — Snowflake responses should be faster at scale.
#               Ref: docs/interview-prep/TRUTH_SOURCE.md
#
# INTERVIEW POINT: "The ?backend query param lets us hit both DBs with the same
#   request — no config restart needed. We log query latency server-side so we
#   can compare OLTP vs OLAP response times and tell the migration payoff story."
#
# Usage:
#   .venv/bin/uvicorn app.main:app --reload
#   curl "http://localhost:8000/prices/AAPL?backend=azure"
#   curl "http://localhost:8000/prices/AAPL?backend=snowflake"
# =============================================================================

import base64
import logging
import os
import time
from datetime import date
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from app import db, queries
from app.models import (
    HealthResponse,
    LoginRequest,
    LoginResponse,
    PredictionSignal,
    PricePoint,
    SectorSymbol,
    SummaryResponse,
    SymbolInfo,
)

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

app = FastAPI(
    title="CMIA Market Data API",
    description=(
        "Market data and ML prediction signals. "
        "Use ?backend=azure (OLTP) or ?backend=snowflake (OLAP) "
        "to compare query performance pre- and post-migration."
    ),
    version="1.0.0",
)

# CORS — open for demo; tighten origin list for production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],   # must include POST for /auth/login
    allow_headers=["*"],
    allow_credentials=True,
)

Backend = Literal["azure", "snowflake"]

# ---------------------------------------------------------------------------
# HELPER
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------

@app.post("/auth/login", response_model=LoginResponse, tags=["auth"])
def login(body: LoginRequest):
    """
    Validate credentials against Azure SQL env vars and return a bearer token.
    Token is base64(username:timestamp) — stateless, sufficient for demo auth.
    INTERVIEW POINT: credentials reuse the DB auth, so RLS roles apply automatically.
    """
    expected_user = os.getenv("AZURE_SQL_USERNAME", "")
    expected_pass = os.getenv("AZURE_SQL_PASSWORD", "")
    if body.username != expected_user or body.password != expected_pass:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "Invalid credentials",
                "trace": "Username or password does not match Azure SQL credentials in .env",
            },
        )
    token = base64.b64encode(f"{body.username}:{int(time.time())}".encode()).decode()
    log.info("Login: user '%s' authenticated", body.username)
    return LoginResponse(access_token=token, token_type="bearer", username=body.username)


# ---------------------------------------------------------------------------
# HELPER
# ---------------------------------------------------------------------------

def _not_found(symbol: str, detail: str) -> HTTPException:
    """Build a 404 HTTPException with structured JSON body — symbol + human-readable trace."""
    return HTTPException(
        status_code=404,
        detail={
            "symbol": symbol.upper(),
            "error": "Symbol not found",
            "trace": detail,
        },
    )


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse, tags=["infra"])
def health(backend: Backend = Query(default="azure", description="DB backend to ping")):
    """
    Ping the selected DB backend and return status.
    Used by Kubernetes liveness probe and uptime monitors.
    """
    t0 = time.perf_counter()
    try:
        conn = db.get_connection(backend)
        ok = queries.ping(conn, backend)
        conn.close()
    except Exception as exc:
        log.error("Health check failed [%s]: %s", backend, exc)
        raise HTTPException(status_code=503, detail={"status": "error", "db_backend": backend, "trace": str(exc)})
    elapsed_ms = (time.perf_counter() - t0) * 1000
    log.info("GET /health [%s]: %.1f ms — %s", backend, elapsed_ms, "ok" if ok else "fail")
    return HealthResponse(status="ok" if ok else "degraded", db_backend=backend)


# ---------------------------------------------------------------------------
# GET /symbols
# ---------------------------------------------------------------------------

@app.get("/symbols", response_model=list[SymbolInfo], tags=["market-data"])
def list_symbols(backend: Backend = Query(default="azure")):
    """
    Return all active equity symbols with sector and industry metadata.
    Excludes benchmark ETFs (SPY, QQQ, etc.).
    """
    t0 = time.perf_counter()
    conn = db.get_connection(backend)
    rows = queries.get_symbols(conn, backend)
    conn.close()
    elapsed_ms = (time.perf_counter() - t0) * 1000
    log.info("GET /symbols [%s]: %.1f ms — %d symbols", backend, elapsed_ms, len(rows))

    return [
        SymbolInfo(
            symbol=r["symbol_code"],
            company_name=r["company_name"],
            sector=r["sector_name"],
            industry=r["industry"],
            exchange=r["exchange"],
            country=r["country"],
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# GET /prices/{symbol}
# ---------------------------------------------------------------------------

@app.get("/prices/{symbol}", response_model=list[PricePoint], tags=["market-data"])
def get_prices(
    symbol: str,
    backend: Backend = Query(default="azure"),
    start: Optional[date] = Query(default=None, description="Start date (YYYY-MM-DD). Defaults to 14 days ago."),
    end:   Optional[date] = Query(default=None, description="End date (YYYY-MM-DD). Defaults to today."),
):
    """
    Return OHLCV price history for a symbol.
    Defaults to the last 14 calendar days. Override with ?start and ?end.
    """
    symbol = symbol.upper()  # normalise at the API boundary — query layer receives clean input
    t0 = time.perf_counter()
    conn = db.get_connection(backend)
    rows = queries.get_prices(conn, backend, symbol, start, end)
    conn.close()
    elapsed_ms = (time.perf_counter() - t0) * 1000
    log.info("GET /prices/%s [%s]: %.1f ms — %d rows", symbol.upper(), backend, elapsed_ms, len(rows))

    if not rows:
        raise _not_found(symbol, f"No price data for '{symbol.upper()}' in the requested date range.")

    return [
        PricePoint(
            date=r["price_date"],
            open=r["open_price"],
            high=r["high_price"],
            low=r["low_price"],
            close=r["close_price"],
            volume=int(r["volume"]),
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# GET /predict/{symbol}
# ---------------------------------------------------------------------------

@app.get("/predict/{symbol}", response_model=PredictionSignal, tags=["predictions"])
def predict(
    symbol: str,
    backend: Backend = Query(default="azure"),
):
    """
    Return the latest ML prediction signal for a symbol.
    Includes RSI, MACD, Bollinger Band position, moving averages, volatility,
    and the binary next-day direction label (1 = up, 0 = down).
    """
    symbol = symbol.upper()
    t0 = time.perf_counter()
    conn = db.get_connection(backend)
    row = queries.get_prediction(conn, backend, symbol)
    conn.close()
    elapsed_ms = (time.perf_counter() - t0) * 1000
    log.info("GET /predict/%s [%s]: %.1f ms", symbol.upper(), backend, elapsed_ms)

    if row is None:
        raise _not_found(symbol, f"No feature data found for symbol '{symbol.upper()}'.")

    return PredictionSignal(
        symbol=row["symbol_code"],
        date=row["price_date"],
        rsi_14=row.get("rsi_14"),
        macd=row["macd"],
        macd_signal=row["macd_signal"],
        bb_position=row.get("bb_position"),
        ma_5=row.get("ma_5"),
        ma_20=row.get("ma_20"),
        volatility_20d=row.get("volatility_20d"),
        target_next_day_up=int(row["target_next_day_up"]),
    )


# ---------------------------------------------------------------------------
# GET /sector/{sector}
# ---------------------------------------------------------------------------

@app.get("/sector/{sector}", response_model=list[SectorSymbol], tags=["market-data"])
def get_sector(
    sector: str,
    backend: Backend = Query(default="azure"),
):
    """
    Return the latest prediction signal for every symbol in the given sector.
    Sector name is case-insensitive (e.g. 'technology' or 'Technology').
    Returns 404 if the sector is not found or has no active symbols.
    """
    t0 = time.perf_counter()
    conn = db.get_connection(backend)
    rows = queries.get_sector_symbols(conn, backend, sector)
    conn.close()
    elapsed_ms = (time.perf_counter() - t0) * 1000
    log.info("GET /sector/%s [%s]: %.1f ms — %d symbols", sector, backend, elapsed_ms, len(rows))

    if not rows:
        raise HTTPException(
            status_code=404,
            detail={
                "sector": sector,
                "error": "Sector not found or has no active symbols",
                "trace": f"No feature rows matched sector '{sector}' in {backend} DB.",
            },
        )

    return [
        SectorSymbol(
            symbol=r["symbol_code"],
            company_name=r["company_name"],
            date=r["price_date"],
            target_next_day_up=int(r["target_next_day_up"]),
            rsi_14=r.get("rsi_14"),
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# GET /summary/{symbol}
# ---------------------------------------------------------------------------

@app.get("/summary/{symbol}", response_model=SummaryResponse, tags=["market-data"])
def get_summary(
    symbol: str,
    backend: Backend = Query(default="azure"),
):
    """
    Return a combined summary: latest close price + ML signal for one symbol.
    Designed as the primary endpoint for a stock detail view in the UI.
    """
    symbol = symbol.upper()
    t0 = time.perf_counter()
    conn = db.get_connection(backend)
    row = queries.get_summary(conn, backend, symbol)
    conn.close()
    elapsed_ms = (time.perf_counter() - t0) * 1000
    log.info("GET /summary/%s [%s]: %.1f ms", symbol.upper(), backend, elapsed_ms)

    if row is None:
        raise _not_found(symbol, f"No summary data found for '{symbol.upper()}'.")

    return SummaryResponse(
        symbol=row["symbol_code"],
        company_name=row["company_name"],
        sector=row["sector"],
        industry=row["industry"],
        latest_close=float(row["latest_close"]),
        latest_date=row["latest_date"],
        target_next_day_up=int(row["target_next_day_up"]),
        rsi_14=row.get("rsi_14"),
        macd=float(row["macd"]),
        bb_position=row.get("bb_position"),
    )
