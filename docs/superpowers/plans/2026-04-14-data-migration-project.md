# Data Migration Project — FastAPI/AKS + Flask/EKS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build two production-style data migration apps (investment positions data: SQLite → PostgreSQL) — Part 1 using FastAPI deployed to AKS, Part 2 using Flask deployed to EKS — each containing intentional bugs to debug, a migration script with validation + rollback, and full Docker + Kubernetes deployment.

**Architecture:** Each part is self-contained: a Python API serves endpoints for positions/trades data, a migration module moves data from SQLite (legacy source) to PostgreSQL (cloud target) with row-count + checksum validation and rollback on failure, and a Dockerfile + K8s manifests handle deployment. Docker Compose handles local dev; K8s manifests are ready for AKS (Part 1) and EKS (Part 2).

**Tech Stack:** Python 3.14, FastAPI + Uvicorn (Part 1), Flask (Part 2), SQLAlchemy 2.x, SQLite (source), PostgreSQL (target via Docker), Pytest + httpx, Docker, Docker Compose, Kubernetes (kubectl), Azure CLI + AKS (Part 1), AWS CLI + EKS (Part 2).

**Why this matters for OTPP interview:** Every bug, migration concept, and deployment step directly maps to what Mark Segal (cloud/migration) and Cindy Tam (clean code/debugging) will probe: column mismatches, transaction rollback, data validation, container deployment, K8s fundamentals.

---

## PART 1: FastAPI + AKS (~2 hours)

### Repo layout for Part 1

```
part1-fastapi-aks/
├── app/
│   ├── main.py              # FastAPI app, middleware, lifespan
│   ├── database.py          # SQLAlchemy engine + session
│   ├── models.py            # ORM models: Position, Trade
│   └── routers/
│       ├── positions.py     # BUG 1 + BUG 2 live here
│       └── trades.py        # BUG 3 (off-by-one pagination)
├── migration/
│   ├── seed.py              # Populates SQLite source DB
│   ├── migrate.py           # SQLite → PostgreSQL with BUG 4
│   └── validate.py          # Row count + checksum validation
├── tests/
│   ├── test_positions.py
│   ├── test_trades.py
│   └── test_migration.py
├── k8s/
│   ├── namespace.yaml
│   ├── configmap.yaml
│   ├── deployment.yaml
│   └── service.yaml
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

### Task 1.0: Bootstrap

**Files:**
- Create: `part1-fastapi-aks/requirements.txt`
- Create: `part1-fastapi-aks/docker-compose.yml`

- [ ] **Step 1: Create requirements.txt**

```
fastapi==0.111.0
uvicorn[standard]==0.29.0
sqlalchemy==2.0.30
psycopg2-binary==2.9.9
pytest==8.2.0
httpx==0.27.0
pytest-anyio==0.0.0
anyio==4.3.0
```

- [ ] **Step 2: Create docker-compose.yml**

```yaml
version: "3.9"
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: cmia
      POSTGRES_PASSWORD: cmia_pass
      POSTGRES_DB: positions_db
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U cmia -d positions_db"]
      interval: 5s
      retries: 10

  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://cmia:cmia_pass@postgres:5432/positions_db
    depends_on:
      postgres:
        condition: service_healthy
```

- [ ] **Step 3: Install packages**

```bash
cd part1-fastapi-aks
pip3 install -r requirements.txt
```

Expected: All packages install without errors.

- [ ] **Step 4: Start PostgreSQL only**

```bash
docker compose up postgres -d
```

Expected: Container starts; `docker compose ps` shows postgres as healthy.

- [ ] **Step 5: Commit**

```bash
git add part1-fastapi-aks/requirements.txt part1-fastapi-aks/docker-compose.yml
git commit -m "feat: part1 bootstrap — requirements and docker-compose"
```

---

### Task 1.1: SQLAlchemy models

**Files:**
- Create: `part1-fastapi-aks/app/database.py`
- Create: `part1-fastapi-aks/app/models.py`

- [ ] **Step 1: Write failing test**

```python
# part1-fastapi-aks/tests/test_positions.py
import os, pytest
from sqlalchemy import create_engine, text

DB_URL = os.getenv("DATABASE_URL", "postgresql://cmia:cmia_pass@localhost:5432/positions_db")

def test_tables_created():
    from app.database import engine
    from app import models  # triggers create_all
    with engine.connect() as conn:
        result = conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))
        tables = {row[0] for row in result}
    assert "positions" in tables
    assert "trades" in tables
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd part1-fastapi-aks
DATABASE_URL=postgresql://cmia:cmia_pass@localhost:5432/positions_db pytest tests/test_positions.py::test_tables_created -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app'`

- [ ] **Step 3: Create database.py**

```python
# part1-fastapi-aks/app/database.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://cmia:cmia_pass@localhost:5432/positions_db")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 4: Create models.py**

```python
# part1-fastapi-aks/app/models.py
from sqlalchemy import Column, Integer, String, Float, Date, DateTime, func
from app.database import Base, engine


class Position(Base):
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(10), nullable=False, index=True)
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    market_value = Column(Float, nullable=False)   # NOTE: column is market_value
    as_of_date = Column(Date, nullable=False)


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(10), nullable=False, index=True)
    side = Column(String(4), nullable=False)        # BUY or SELL
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    traded_at = Column(DateTime, server_default=func.now())


# Create tables on import (fine for this exercise)
Base.metadata.create_all(bind=engine)
```

- [ ] **Step 5: Create `app/__init__.py`**

```python
# part1-fastapi-aks/app/__init__.py
```

- [ ] **Step 6: Run test to verify it passes**

```bash
DATABASE_URL=postgresql://cmia:cmia_pass@localhost:5432/positions_db pytest tests/test_positions.py::test_tables_created -v
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add part1-fastapi-aks/app/
git commit -m "feat: part1 SQLAlchemy models — positions and trades tables"
```

---

### Task 1.2: FastAPI app with intentional bugs (read carefully — bugs are deliberate)

This task builds the API with 3 intentional bugs for you to debug later. **Do not fix them now.** After this task you will debug them one by one.

**Bugs planted:**
- **BUG 1** (`positions.py`): query returns `mkt_val` alias but Pydantic schema expects `market_value` → 422 on response serialization
- **BUG 2** (`positions.py`): null check missing — positions with `quantity=None` crash with `TypeError`
- **BUG 3** (`trades.py`): pagination offset uses `page * size` instead of `(page - 1) * size` → page 1 skips first N rows

**Files:**
- Create: `part1-fastapi-aks/app/routers/positions.py`
- Create: `part1-fastapi-aks/app/routers/trades.py`
- Create: `part1-fastapi-aks/app/main.py`

- [ ] **Step 1: Write failing tests (these FAIL because of the bugs)**

```python
# part1-fastapi-aks/tests/test_positions.py  (add to existing file)
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app import models
import datetime

