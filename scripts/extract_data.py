"""
File: scripts/extract_data.py
Layer: Data ingestion (entry point — runs before anything else)
Connects to: yfinance (public API, no key needed)
Goal: Pull real capital markets data for 20 symbols, save to structured CSVs.
      Output feeds both Part 1 (Azure SQL source) and Part 2 (Snowflake source).
Ref: docs/interview-prep/TRUTH_SOURCE.md — "data-first architecture"
"""

import yfinance as yf
import pandas as pd
from pathlib import Path
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "raw"
START_DATE = "2022-01-01"
END_DATE   = "2024-12-31"   # ~3 years = ~750 trading days per symbol

# OTPP-relevant symbols: large-cap equities + financial sector (mirrors CMIA holdings universe)
TECH_SYMBOLS = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "CRM", "ORCL", "ADBE"]
FIN_SYMBOLS  = ["JPM", "GS", "MS", "BLK", "BAC", "C", "WFC", "SCHW", "CME", "ICE"]
INDEX_SYMBOLS = ["SPY", "QQQ", "IEF", "GLD", "TLT"]  # benchmarks for predictor features

ALL_SYMBOLS = TECH_SYMBOLS + FIN_SYMBOLS
# ──────────────────────────────────────────────────────────────────────────────


def download_prices(symbols: list[str], start: str, end: str) -> pd.DataFrame:
    """Download daily OHLCV for all symbols from yfinance, return flat DataFrame."""
    print(f"\n[extract] Downloading {len(symbols)} symbols from {start} to {end}...")

    # group_by="ticker" returns MultiIndex — we flatten it below
    raw = yf.download(symbols, start=start, end=end, group_by="ticker",
                      auto_adjust=True, threads=True)  # auto_adjust = split/dividend adjusted

    frames = []
    for sym in symbols:
        try:
            df = raw[sym].copy()           # slice one symbol's OHLCV block
            df = df.dropna(subset=["Close"])
            df.index.name = "date"
            df = df.reset_index()
            df.columns = [c.lower().replace(" ", "_") for c in df.columns]
            df.insert(0, "symbol", sym)    # prepend symbol column for flat table structure
            frames.append(df)
            print(f"  {sym}: {len(df)} rows")
        except Exception as e:
            print(f"  {sym}: SKIP — {e}")

    combined = pd.concat(frames, ignore_index=True)
    combined["date"] = pd.to_datetime(combined["date"]).dt.date   # strip time, keep date only
    return combined


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute technical indicator features per symbol — used as predictor inputs.
    Connects to: prices DataFrame from download_prices()
    """
    print("\n[features] Computing technical indicators per symbol...")
    result_frames = []

    for sym, grp in df.groupby("symbol"):
        grp = grp.sort_values("date").copy()

        # Daily return — percentage change close to close
        grp["daily_return"]   = grp["close"].pct_change()

        # Moving averages — trend features
        grp["ma_5"]  = grp["close"].rolling(5).mean()    # 1-week MA
        grp["ma_20"] = grp["close"].rolling(20).mean()   # 1-month MA
        grp["ma_50"] = grp["close"].rolling(50).mean()   # 1-quarter MA

        # Volatility — 20-day rolling std of returns (annualised)
        grp["volatility_20d"] = grp["daily_return"].rolling(20).std() * (252 ** 0.5)

        # RSI (14-day) — momentum oscillator, 0-100 scale
        delta = grp["close"].diff()
        gain  = delta.clip(lower=0).rolling(14).mean()   # avg gain over 14 days
        loss  = (-delta.clip(upper=0)).rolling(14).mean() # avg loss over 14 days
        grp["rsi_14"] = 100 - (100 / (1 + gain / loss.replace(0, 1e-9)))  # avoid div/0

        # MACD — difference between 12-day and 26-day EMA (trend momentum)
        ema12 = grp["close"].ewm(span=12, adjust=False).mean()
        ema26 = grp["close"].ewm(span=26, adjust=False).mean()
        grp["macd"]        = ema12 - ema26
        grp["macd_signal"] = grp["macd"].ewm(span=9, adjust=False).mean()  # signal line

        # Bollinger Bands — price relative to rolling mean ± 2 std
        bb_mid             = grp["close"].rolling(20).mean()
        bb_std             = grp["close"].rolling(20).std()
        grp["bb_upper"]    = bb_mid + 2 * bb_std
        grp["bb_lower"]    = bb_mid - 2 * bb_std
        grp["bb_position"] = (grp["close"] - grp["bb_lower"]) / (grp["bb_upper"] - grp["bb_lower"] + 1e-9)

        # Target label for predictor — did close go up next day? (1 = yes, 0 = no)
        grp["target_next_day_up"] = (grp["close"].shift(-1) > grp["close"]).astype(int)

        result_frames.append(grp)

    out = pd.concat(result_frames, ignore_index=True)
    print(f"  Features computed. Shape: {out.shape}")
    return out


def download_benchmarks(symbols: list[str], start: str, end: str) -> pd.DataFrame:
    """Download index/benchmark prices — used as market context features in predictor."""
    print(f"\n[benchmarks] Downloading {len(symbols)} benchmark symbols...")
    raw = yf.download(symbols, start=start, end=end, group_by="ticker",
                      auto_adjust=True, threads=True)
    frames = []
    for sym in symbols:
        try:
            df = raw[sym][["Close"]].copy()
            df.index.name = "date"
            df = df.reset_index()
            df.columns = ["date", "close"]
            df["symbol"] = sym
            df["date"] = pd.to_datetime(df["date"]).dt.date
            df = df.dropna()
            frames.append(df)
            print(f"  {sym}: {len(df)} rows")
        except Exception as e:
            print(f"  {sym}: SKIP — {e}")
    return pd.concat(frames, ignore_index=True)


def build_company_metadata() -> pd.DataFrame:
    """
    Fetch company info (sector, industry, market cap) from yfinance for each symbol.
    Used as DIM_SYMBOL in Snowflake star schema.
    """
    print("\n[metadata] Fetching company info...")
    rows = []
    for sym in ALL_SYMBOLS:
        try:
            info = yf.Ticker(sym).info
            rows.append({
                "symbol":        sym,
                "company_name":  info.get("longName", ""),
                "sector":        info.get("sector", ""),
                "industry":      info.get("industry", ""),
                "market_cap":    info.get("marketCap", None),
                "currency":      info.get("currency", "USD"),
                "exchange":      info.get("exchange", ""),
                "country":       info.get("country", ""),
                "as_of_date":    datetime.today().date(),
            })
            print(f"  {sym}: {info.get('longName','?')} | {info.get('sector','?')}")
        except Exception as e:
            print(f"  {sym}: SKIP — {e}")
    return pd.DataFrame(rows)


def save(df: pd.DataFrame, filename: str) -> None:
    """Save DataFrame to CSV in OUTPUT_DIR, print row count and file size."""
    path = OUTPUT_DIR / filename
    df.to_csv(path, index=False)
    size_kb = path.stat().st_size / 1024
    print(f"  Saved: {filename} — {len(df):,} rows, {size_kb:.1f} KB")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {OUTPUT_DIR}")

    # 1. Raw prices — all 20 equity symbols, 3 years
    prices_raw = download_prices(ALL_SYMBOLS, START_DATE, END_DATE)
    save(prices_raw, "prices_raw.csv")

    # 2. Prices + technical features — main predictor input table
    prices_features = add_features(prices_raw)
    save(prices_features, "prices_features.csv")

    # 3. Benchmark / index prices — market context for predictor
    benchmarks = download_benchmarks(INDEX_SYMBOLS, START_DATE, END_DATE)
    save(benchmarks, "benchmarks.csv")

    # 4. Company metadata — dimension table for Snowflake star schema
    metadata = build_company_metadata()
    save(metadata, "company_metadata.csv")

    # ── Summary ───────────────────────────────────────────────────────────────
    total_rows = len(prices_raw) + len(benchmarks) + len(metadata)
    print(f"\n{'─'*50}")
    print(f"EXTRACTION COMPLETE")
    print(f"{'─'*50}")
    print(f"  prices_raw.csv      {len(prices_raw):>7,} rows  — OHLCV for 20 symbols")
    print(f"  prices_features.csv {len(prices_features):>7,} rows  — OHLCV + 10 technical indicators")
    print(f"  benchmarks.csv      {len(benchmarks):>7,} rows  — SPY, QQQ, IEF, GLD, TLT")
    print(f"  company_metadata.csv {len(metadata):>6,} rows  — sector, industry, market cap")
    print(f"  {'─'*40}")
    print(f"  Total (excl features): {total_rows:,} rows")
    print(f"\nData range: {START_DATE} → {END_DATE}")
    print(f"Symbols:    {ALL_SYMBOLS}")
    print(f"\nNext: push prices_raw.csv → Azure SQL (Part 1 source)")
    print(f"      push prices_features.csv → Snowflake (Part 2 source)")
    print(f"{'─'*50}\n")


if __name__ == "__main__":
    main()
