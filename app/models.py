# What this file does: Pydantic response models for all FastAPI endpoints
# Which services: consumed by main.py, shapes JSON responses
# Tech layer: API — defines the contract between backend and any frontend/client
# Project goal: same models work regardless of DB_BACKEND (azure or snowflake)

from pydantic import BaseModel
from typing import Optional
from datetime import date


class HealthResponse(BaseModel):
    status: str
    db_backend: str


class SymbolInfo(BaseModel):
    symbol: str
    company_name: str
    sector: str
    industry: str
    exchange: str
    country: str


class PricePoint(BaseModel):
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int


class PredictionSignal(BaseModel):
    symbol: str
    date: date
    rsi_14: Optional[float]
    macd: float
    macd_signal: float
    bb_position: Optional[float]
    ma_5: Optional[float]
    ma_20: Optional[float]
    volatility_20d: Optional[float]
    target_next_day_up: int  # 1 = predicted up, 0 = predicted down


class SectorSymbol(BaseModel):
    symbol: str
    company_name: str
    date: date
    target_next_day_up: int
    rsi_14: Optional[float]


class SummaryResponse(BaseModel):
    symbol: str
    company_name: str
    sector: str
    industry: str
    latest_close: float
    latest_date: date
    target_next_day_up: int
    rsi_14: Optional[float]
    macd: float
    bb_position: Optional[float]