client = TestClient(app)


def _insert_position(symbol="AAPL", quantity=100.0, price=175.0):
    db = SessionLocal()
    pos = models.Position(
        symbol=symbol,
        quantity=quantity,
        price=price,
        market_value=round(quantity * price, 2),
        as_of_date=datetime.date.today(),
    )
    db.add(pos)
    db.commit()
    db.refresh(pos)
    db.close()
    return pos


def test_get_positions_returns_market_value():
    _insert_position()
    r = client.get("/api/positions")
    assert r.status_code == 200
    data = r.json()
    assert len(data) > 0
    assert "market_value" in data[0]          # BUG 1 will make this fail


def test_positions_with_null_quantity():
    # insert a row with quantity=None to simulate bad source data
    db = SessionLocal()
    pos = models.Position(
        symbol="BAD", quantity=None, price=10.0, market_value=0.0,
        as_of_date=datetime.date.today()
    )
    db.add(pos)
    db.commit()
    db.close()
    r = client.get("/api/positions")
    assert r.status_code == 200                # BUG 2 will 500 here


def test_trades_pagination_page1_starts_at_first_row():
    db = SessionLocal()
    for i in range(5):
        db.add(models.Trade(symbol=f"SYM{i}", side="BUY", quantity=10, price=100))
    db.commit()
    db.close()
    r1 = client.get("/api/trades?page=1&size=3")
    r2 = client.get("/api/trades?page=2&size=3")
    assert r1.status_code == 200
    ids_p1 = [t["id"] for t in r1.json()]
    ids_p2 = [t["id"] for t in r2.json()]
    assert ids_p1 != ids_p2                    # BUG 3: p1 skips rows, may overlap
```

- [ ] **Step 2: Run tests to verify they fail (expected — bugs are in)**

```bash
DATABASE_URL=postgresql://cmia:cmia_pass@localhost:5432/positions_db pytest tests/test_positions.py -v 2>&1 | tail -20
```

Expected: Tests fail with `ModuleNotFoundError` (app not created yet). That is correct.

- [ ] **Step 3: Create routers/positions.py — with BUG 1 and BUG 2 inside**

```python
# part1-fastapi-aks/app/routers/positions.py
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.database import get_db
import datetime

router = APIRouter(prefix="/api/positions", tags=["positions"])


class PositionOut(BaseModel):
    id: int
    symbol: str
    quantity: float
    price: float
    market_value: float          # schema expects market_value
    as_of_date: datetime.date

    class Config:
        from_attributes = True


@router.get("", response_model=list[PositionOut])
def get_positions(db: Session = Depends(get_db)):
    # BUG 1: raw SQL aliases market_value as mkt_val — Pydantic can't map it
    rows = db.execute(
        text("SELECT id, symbol, quantity, price, market_value AS mkt_val, as_of_date FROM positions")
    ).mappings().all()

    result = []
    for row in rows:
        # BUG 2: no null guard — if quantity is None, float() raises TypeError → 500
        result.append(PositionOut(
            id=row["id"],
            symbol=row["symbol"],
            quantity=float(row["quantity"]),   # crashes when quantity IS NULL
            price=float(row["price"]),
            market_value=float(row["mkt_val"]),   # KeyError here because of BUG 1
            as_of_date=row["as_of_date"],
        ))
    return result
```

- [ ] **Step 4: Create routers/trades.py — with BUG 3 inside**

```python
# part1-fastapi-aks/app/routers/trades.py
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app import models
import datetime

router = APIRouter(prefix="/api/trades", tags=["trades"])


class TradeOut(BaseModel):
    id: int
    symbol: str
    side: str
    quantity: float
    price: float

    class Config:
        from_attributes = True


