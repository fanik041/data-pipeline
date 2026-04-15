# =============================================================================
# FILE: tests/test_api.py
# What this file does: Pytest integration tests for all 6 FastAPI endpoints.
#                      Uses TestClient + mocked DB layer — no live DB needed.
# Which services: FastAPI test client (httpx), mocked app.db and app.queries
# Tech layer: Testing — validates API response shapes, status codes, error handling
# Project goal: Ensure the API contract (Pydantic models, status codes, JSON
#               error format) is correct before connecting to live Azure SQL / Snowflake.
#
# Run with: .venv/bin/pytest tests/ -v
# =============================================================================

import pytest
from datetime import date
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# ---------------------------------------------------------------------------
# FIXTURES — reusable mock row shapes
# ---------------------------------------------------------------------------

MOCK_SYMBOL = {
    "symbol_code": "AAPL",
    "company_name": "Apple Inc.",
    "sector_name": "Technology",
    "industry": "Consumer Electronics",
    "exchange": "NASDAQ",
    "country": "United States",
}

MOCK_PRICE = {
    "price_date": date(2024, 3, 1),
    "symbol_code": "AAPL",
    "company_name": "Apple Inc.",
    "sector_name": "Technology",
    "open_price": 170.0,
    "high_price": 175.0,
    "low_price": 169.0,
    "close_price": 174.0,
    "volume": 55000000,
    "intraday_range_pct": 3.45,
}

MOCK_PREDICTION = {
    "symbol_code": "AAPL",
    "company_name": "Apple Inc.",
    "sector_name": "Technology",
    "price_date": date(2024, 3, 1),
    "rsi_14": 58.3,
    "macd": 2.1,
    "macd_signal": 1.8,
    "bb_position": 0.72,
    "ma_5": 172.0,
    "ma_20": 168.0,
    "volatility_20d": 0.015,
    "target_next_day_up": 1,
}

MOCK_SECTOR_SYMBOL = {
    "symbol_code": "AAPL",
    "company_name": "Apple Inc.",
    "price_date": date(2024, 3, 1),
    "target_next_day_up": 1,
    "rsi_14": 58.3,
}

MOCK_SUMMARY = {
    "symbol_code": "AAPL",
    "company_name": "Apple Inc.",
    "sector": "Technology",
    "industry": "Consumer Electronics",
    "latest_close": 174.0,
    "latest_date": date(2024, 3, 1),
    "target_next_day_up": 1,
    "rsi_14": 58.3,
    "macd": 2.1,
    "bb_position": 0.72,
}


def _mock_conn():
    """Return a mock DB connection (not used in tests — queries are mocked)."""
    return MagicMock()


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_ok(self):
        """Health endpoint returns 200 with status=ok for azure backend."""
        with patch("app.main.db.get_connection", return_value=_mock_conn()), \
             patch("app.main.queries.ping", return_value=True):
            resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["db_backend"] == "azure"

    def test_health_snowflake(self):
        """Health endpoint accepts ?backend=snowflake."""
        with patch("app.main.db.get_connection", return_value=_mock_conn()), \
             patch("app.main.queries.ping", return_value=True):
            resp = client.get("/health?backend=snowflake")
        assert resp.status_code == 200
        assert resp.json()["db_backend"] == "snowflake"

    def test_health_db_error_returns_503(self):
        """Health endpoint returns 503 when DB connection fails."""
        with patch("app.main.db.get_connection", side_effect=Exception("connection refused")):
            resp = client.get("/health")
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# /symbols
# ---------------------------------------------------------------------------

class TestSymbols:
    def test_returns_symbol_list(self):
        """Symbols endpoint returns a list of SymbolInfo objects."""
        with patch("app.main.db.get_connection", return_value=_mock_conn()), \
             patch("app.main.queries.get_symbols", return_value=[MOCK_SYMBOL]):
            resp = client.get("/symbols")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert body[0]["symbol"] == "AAPL"
        assert body[0]["sector"] == "Technology"

    def test_empty_list_returns_200(self):
        """Symbols endpoint returns empty list (not 404) when DB is empty."""
        with patch("app.main.db.get_connection", return_value=_mock_conn()), \
             patch("app.main.queries.get_symbols", return_value=[]):
            resp = client.get("/symbols")
        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# /prices/{symbol}
# ---------------------------------------------------------------------------