@router.get("", response_model=list[TradeOut])
def get_trades(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    # BUG 3: offset should be (page-1)*size but uses page*size → page 1 skips first `size` rows
    offset = page * size
    trades = db.query(models.Trade).offset(offset).limit(size).all()
    return trades
```

- [ ] **Step 5: Create routers/__init__.py**

```python
# part1-fastapi-aks/app/routers/__init__.py
```

- [ ] **Step 6: Create main.py**

```python
# part1-fastapi-aks/app/main.py
from fastapi import FastAPI
from app.routers import positions, trades
from app import models  # ensures tables are created

app = FastAPI(title="CMIA Positions API", version="1.0.0")

app.include_router(positions.router)
app.include_router(trades.router)


@app.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 7: Run the tests — confirm all 3 fail because of the bugs**

```bash
DATABASE_URL=postgresql://cmia:cmia_pass@localhost:5432/positions_db pytest tests/test_positions.py -v 2>&1 | tail -30
```

Expected:
- `test_get_positions_returns_market_value` → FAIL (KeyError `mkt_val` or validation error)
- `test_positions_with_null_quantity` → FAIL (500 TypeError)
- `test_trades_pagination_page1_starts_at_first_row` → FAIL or unexpected behavior

- [ ] **Step 8: Commit the buggy code (this is intentional)**

```bash
git add part1-fastapi-aks/app/
git commit -m "feat: part1 FastAPI routers with 3 bugs to debug"
```

---

### Task 1.3: Debug the 3 bugs — one at a time (THIS IS THE CORE EXERCISE)

This is where you practice the actual interview skill: read the error, reason about the cause, fix precisely, verify.

**Files:**
- Modify: `part1-fastapi-aks/app/routers/positions.py`
- Modify: `part1-fastapi-aks/app/routers/trades.py`

#### Fix BUG 1 — column alias mismatch

- [ ] **Step 1: Read the failure**

Run one test in isolation and read the traceback carefully:
```bash
DATABASE_URL=postgresql://cmia:cmia_pass@localhost:5432/positions_db pytest tests/test_positions.py::test_get_positions_returns_market_value -v -s 2>&1 | tail -20
```

You will see a `KeyError: 'mkt_val'` or a Pydantic validation error. The root cause: SQL aliases the column as `mkt_val` but the code tries to access `row["mkt_val"]` AND the Pydantic model expects `market_value`.

- [ ] **Step 2: Fix — use ORM instead of raw SQL, or fix the alias**

In `app/routers/positions.py`, replace the raw SQL query and row construction:

```python
@router.get("", response_model=list[PositionOut])
def get_positions(db: Session = Depends(get_db)):
    from app import models
    positions = db.query(models.Position).all()
    return positions
```

This removes the alias problem entirely and uses the ORM — cleaner, type-safe, Pydantic maps directly from ORM attributes.

- [ ] **Step 3: Run just BUG 1 test**

```bash
DATABASE_URL=postgresql://cmia:cmia_pass@localhost:5432/positions_db pytest tests/test_positions.py::test_get_positions_returns_market_value -v
```

Expected: PASS (assuming no null rows exist yet)

#### Fix BUG 2 — null quantity crash

- [ ] **Step 4: Run the null test to see the crash**

```bash
DATABASE_URL=postgresql://cmia:cmia_pass@localhost:5432/positions_db pytest tests/test_positions.py::test_positions_with_null_quantity -v -s 2>&1 | tail -20
```

Expected: 500 Internal Server Error. The ORM now returns the row but Pydantic tries to validate `quantity=None` as `float` and fails. The fix: filter out nulls OR use `Optional[float]` in schema.

For a production migration scenario (which is the interview topic) the right answer is: **filter invalid source data** and log it, not hide it in the schema.

- [ ] **Step 5: Fix — filter null quantities, add a warning**

```python
# app/routers/positions.py — replace the endpoint
@router.get("", response_model=list[PositionOut])
def get_positions(db: Session = Depends(get_db)):
    from app import models
    from sqlalchemy import and_
    positions = (
        db.query(models.Position)
        .filter(
            models.Position.quantity.isnot(None),
            models.Position.price.isnot(None),
        )
        .all()
    )
    return positions
```

- [ ] **Step 6: Run both position tests**

```bash
DATABASE_URL=postgresql://cmia:cmia_pass@localhost:5432/positions_db pytest tests/test_positions.py::test_get_positions_returns_market_value tests/test_positions.py::test_positions_with_null_quantity -v
```

Expected: Both PASS

#### Fix BUG 3 — off-by-one pagination

- [ ] **Step 7: Run the pagination test to see the failure**

```bash
DATABASE_URL=postgresql://cmia:cmia_pass@localhost:5432/positions_db pytest tests/test_positions.py::test_trades_pagination_page1_starts_at_first_row -v -s 2>&1 | tail -20
```

Expected: page 1 returns rows starting at position 10 (skips first 10), so p1 may be empty or wrong.

- [ ] **Step 8: Fix — offset = (page - 1) * size**

```python
# app/routers/trades.py — fix the offset line
    offset = (page - 1) * size
```

- [ ] **Step 9: Run all tests**

```bash
DATABASE_URL=postgresql://cmia:cmia_pass@localhost:5432/positions_db pytest tests/ -v
```

Expected: All PASS

- [ ] **Step 10: Commit fixes**

```bash
git add part1-fastapi-aks/app/routers/
git commit -m "fix: part1 — column alias mismatch, null guard, pagination offset"
```

---

### Task 1.4: Data migration script (SQLite → PostgreSQL)

This is the interview centrepiece: a production-style migration with seeding, validation, and rollback.

**Files:**
- Create: `part1-fastapi-aks/migration/seed.py`
- Create: `part1-fastapi-aks/migration/validate.py`
- Create: `part1-fastapi-aks/migration/migrate.py`
- Create: `part1-fastapi-aks/migration/__init__.py`

- [ ] **Step 1: Write failing migration test**

```python
# part1-fastapi-aks/tests/test_migration.py
import os, sqlite3, pytest
from migration.seed import seed_sqlite
from migration.migrate import run_migration
from migration.validate import validate_migration


SOURCE_DB = "/tmp/cmia_source.db"
TARGET_URL = os.getenv("DATABASE_URL", "postgresql://cmia:cmia_pass@localhost:5432/positions_db")


def test_migration_moves_all_rows():
    seed_sqlite(SOURCE_DB, n_positions=50, n_trades=30)
    result = run_migration(source_db=SOURCE_DB, target_url=TARGET_URL)
    assert result["success"] is True
    assert result["positions_migrated"] == 50
    assert result["trades_migrated"] == 30


def test_validation_passes_after_migration():
    report = validate_migration(source_db=SOURCE_DB, target_url=TARGET_URL)
    assert report["positions_match"] is True
    assert report["trades_match"] is True
    assert report["checksum_match"] is True
```

- [ ] **Step 2: Run to verify it fails**

```bash
DATABASE_URL=postgresql://cmia:cmia_pass@localhost:5432/positions_db pytest tests/test_migration.py -v 2>&1 | tail -10
```

Expected: FAIL — `ModuleNotFoundError: No module named 'migration'`

- [ ] **Step 3: Create migration/__init__.py**

```python
# part1-fastapi-aks/migration/__init__.py
```

- [ ] **Step 4: Create seed.py**

```python
# part1-fastapi-aks/migration/seed.py
import sqlite3
import datetime
import random


SYMBOLS = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "JPM", "GS", "MS", "BRK", "BLK"]


def seed_sqlite(db_path: str, n_positions: int = 50, n_trades: int = 30):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("DROP TABLE IF EXISTS positions")
    cur.execute("DROP TABLE IF EXISTS trades")

    cur.execute("""
        CREATE TABLE positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            quantity REAL NOT NULL,
            price REAL NOT NULL,
            market_value REAL NOT NULL,
            as_of_date TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            quantity REAL NOT NULL,
            price REAL NOT NULL,
            traded_at TEXT NOT NULL
        )
    """)

    today = datetime.date.today().isoformat()
    for _ in range(n_positions):
        sym = random.choice(SYMBOLS)
        qty = round(random.uniform(100, 10000), 2)
        price = round(random.uniform(10, 500), 2)
        mv = round(qty * price, 2)
        cur.execute(
            "INSERT INTO positions (symbol, quantity, price, market_value, as_of_date) VALUES (?, ?, ?, ?, ?)",
            (sym, qty, price, mv, today),
        )

    now = datetime.datetime.now().isoformat()
    for _ in range(n_trades):
        sym = random.choice(SYMBOLS)
        side = random.choice(["BUY", "SELL"])
        qty = round(random.uniform(10, 1000), 2)
        price = round(random.uniform(10, 500), 2)
        cur.execute(
            "INSERT INTO trades (symbol, side, quantity, price, traded_at) VALUES (?, ?, ?, ?, ?)",
            (sym, side, qty, price, now),
        )

    conn.commit()
    conn.close()
    print(f"[seed] SQLite seeded: {n_positions} positions, {n_trades} trades → {db_path}")
```

- [ ] **Step 5: Create validate.py**

```python
# part1-fastapi-aks/migration/validate.py
import sqlite3
import hashlib
from sqlalchemy import create_engine, text


def _sqlite_checksum(db_path: str, table: str, col: str) -> str:
    """XOR-based checksum: sum of a numeric column rounded to 2 decimal places."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(f"SELECT ROUND(SUM({col}), 2) FROM {table}")
    val = cur.fetchone()[0] or 0.0
    conn.close()
    return str(round(val, 2))


def _pg_checksum(engine, table: str, col: str) -> str:
    with engine.connect() as conn:
        row = conn.execute(text(f"SELECT ROUND(SUM({col})::numeric, 2) FROM {table}")).fetchone()
    return str(float(row[0]) if row[0] else 0.0)


def validate_migration(source_db: str, target_url: str) -> dict:
    sqlite_conn = sqlite3.connect(source_db)
    pg_engine = create_engine(target_url)

    # Row counts
    src_pos = sqlite_conn.execute("SELECT COUNT(*) FROM positions").fetchone()[0]
    src_trades = sqlite_conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    sqlite_conn.close()

    with pg_engine.connect() as conn:
        tgt_pos = conn.execute(text("SELECT COUNT(*) FROM positions")).scalar()
        tgt_trades = conn.execute(text("SELECT COUNT(*) FROM trades")).scalar()

    # Checksum on market_value (financial correctness check)
    src_checksum = _sqlite_checksum(source_db, "positions", "market_value")
    tgt_checksum = _pg_checksum(pg_engine, "positions", "market_value")

    report = {
        "source_positions": src_pos,
        "target_positions": tgt_pos,
        "source_trades": src_trades,
        "target_trades": tgt_trades,
        "positions_match": src_pos == tgt_pos,
        "trades_match": src_trades == tgt_trades,
        "source_checksum": src_checksum,
        "target_checksum": tgt_checksum,
        "checksum_match": abs(float(src_checksum) - float(tgt_checksum)) < 0.01,
    }

    print("[validate]", report)
    return report
```

- [ ] **Step 6: Create migrate.py**

```python
# part1-fastapi-aks/migration/migrate.py
import sqlite3
from sqlalchemy import create_engine, text


def run_migration(source_db: str, target_url: str) -> dict:
    """
    Migrate positions and trades from SQLite → PostgreSQL.
    Uses a transaction: rolls back everything if any insert fails.
    Returns dict with success flag and row counts.
    """
    sqlite_conn = sqlite3.connect(source_db)
    pg_engine = create_engine(target_url)

    # Read source data
    positions = sqlite_conn.execute(
        "SELECT symbol, quantity, price, market_value, as_of_date FROM positions"
    ).fetchall()
    trades = sqlite_conn.execute(
        "SELECT symbol, side, quantity, price, traded_at FROM trades"
    ).fetchall()
    sqlite_conn.close()

    pos_count = 0
    trade_count = 0

    with pg_engine.begin() as conn:   # begin() = auto-commit on success, rollback on exception
        # Clear target tables first (idempotent migration)
        conn.execute(text("DELETE FROM trades"))
        conn.execute(text("DELETE FROM positions"))

        for row in positions:
            conn.execute(
                text("""
                    INSERT INTO positions (symbol, quantity, price, market_value, as_of_date)
                    VALUES (:symbol, :quantity, :price, :market_value, :as_of_date)
                """),
                {
                    "symbol": row[0],
                    "quantity": row[1],
                    "price": row[2],
                    "market_value": row[3],
                    "as_of_date": row[4],
                },
            )
            pos_count += 1

        for row in trades:
            conn.execute(
                text("""
                    INSERT INTO trades (symbol, side, quantity, price, traded_at)
                    VALUES (:symbol, :side, :quantity, :price, :traded_at)
                """),
                {
                    "symbol": row[0],
                    "side": row[1],
                    "quantity": row[2],
                    "price": row[3],
                    "traded_at": row[4],
                },
            )
            trade_count += 1

    print(f"[migrate] Done: {pos_count} positions, {trade_count} trades")
    return {"success": True, "positions_migrated": pos_count, "trades_migrated": trade_count}
```

- [ ] **Step 7: Run migration tests**

```bash
DATABASE_URL=postgresql://cmia:cmia_pass@localhost:5432/positions_db pytest tests/test_migration.py -v
```

Expected: Both PASS

- [ ] **Step 8: Run manually to see real output**

```bash
DATABASE_URL=postgresql://cmia:cmia_pass@localhost:5432/positions_db python3 -c "
from migration.seed import seed_sqlite
from migration.migrate import run_migration
from migration.validate import validate_migration
seed_sqlite('/tmp/cmia_source.db', 100, 50)
r = run_migration('/tmp/cmia_source.db', 'postgresql://cmia:cmia_pass@localhost:5432/positions_db')
print(r)
v = validate_migration('/tmp/cmia_source.db', 'postgresql://cmia:cmia_pass@localhost:5432/positions_db')
print(v)
"
```

Expected output: `success: True`, `positions_match: True`, `trades_match: True`, `checksum_match: True`

- [ ] **Step 9: Commit**

```bash
git add part1-fastapi-aks/migration/ part1-fastapi-aks/tests/test_migration.py
git commit -m "feat: part1 migration — seed, migrate SQLite→PG, validate checksums"
```

---

### Task 1.5: Dockerize + Kubernetes manifests for AKS

**Files:**
- Create: `part1-fastapi-aks/Dockerfile`
- Create: `part1-fastapi-aks/k8s/namespace.yaml`
- Create: `part1-fastapi-aks/k8s/configmap.yaml`
- Create: `part1-fastapi-aks/k8s/deployment.yaml`
- Create: `part1-fastapi-aks/k8s/service.yaml`

- [ ] **Step 1: Create Dockerfile**

```dockerfile
# part1-fastapi-aks/Dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY migration/ ./migration/

ENV DATABASE_URL=postgresql://cmia:cmia_pass@postgres:5432/positions_db

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Build and test Docker image locally**

```bash
cd part1-fastapi-aks
docker build -t cmia-fastapi:latest .
docker run --rm -e DATABASE_URL=postgresql://cmia:cmia_pass@host.docker.internal:5432/positions_db \
  -p 8000:8000 cmia-fastapi:latest &
sleep 3
curl http://localhost:8000/health
```

Expected: `{"status":"ok"}`

```bash
pkill -f uvicorn 2>/dev/null; true
```

- [ ] **Step 3: Create k8s/namespace.yaml**

```yaml
# part1-fastapi-aks/k8s/namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: cmia
```

- [ ] **Step 4: Create k8s/configmap.yaml**

```yaml
# part1-fastapi-aks/k8s/configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: cmia-config
  namespace: cmia
data:
  DATABASE_URL: "postgresql://cmia:cmia_pass@postgres-service:5432/positions_db"
  APP_ENV: "production"
```

- [ ] **Step 5: Create k8s/deployment.yaml**

```yaml
# part1-fastapi-aks/k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: cmia-fastapi
  namespace: cmia
  labels:
    app: cmia-fastapi
spec:
  replicas: 2
  selector:
    matchLabels:
      app: cmia-fastapi
  template:
    metadata:
      labels:
        app: cmia-fastapi
    spec:
      containers:
        - name: fastapi
          image: YOUR_ACR_NAME.azurecr.io/cmia-fastapi:latest   # replace with your ACR
          ports:
            - containerPort: 8000
          envFrom:
            - configMapRef:
                name: cmia-config
          readinessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 15
            periodSeconds: 20
          resources:
            requests:
              memory: "128Mi"
              cpu: "100m"
            limits:
              memory: "256Mi"
              cpu: "500m"
```

- [ ] **Step 6: Create k8s/service.yaml**

```yaml
# part1-fastapi-aks/k8s/service.yaml
apiVersion: v1
kind: Service
metadata:
  name: cmia-fastapi-service
  namespace: cmia
spec:
  selector:
    app: cmia-fastapi
  ports:
    - protocol: TCP
      port: 80
      targetPort: 8000
  type: LoadBalancer    # Azure provisions an external IP for this
```

- [ ] **Step 7: Deploy to AKS (run these when you have an AKS cluster)**

```bash
# 1. Create resource group + AKS cluster (one-time setup ~5 min)
az group create --name cmia-rg --location canadacentral
az aks create --resource-group cmia-rg --name cmia-aks \
  --node-count 2 --node-vm-size Standard_B2s \
  --generate-ssh-keys

# 2. Get credentials
az aks get-credentials --resource-group cmia-rg --name cmia-aks

# 3. Create Azure Container Registry + push image
az acr create --resource-group cmia-rg --name cmiaregistry --sku Basic
az acr login --name cmiaregistry
docker tag cmia-fastapi:latest cmiaregistry.azurecr.io/cmia-fastapi:latest
docker push cmiaregistry.azurecr.io/cmia-fastapi:latest

# 4. Attach ACR to AKS
az aks update --name cmia-aks --resource-group cmia-rg --attach-acr cmiaregistry

# 5. Apply manifests
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml

# 6. Verify
kubectl get pods -n cmia
kubectl get svc -n cmia     # wait for EXTERNAL-IP
curl http://<EXTERNAL-IP>/health
```

- [ ] **Step 8: Commit**

```bash
git add part1-fastapi-aks/Dockerfile part1-fastapi-aks/k8s/
git commit -m "feat: part1 Dockerfile and AKS manifests — 2 replicas, readiness/liveness probes"
```

---

## PART 2: Flask + EKS (~2 hours)

### Repo layout for Part 2

```
part2-flask-eks/
├── app/
│   ├── __init__.py          # Flask app factory
│   ├── routes.py            # BUG 1 (wrong HTTP method) + BUG 3 (bad rollback)
│   ├── models.py            # SQLAlchemy models (same schema)
│   ├── database.py          # DB connection (same pattern)
│   └── pipeline.py          # ETL logic — BUG 2 (duplicates) + BUG 4 (div/0)
├── migration/
│   ├── seed_csv.py          # Generates CSV source files
│   ├── etl.py               # CSV → PostgreSQL ETL with validation
│   └── validate.py          # Reusable validation (same logic as Part 1)
├── tests/
│   ├── test_routes.py
│   └── test_pipeline.py
├── k8s/
│   ├── namespace.yaml
│   ├── configmap.yaml
│   ├── deployment.yaml
│   └── service.yaml
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

### Task 2.0: Bootstrap Flask

**Files:**
- Create: `part2-flask-eks/requirements.txt`
- Create: `part2-flask-eks/docker-compose.yml`

- [ ] **Step 1: Create requirements.txt**

```
flask==3.0.3
flask-sqlalchemy==3.1.1
sqlalchemy==2.0.30
psycopg2-binary==2.9.9
pytest==8.2.0
pytest-flask==1.3.0
```

- [ ] **Step 2: Create docker-compose.yml**

```yaml
version: "3.9"
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: cmia
      POSTGRES_PASSWORD: cmia_pass
      POSTGRES_DB: flask_positions_db
    ports:
      - "5433:5432"   # 5433 to avoid conflict with Part 1
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U cmia -d flask_positions_db"]
      interval: 5s
      retries: 10

  api:
    build: .
    ports:
      - "5000:5000"
    environment:
      DATABASE_URL: postgresql://cmia:cmia_pass@postgres:5432/flask_positions_db
    depends_on:
      postgres:
        condition: service_healthy
```

- [ ] **Step 3: Install packages**

```bash
cd part2-flask-eks
pip3 install -r requirements.txt
```

- [ ] **Step 4: Start PostgreSQL**

```bash
docker compose up postgres -d
```

- [ ] **Step 5: Commit**

```bash
git add part2-flask-eks/requirements.txt part2-flask-eks/docker-compose.yml
git commit -m "feat: part2 bootstrap — Flask requirements and docker-compose"
```

---

### Task 2.1: Flask models and database

**Files:**
- Create: `part2-flask-eks/app/__init__.py`
- Create: `part2-flask-eks/app/database.py`
- Create: `part2-flask-eks/app/models.py`

- [ ] **Step 1: Write failing test**

```python
# part2-flask-eks/tests/test_routes.py
import os, pytest
os.environ["DATABASE_URL"] = "postgresql://cmia:cmia_pass@localhost:5433/flask_positions_db"

from app import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.get_json()["status"] == "ok"
```

- [ ] **Step 2: Run to confirm fail**

```bash
cd part2-flask-eks
DATABASE_URL=postgresql://cmia:cmia_pass@localhost:5433/flask_positions_db pytest tests/test_routes.py::test_health -v 2>&1 | tail -10
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Create app/database.py**

```python
# part2-flask-eks/app/database.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://cmia:cmia_pass@localhost:5433/flask_positions_db")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 4: Create app/models.py (same schema as Part 1)**

```python
# part2-flask-eks/app/models.py
from sqlalchemy import Column, Integer, String, Float, Date, DateTime, func
from app.database import Base


class Position(Base):
    __tablename__ = "positions"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(10), nullable=False)
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    market_value = Column(Float, nullable=False)
    as_of_date = Column(Date, nullable=False)


class Trade(Base):
    __tablename__ = "trades"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(10), nullable=False)
    side = Column(String(4), nullable=False)
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    pnl_pct = Column(Float, nullable=True)
    traded_at = Column(DateTime, server_default=func.now())
```

- [ ] **Step 5: Create app/__init__.py (Flask app factory)**

```python
# part2-flask-eks/app/__init__.py
import os
from flask import Flask
from app.database import engine, Base


def create_app():
    app = Flask(__name__)
    app.config["DATABASE_URL"] = os.getenv(
        "DATABASE_URL", "postgresql://cmia:cmia_pass@localhost:5433/flask_positions_db"
    )

    # Create tables
    from app import models   # noqa: F401
    Base.metadata.create_all(bind=engine)

    from app.routes import bp
    app.register_blueprint(bp)

    return app
```

- [ ] **Step 6: Create app/routes.py — with BUG 1 (wrong HTTP method) + BUG 3 (commit instead of rollback)**

```python
# part2-flask-eks/app/routes.py
from flask import Blueprint, jsonify, request
from app.database import SessionLocal
from app import models

bp = Blueprint("main", __name__)


@bp.get("/health")
def health():
    return jsonify({"status": "ok"})


@bp.get("/api/positions")
def get_positions():
    db = SessionLocal()
    positions = db.query(models.Position).all()
    db.close()
    return jsonify([
        {
            "id": p.id,
            "symbol": p.symbol,
            "quantity": p.quantity,
            "price": p.price,
            "market_value": p.market_value,
            "as_of_date": str(p.as_of_date),
        }
        for p in positions
    ])


# BUG 1: decorated with @bp.get but should be @bp.post — POST body will never be read
@bp.get("/api/run-etl")
def run_etl():
    data = request.get_json(silent=True) or {}
    source_path = data.get("source_path", "/tmp/cmia_positions.csv")

    db = SessionLocal()
    try:
        from app.pipeline import run_etl_pipeline
        result = run_etl_pipeline(source_path, db)
        db.commit()
        return jsonify(result)
    except Exception as e:
        # BUG 3: calls db.commit() on error instead of db.rollback() — bad data may persist
        db.commit()
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()
```

- [ ] **Step 7: Create app/pipeline.py — with BUG 2 (duplicates) + BUG 4 (div/0)**

```python
# part2-flask-eks/app/pipeline.py
import csv
import datetime


def run_etl_pipeline(csv_path: str, db) -> dict:
    """
    Reads positions from a CSV and inserts into the DB.
    Contains 2 bugs: no dedup check (BUG 2) + division by zero (BUG 4).
    """
    from app import models

    inserted = 0
    errors = []

    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                buy_price = float(row.get("buy_price", 0))
                sell_price = float(row.get("sell_price", 0))

                # BUG 4: no guard for buy_price == 0 → ZeroDivisionError
                pnl_pct = (sell_price - buy_price) / buy_price * 100

                pos = models.Position(
                    symbol=row["symbol"],
                    quantity=float(row["quantity"]),
                    price=float(row["price"]),
                    market_value=float(row["quantity"]) * float(row["price"]),
                    as_of_date=datetime.date.today(),
                )
                # BUG 2: no check for existing row — re-running ETL duplicates everything
                db.add(pos)
                inserted += 1
            except Exception as e:
                errors.append({"row": row, "error": str(e)})

    return {"inserted": inserted, "errors": errors}
```

- [ ] **Step 8: Run health test**

```bash
DATABASE_URL=postgresql://cmia:cmia_pass@localhost:5433/flask_positions_db pytest tests/test_routes.py::test_health -v
```

Expected: PASS

- [ ] **Step 9: Commit buggy Flask code**

```bash
git add part2-flask-eks/app/
git commit -m "feat: part2 Flask app with 3 bugs to debug"
```

---

### Task 2.2: Write tests that expose the bugs + fix them

**Files:**
- Create: `part2-flask-eks/tests/test_pipeline.py`
- Modify: `part2-flask-eks/app/routes.py`
- Modify: `part2-flask-eks/app/pipeline.py`

- [ ] **Step 1: Write pipeline tests that expose BUG 2 and BUG 4**

```python
# part2-flask-eks/tests/test_pipeline.py
import os, csv, tempfile, pytest
os.environ["DATABASE_URL"] = "postgresql://cmia:cmia_pass@localhost:5433/flask_positions_db"

from app import create_app
from app.database import SessionLocal
from app import models


@pytest.fixture(autouse=True)
def clean_positions():
    db = SessionLocal()
    db.query(models.Position).delete()
    db.commit()
    db.close()


def _write_csv(path, rows):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["symbol", "quantity", "price", "buy_price", "sell_price"])
        writer.writeheader()
        writer.writerows(rows)


def test_etl_no_duplicates_on_rerun():
    app = create_app()
    rows = [
        {"symbol": "AAPL", "quantity": "100", "price": "175.0", "buy_price": "170.0", "sell_price": "175.0"},
        {"symbol": "MSFT", "quantity": "50", "price": "300.0", "buy_price": "290.0", "sell_price": "300.0"},
    ]
    with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False) as f:
        path = f.name
    _write_csv(path, rows)

    with app.test_client() as c:
        # Run ETL twice
        c.post("/api/run-etl", json={"source_path": path})
        c.post("/api/run-etl", json={"source_path": path})

    db = SessionLocal()
    count = db.query(models.Position).count()
    db.close()
    # BUG 2: without dedup, count will be 4 (2 inserts × 2 runs)
    assert count == 2, f"Expected 2 positions but got {count} — duplicate rows inserted"


def test_etl_handles_zero_buy_price():
    app = create_app()
    rows = [
        {"symbol": "AAPL", "quantity": "100", "price": "175.0", "buy_price": "0", "sell_price": "175.0"},
    ]
    with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False) as f:
        path = f.name
    _write_csv(path, rows)

    with app.test_client() as c:
        r = c.post("/api/run-etl", json={"source_path": path})
    # BUG 4: ZeroDivisionError means the row is in errors, not inserted
    data = r.get_json()
    # After fix: inserted=1, errors=[]
    assert data.get("inserted") == 1
    assert data.get("errors") == []
```

- [ ] **Step 2: Write route test that exposes BUG 1**

```python
# part2-flask-eks/tests/test_routes.py  — add to existing file

def test_run_etl_requires_post_method(client):
    # BUG 1: endpoint is @bp.get so POST returns 405 Method Not Allowed
    r = client.post("/api/run-etl", json={"source_path": "/tmp/fake.csv"})
    assert r.status_code != 405, "Endpoint must accept POST — got 405 Method Not Allowed"
```

- [ ] **Step 3: Run all Part 2 tests — confirm failures**

```bash
DATABASE_URL=postgresql://cmia:cmia_pass@localhost:5433/flask_positions_db pytest tests/ -v 2>&1 | tail -20
```

Expected: `test_run_etl_requires_post_method` → FAIL (405), `test_etl_no_duplicates_on_rerun` → FAIL (count=4), `test_etl_handles_zero_buy_price` → FAIL (ZeroDivisionError)

#### Fix BUG 1 — wrong HTTP method

- [ ] **Step 4: Fix routes.py — change @bp.get to @bp.post + fix rollback**

```python
# app/routes.py — replace run_etl function entirely
@bp.post("/api/run-etl")
def run_etl():
    data = request.get_json(silent=True) or {}
    source_path = data.get("source_path", "/tmp/cmia_positions.csv")

    db = SessionLocal()
    try:
        from app.pipeline import run_etl_pipeline
        result = run_etl_pipeline(source_path, db)
        db.commit()
        return jsonify(result)
    except Exception as e:
        db.rollback()   # FIX BUG 3: was db.commit()
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()
```

#### Fix BUG 2 — duplicate inserts

- [ ] **Step 5: Fix pipeline.py — add dedup check + guard for zero buy_price**

```python
# app/pipeline.py — replace run_etl_pipeline entirely
import csv
import datetime


def run_etl_pipeline(csv_path: str, db) -> dict:
    from app import models

    inserted = 0
    skipped = 0
    errors = []

    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                buy_price = float(row.get("buy_price", 0))
                sell_price = float(row.get("sell_price", 0))

                # FIX BUG 4: guard against zero buy_price
                if buy_price == 0:
                    pnl_pct = None
                else:
                    pnl_pct = round((sell_price - buy_price) / buy_price * 100, 4)

                symbol = row["symbol"]
                quantity = float(row["quantity"])
                price = float(row["price"])
                as_of_date = datetime.date.today()

                # FIX BUG 2: dedup check — skip if same symbol+date already exists
                existing = (
                    db.query(models.Position)
                    .filter(
                        models.Position.symbol == symbol,
                        models.Position.as_of_date == as_of_date,
                    )
                    .first()
                )
                if existing:
                    skipped += 1
                    continue

                pos = models.Position(
                    symbol=symbol,
                    quantity=quantity,
                    price=price,
                    market_value=round(quantity * price, 2),
                    as_of_date=as_of_date,
                )
                db.add(pos)
                inserted += 1
            except Exception as e:
                errors.append({"row": dict(row), "error": str(e)})

    return {"inserted": inserted, "skipped": skipped, "errors": errors}
```

- [ ] **Step 6: Run all Part 2 tests**

```bash
DATABASE_URL=postgresql://cmia:cmia_pass@localhost:5433/flask_positions_db pytest tests/ -v
```

Expected: All PASS

- [ ] **Step 7: Commit fixes**

```bash
git add part2-flask-eks/app/
git commit -m "fix: part2 — POST method, dedup check, zero buy_price guard, rollback on error"
```

---

### Task 2.3: CSV ETL migration with validation

**Files:**
- Create: `part2-flask-eks/migration/__init__.py`
- Create: `part2-flask-eks/migration/seed_csv.py`
- Create: `part2-flask-eks/migration/validate.py`
- Create: `part2-flask-eks/migration/etl.py`

- [ ] **Step 1: Write failing test**

```python
# part2-flask-eks/tests/test_pipeline.py — add to existing file
from migration.seed_csv import seed_csv
from migration.etl import run_etl_migration
from migration.validate import validate_etl


def test_csv_etl_all_rows_migrated():
    path = "/tmp/cmia_etl_source.csv"
    seed_csv(path, n=40)

    db = SessionLocal()
    db.query(models.Position).delete()
    db.commit()
    db.close()

    result = run_etl_migration(
        csv_path=path,
        target_url=os.environ["DATABASE_URL"],
    )
    assert result["success"] is True
    assert result["inserted"] == 40

    report = validate_etl(csv_path=path, target_url=os.environ["DATABASE_URL"])
    assert report["row_count_match"] is True
```

- [ ] **Step 2: Run to confirm fail**

```bash
DATABASE_URL=postgresql://cmia:cmia_pass@localhost:5433/flask_positions_db pytest tests/test_pipeline.py::test_csv_etl_all_rows_migrated -v 2>&1 | tail -10
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Create migration/__init__.py**

```python
# part2-flask-eks/migration/__init__.py
```

- [ ] **Step 4: Create migration/seed_csv.py**

```python
# part2-flask-eks/migration/seed_csv.py
import csv
import random
import datetime

SYMBOLS = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "JPM", "GS", "MS", "BAC", "C"]


def seed_csv(path: str, n: int = 40):
    today = datetime.date.today().isoformat()
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["symbol", "quantity", "price", "buy_price", "sell_price"]
        )
        writer.writeheader()
        for _ in range(n):
            sym = random.choice(SYMBOLS)
            qty = round(random.uniform(10, 1000), 2)
            buy = round(random.uniform(50, 400), 2)
            sell = round(buy * random.uniform(0.9, 1.2), 2)
            writer.writerow({
                "symbol": sym,
                "quantity": qty,
                "price": sell,
                "buy_price": buy,
                "sell_price": sell,
            })
    print(f"[seed_csv] Wrote {n} rows to {path}")
```

- [ ] **Step 5: Create migration/validate.py**

```python
# part2-flask-eks/migration/validate.py
import csv
from sqlalchemy import create_engine, text


def validate_etl(csv_path: str, target_url: str) -> dict:
    with open(csv_path, newline="") as f:
        source_rows = list(csv.DictReader(f))

    engine = create_engine(target_url)
    with engine.connect() as conn:
        tgt_count = conn.execute(text("SELECT COUNT(*) FROM positions")).scalar()
        tgt_mv_sum = conn.execute(
            text("SELECT ROUND(SUM(market_value)::numeric, 2) FROM positions")
        ).scalar()

    src_mv_sum = round(
        sum(float(r["quantity"]) * float(r["price"]) for r in source_rows), 2
    )

    report = {
        "source_rows": len(source_rows),
        "target_rows": tgt_count,
        "row_count_match": len(source_rows) == tgt_count,
        "source_mv_sum": src_mv_sum,
        "target_mv_sum": float(tgt_mv_sum) if tgt_mv_sum else 0.0,
        "checksum_match": abs(src_mv_sum - float(tgt_mv_sum or 0)) < 0.10,
    }
    print("[validate_etl]", report)
    return report