class TestPrices:
    def test_returns_price_list(self):
        """Prices endpoint returns OHLCV rows for a valid symbol."""
        with patch("app.main.db.get_connection", return_value=_mock_conn()), \
             patch("app.main.queries.get_prices", return_value=[MOCK_PRICE]):
            resp = client.get("/prices/AAPL")
        assert resp.status_code == 200
        body = resp.json()
        assert body[0]["close"] == 174.0
        assert body[0]["volume"] == 55000000

    def test_unknown_symbol_returns_404(self):
        """Prices endpoint returns 404 with JSON body for unknown symbol."""
        with patch("app.main.db.get_connection", return_value=_mock_conn()), \
             patch("app.main.queries.get_prices", return_value=[]):
            resp = client.get("/prices/FAKE")
        assert resp.status_code == 404
        body = resp.json()
        # FastAPI wraps HTTPException.detail in a "detail" key
        assert body["detail"]["symbol"] == "FAKE"
        assert "error" in body["detail"]
        assert "trace" in body["detail"]

    def test_lowercase_symbol_normalised(self):
        """Symbol is uppercased automatically — aapl resolves to AAPL."""
        with patch("app.main.db.get_connection", return_value=_mock_conn()), \
             patch("app.main.queries.get_prices", return_value=[MOCK_PRICE]) as mock_q:
            resp = client.get("/prices/aapl")
        assert resp.status_code == 200
        # queries.get_prices should have been called with 'AAPL'
        call_args = mock_q.call_args
        assert call_args[0][2] == "AAPL"  # positional arg: symbol

    def test_date_range_params_accepted(self):
        """?start and ?end params are passed through without error."""
        with patch("app.main.db.get_connection", return_value=_mock_conn()), \
             patch("app.main.queries.get_prices", return_value=[MOCK_PRICE]):
            resp = client.get("/prices/AAPL?start=2024-01-01&end=2024-03-01")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# /predict/{symbol}
# ---------------------------------------------------------------------------

class TestPredict:
    def test_returns_prediction_signal(self):
        """Predict endpoint returns full signal including target_next_day_up."""
        with patch("app.main.db.get_connection", return_value=_mock_conn()), \
             patch("app.main.queries.get_prediction", return_value=MOCK_PREDICTION):
            resp = client.get("/predict/AAPL")
        assert resp.status_code == 200
        body = resp.json()
        assert body["target_next_day_up"] == 1
        assert body["rsi_14"] == 58.3
        assert "macd" in body
        assert "bb_position" in body
        assert "ma_5" in body

    def test_unknown_symbol_returns_404(self):
        """Predict endpoint returns structured 404 for unknown symbol."""
        with patch("app.main.db.get_connection", return_value=_mock_conn()), \
             patch("app.main.queries.get_prediction", return_value=None):
            resp = client.get("/predict/FAKE")
        assert resp.status_code == 404
        detail = resp.json()["detail"]
        assert detail["symbol"] == "FAKE"
        assert "error" in detail
        assert "trace" in detail


# ---------------------------------------------------------------------------
# /sector/{sector}
# ---------------------------------------------------------------------------

class TestSector:
    def test_returns_sector_symbols(self):
        """Sector endpoint returns all symbols in a given sector."""
        with patch("app.main.db.get_connection", return_value=_mock_conn()), \
             patch("app.main.queries.get_sector_symbols", return_value=[MOCK_SECTOR_SYMBOL]):
            resp = client.get("/sector/Technology")
        assert resp.status_code == 200
        body = resp.json()
        assert body[0]["symbol"] == "AAPL"
        assert "target_next_day_up" in body[0]

    def test_unknown_sector_returns_404(self):
        """Sector endpoint returns 404 when sector has no active symbols."""
        with patch("app.main.db.get_connection", return_value=_mock_conn()), \
             patch("app.main.queries.get_sector_symbols", return_value=[]):
            resp = client.get("/sector/FakeSector")
        assert resp.status_code == 404
        detail = resp.json()["detail"]
        assert "sector" in detail
        assert "error" in detail


# ---------------------------------------------------------------------------
# /summary/{symbol}
# ---------------------------------------------------------------------------

class TestSummary:
    def test_returns_summary(self):
        """Summary endpoint combines price and prediction into one response."""
        with patch("app.main.db.get_connection", return_value=_mock_conn()), \
             patch("app.main.queries.get_summary", return_value=MOCK_SUMMARY):
            resp = client.get("/summary/AAPL")
        assert resp.status_code == 200
        body = resp.json()
        assert body["symbol"] == "AAPL"
        assert body["latest_close"] == 174.0
        assert body["target_next_day_up"] == 1

    def test_unknown_symbol_returns_404(self):
        """Summary endpoint returns structured 404 for unknown symbol."""
        with patch("app.main.db.get_connection", return_value=_mock_conn()), \
             patch("app.main.queries.get_summary", return_value=None):
            resp = client.get("/summary/FAKE")
        assert resp.status_code == 404
        detail = resp.json()["detail"]
        assert detail["symbol"] == "FAKE"