```

- [ ] **Step 6: Create migration/etl.py**

```python
# part2-flask-eks/migration/etl.py
import csv
import datetime
from sqlalchemy import create_engine, text


def run_etl_migration(csv_path: str, target_url: str) -> dict:
    engine = create_engine(target_url)
    inserted = 0
    errors = []

    with open(csv_path, newline="") as f:
        rows = list(csv.DictReader(f))

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM positions"))  # idempotent

        for row in rows:
            try:
                qty = float(row["quantity"])
                price = float(row["price"])
                mv = round(qty * price, 2)
                conn.execute(
                    text("""
                        INSERT INTO positions (symbol, quantity, price, market_value, as_of_date)
                        VALUES (:symbol, :quantity, :price, :market_value, :as_of_date)
                    """),
                    {
                        "symbol": row["symbol"],
                        "quantity": qty,
                        "price": price,
                        "market_value": mv,
                        "as_of_date": datetime.date.today(),
                    },
                )
                inserted += 1
            except Exception as e:
                errors.append({"row": dict(row), "error": str(e)})

    return {"success": True, "inserted": inserted, "errors": errors}
```

- [ ] **Step 7: Run all tests**

```bash
DATABASE_URL=postgresql://cmia:cmia_pass@localhost:5433/flask_positions_db pytest tests/ -v
```

Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add part2-flask-eks/migration/ part2-flask-eks/tests/
git commit -m "feat: part2 CSV ETL migration — seed, migrate, validate checksums"
```

---

### Task 2.4: Dockerize + Kubernetes manifests for EKS

**Files:**
- Create: `part2-flask-eks/Dockerfile`
- Create: `part2-flask-eks/k8s/namespace.yaml`
- Create: `part2-flask-eks/k8s/configmap.yaml`
- Create: `part2-flask-eks/k8s/deployment.yaml`
- Create: `part2-flask-eks/k8s/service.yaml`

- [ ] **Step 1: Create Dockerfile**

```dockerfile
# part2-flask-eks/Dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY migration/ ./migration/

ENV DATABASE_URL=postgresql://cmia:cmia_pass@postgres:5432/flask_positions_db
ENV FLASK_APP=app
ENV FLASK_ENV=production

EXPOSE 5000

CMD ["flask", "run", "--host=0.0.0.0", "--port=5000"]
```

- [ ] **Step 2: Build and test Docker image**

```bash
cd part2-flask-eks
docker build -t cmia-flask:latest .
docker run --rm \
  -e DATABASE_URL=postgresql://cmia:cmia_pass@host.docker.internal:5433/flask_positions_db \
  -p 5000:5000 cmia-flask:latest &
sleep 3
curl http://localhost:5000/health
pkill -f "flask run" 2>/dev/null; true
```

Expected: `{"status":"ok"}`

- [ ] **Step 3: Create k8s/namespace.yaml**

```yaml
# part2-flask-eks/k8s/namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: cmia-flask
```

- [ ] **Step 4: Create k8s/configmap.yaml**

```yaml
# part2-flask-eks/k8s/configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: cmia-flask-config
  namespace: cmia-flask
data:
  DATABASE_URL: "postgresql://cmia:cmia_pass@postgres-service:5432/flask_positions_db"
  FLASK_ENV: "production"
```

- [ ] **Step 5: Create k8s/deployment.yaml**

```yaml
# part2-flask-eks/k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: cmia-flask
  namespace: cmia-flask
  labels:
    app: cmia-flask
spec:
  replicas: 2
  selector:
    matchLabels:
      app: cmia-flask
  template:
    metadata:
      labels:
        app: cmia-flask
    spec:
      containers:
        - name: flask
          image: YOUR_ECR_ACCOUNT_ID.dkr.ecr.ca-central-1.amazonaws.com/cmia-flask:latest
          ports:
            - containerPort: 5000
          envFrom:
            - configMapRef:
                name: cmia-flask-config
          readinessProbe:
            httpGet:
              path: /health
              port: 5000
            initialDelaySeconds: 5
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /health
              port: 5000
            initialDelaySeconds: 15
            periodSeconds: 20
          resources:
            requests:
              memory: "128Mi"
              cpu: "100m"
            limits:
              memory: "256Mi"
              cpu: "500m"
```

- [ ] **Step 6: Create k8s/service.yaml**

```yaml
# part2-flask-eks/k8s/service.yaml
apiVersion: v1
kind: Service
metadata:
  name: cmia-flask-service
  namespace: cmia-flask
  annotations:
    service.beta.kubernetes.io/aws-load-balancer-type: "nlb"  # AWS NLB
spec:
  selector:
    app: cmia-flask
  ports:
    - protocol: TCP
      port: 80
      targetPort: 5000
  type: LoadBalancer
```

- [ ] **Step 7: Deploy to EKS (run these when you have an EKS cluster)**

```bash
# 1. Create EKS cluster (one-time setup ~15 min)
eksctl create cluster \
  --name cmia-eks \
  --region ca-central-1 \
  --nodegroup-name standard-workers \
  --node-type t3.small \
  --nodes 2 \
  --managed

# 2. Create ECR repository + push image
aws ecr create-repository --repository-name cmia-flask --region ca-central-1
aws ecr get-login-password --region ca-central-1 | \
  docker login --username AWS --password-stdin \
  $(aws sts get-caller-identity --query Account --output text).dkr.ecr.ca-central-1.amazonaws.com
docker tag cmia-flask:latest \
  $(aws sts get-caller-identity --query Account --output text).dkr.ecr.ca-central-1.amazonaws.com/cmia-flask:latest
docker push \
  $(aws sts get-caller-identity --query Account --output text).dkr.ecr.ca-central-1.amazonaws.com/cmia-flask:latest

# 3. Apply manifests
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml

# 4. Verify
kubectl get pods -n cmia-flask
kubectl get svc -n cmia-flask
curl http://<EXTERNAL-IP>/health
```

- [ ] **Step 8: Final commit**

```bash
git add part2-flask-eks/Dockerfile part2-flask-eks/k8s/
git commit -m "feat: part2 Dockerfile and EKS manifests — 2 replicas, NLB service"
```

---

## Interview talking points this project gives you

### On migration (Mark Segal questions)
- "I used SQLAlchemy's `engine.begin()` context manager which auto-commits on success and rolls back on any exception — no manual try/except needed for the transaction itself."
- "After migration I validate row counts and a checksum on `market_value` — this gives you confidence the financial numbers are consistent, not just that rows moved."
- "The migration is idempotent: it DELETEs before inserting, so re-running it doesn't create duplicates. For real Snowflake migrations you'd use MERGE or a staging table."

### On debugging (Cindy Tam questions)
- "The first bug was a column alias mismatch — raw SQL returned `mkt_val` but Pydantic expected `market_value`. Switching to the ORM eliminated the mapping entirely."
- "The pagination bug was off-by-one: `page * size` instead of `(page-1) * size`. Page 1 was skipping the first N rows entirely. Classic mistake."
- "The rollback bug in Flask was dangerous in a financial context — on exception the code was calling `db.commit()` which would persist partial/corrupted data. Fixed to `db.rollback()`."

### On containers / K8s
- "Both services have readiness and liveness probes. Readiness tells Kubernetes not to route traffic until the app is ready; liveness restarts the pod if the app hangs."
- "Resources requests/limits are set so the scheduler can bin-pack pods and prevent one pod from starving others."
- "AKS uses Azure's LoadBalancer; EKS uses an NLB via the `service.beta.kubernetes.io/aws-load-balancer-type` annotation."

---

## Self-Review (plan completeness check)

| Requirement | Covered? |
|---|---|
| FastAPI app with debugging | Task 1.2 + 1.3 — 3 bugs planted and fixed |
| Flask app with debugging | Task 2.1–2.2 — 3 bugs planted and fixed |
| Data migration project | Task 1.4 (SQLite→PG) + Task 2.3 (CSV→PG) |
| Validation + rollback | validate.py in both parts, `engine.begin()` + `db.rollback()` |
| AKS deployment | Task 1.5 — Dockerfile + manifests + az commands |
| EKS deployment | Task 2.4 — Dockerfile + manifests + eksctl commands |
| 4 hour time budget | ~2h each part, Docker Compose removes cloud setup blocking time |
| Interview talking points | Mapped to Mark (migration/cloud) + Cindy (debugging/code) |
