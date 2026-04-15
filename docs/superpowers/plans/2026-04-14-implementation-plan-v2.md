# Implementation Plan v2
_Ground truth: `docs/interview-prep/TRUTH_SOURCE.md`_
_Supersedes: `2026-04-14-data-migration-project.md` (wrong stack, synthetic data, EKS)_

---

## Architecture

```
yfinance (live market data)
        │
        ▼
  Azure SQL                         ← Part 1 source (simulates legacy SQL Server)
  (OLTP, hosted free tier)
        │
        │  FastAPI migration service
        │  • schema transform (OLTP → OLAP)
        │  • stored proc → Snowflake equivalent
        │  • validation + rollback
        ▼
  Snowflake                         ← Part 1 target + Part 2 source
  (OLAP, free trial)
        │
        │  Flask ETL pipeline
        │  • aggregate + reshape
        │  • validation + rollback
        ▼
  Amazon RDS (PostgreSQL)           ← Part 2 target (TBD — user to confirm)
  (OLTP serving layer, free tier)
        │
        ├── Part 1: FastAPI → Azure AKS
        └── Part 2: Flask  → AWS (ECS or EKS)
```

**Why this stack maps to OTPP interview:**
- Azure SQL = SQL Server equivalent (what CMIA is migrating FROM)
- Snowflake = what CMIA is migrating TO (data)
- AKS = where Python scripts/apps land (compute)
- OLTP→OLAP schema transformation = the actual engineering challenge in the role

---

## Owner legend

- 🔴 **YOU** — requires your accounts, credentials, or decisions
- 🔵 **ME** — Claude builds, writes, implements
- 🟡 **TOGETHER** — you run commands, review output, make calls

---

## Phase 0 — Cloud Setup (YOU, ~45 min)

Nothing gets built until these are done. Each item produces a credential or connection string.

### 0.1 Azure SQL
- [ ] 🔴 Go to portal.azure.com → Create resource → Azure SQL → free serverless tier
- [ ] 🔴 Create database: `cmia-source-db`, server: `cmia-source-server`
- [ ] 🔴 Set firewall rule: "Allow Azure services" ON + add your IP
- [ ] 🔴 Copy connection string → paste into `.env` file (Claude will create the template)
- [ ] 🔴 Run `az login` in terminal and confirm it works

**Expected output:** `AZURE_SQL_CONN=mssql+pyodbc://user:pass@server.database.windows.net/cmia-source-db?driver=ODBC+Driver+18+for+SQL+Server`

### 0.2 Snowflake
- [ ] 🔴 Sign up at snowflake.com/trial (free, $400 credit, 30 days)
- [ ] 🔴 Note your: account identifier, warehouse name (default: `COMPUTE_WH`), database name
- [ ] 🔴 Create database: `CMIA_DW`
- [ ] 🔴 Create warehouse: `CMIA_WH` (X-Small, auto-suspend 1 min)
- [ ] 🔴 Copy credentials → paste into `.env` file

**Expected output:** `SNOWFLAKE_ACCOUNT=xxx.snowflakecomputing.com`, `SNOWFLAKE_USER`, `SNOWFLAKE_PASSWORD`, `SNOWFLAKE_DATABASE=CMIA_DW`, `SNOWFLAKE_WAREHOUSE=CMIA_WH`

### 0.3 AWS (Part 2)
- [ ] 🔴 **Decision needed:** confirm Amazon RDS PostgreSQL as Part 2 target (recommended) or pick alternative
  - Option A: **Amazon RDS PostgreSQL** — free tier 12 months, OLTP serving layer, interesting OLAP→OLTP reverse story
  - Option B: **Amazon Aurora Serverless** — PostgreSQL-compatible, scales to zero, slightly more complex setup
  - Option C: **Amazon Redshift** — OLAP→OLAP, least interesting story, not recommended
- [ ] 🔴 Once decided: create RDS instance `cmia-target-db` (free tier, PostgreSQL 15)
- [ ] 🔴 Set security group: allow inbound 5432 from your IP
- [ ] 🔴 Copy connection string → paste into `.env`
- [ ] 🔴 Run `aws configure` with your access key + secret

**Expected output:** `AWS_RDS_CONN=postgresql://user:pass@endpoint.rds.amazonaws.com:5432/cmia_target`

### 0.4 Local environment
- [ ] 🔴 Confirm Docker is running: `docker ps`
- [ ] 🔴 Confirm kubectl works: `kubectl version --client`
- [ ] 🔴 Install ODBC Driver 18 for SQL Server (needed for Azure SQL from Python):
  ```bash
  brew install msodbcsql18 mssql-tools18
  ```

---

## Phase 1 — Data Exploration (🟡 TOGETHER, ~30 min)

Data-first: look at what yfinance actually returns before writing a single model.

### 1.1 Pull and inspect yfinance data
- [ ] 🔵 ME: Create `scripts/explore_data.py` — pulls 20 capital markets symbols, prints dtypes, nulls, cardinality, sample rows
- [ ] 🟡 YOU: Run it: `python3 scripts/explore_data.py`
- [ ] 🟡 YOU: Review output and flag any surprises (missing data, unexpected types)

**Symbols used (OTPP-relevant — large-cap + financial sector):**
```
AAPL, MSFT, GOOGL, AMZN, JPM, GS, MS, BLK, BX, KKR,
BAC, C, WFC, SCHW, CME, ICE, SPGI, MCO, TRV, CB
```

**Expected data shape:**
```
prices:    (symbol, date, open, high, low, close, volume, adj_close)
~14,600 rows × 20 symbols = ~292,000 rows, 2 years daily OHLCV
```

### 1.2 Design source schema (Azure SQL — OLTP)
- [ ] 🔵 ME: Based on actual yfinance output, write `docs/schema/source-schema.md`
  - Normalised tables: `symbols`, `daily_prices`, `positions`, `corporate_actions`
  - Primary keys, foreign keys, indexes
  - Deliberately includes SQL Server patterns: stored procedure for position calc, identity columns, T-SQL types
- [ ] 🟡 YOU: Review and approve before any table is created

### 1.3 Design target schema (Snowflake — OLAP)
- [ ] 🔵 ME: Write `docs/schema/target-schema.md`
  - Denormalised: fact table `FACT_PRICES`, dimension tables `DIM_SYMBOL`, `DIM_DATE`
  - Snowflake-specific: VARIANT column for raw JSON, CLUSTER BY date, TIME_TRAVEL retention
  - Views for common analytical queries (portfolio value, rolling returns, sector aggregates)
- [ ] 🟡 YOU: Review and approve

**Key schema transformation to explain in interview:**
> Source: 3NF normalised (symbols + prices as separate tables, joined at query time)
> Target: denormalised star schema (single scan for aggregations, no joins needed)
> Why: Snowflake is columnar — wide tables with repeated data are cheaper than joins at scale

---

## Phase 2 — Part 1: FastAPI + Azure SQL → Snowflake + AKS (~3 hours build)

### Repo structure
```
part1-fastapi-aks/
├── app/
│   ├── main.py              # FastAPI app entry point
│   ├── config.py            # env vars, connection strings
│   ├── database/
│   │   ├── azure_sql.py     # SQLAlchemy engine for Azure SQL (source)
│   │   └── snowflake.py     # Snowflake connector (target)
│   └── routers/
│       ├── prices.py        # GET /prices — reads from Snowflake
│       ├── positions.py     # GET /positions — reads from Snowflake
│       └── migration.py     # POST /migrate — triggers migration run
├── migration/
│   ├── ingest.py            # yfinance → Azure SQL
│   ├── transform.py         # OLTP schema → OLAP schema (core logic)
│   ├── load.py              # transformed data → Snowflake (COPY INTO)
│   ├── validate.py          # row counts + checksum + business rules
│   └── rollback.py          # Snowflake TIME_TRAVEL rollback
├── tests/
│   ├── test_prices.py
│   ├── test_migration.py
│   └── test_validation.py
├── k8s/
│   ├── namespace.yaml
│   ├── secret.yaml          # Azure Key Vault reference (not hardcoded)
│   ├── deployment.yaml
│   └── service.yaml
├── Dockerfile
├── docker-compose.yml       # local dev only
├── requirements.txt
└── .env.example             # template — never commit .env
```

### 2.1 Bootstrap
- [ ] 🔵 ME: `requirements.txt`, `.env.example`, `docker-compose.yml`
- [ ] 🔵 ME: `app/config.py` — loads all env vars, fails fast if any missing
- [ ] 🟡 YOU: Copy `.env.example` → `.env`, fill in credentials from Phase 0

### 2.2 Ingest — yfinance → Azure SQL
- [ ] 🔵 ME: `migration/ingest.py`
  - Pulls yfinance data for 20 symbols
  - Creates Azure SQL tables (from approved source schema)
  - Loads data with upsert (idempotent — safe to re-run)
  - Stored procedure: `sp_calculate_positions` — T-SQL, calculates market value from prices
- [ ] 🔵 ME: `tests/test_ingest.py` — verifies row counts, no nulls in key columns
- [ ] 🟡 YOU: Run ingest, verify in Azure SQL portal or via `sqlcmd`

### 2.3 Transform — OLTP → OLAP schema conversion
- [ ] 🔵 ME: `migration/transform.py`
  - Reads from Azure SQL (with `SNAPSHOT` isolation — consistent read, no locks)
  - Flattens normalised tables → star schema
  - Adds Snowflake-specific columns: `_loaded_at`, `_source_system`, `_batch_id`
  - Handles SQL Server → Snowflake type mapping (DATETIME2 → TIMESTAMP_NTZ, NVARCHAR → VARCHAR, etc.)
- [ ] 🔵 ME: `migration/load.py`
  - Writes to Snowflake using `COPY INTO` (not row-by-row inserts — interview talking point)
  - Stages data in Snowflake internal stage first, then copies
- [ ] 🔵 ME: `migration/validate.py`
  - Row count: source vs target
  - Checksum: SUM(close_price) source vs SUM(CLOSE_PRICE) target
  - Business rule: no future dates, no negative prices, no zero volume
- [ ] 🔵 ME: `migration/rollback.py`
  - Uses Snowflake TIME_TRAVEL: `SELECT * FROM FACT_PRICES AT(OFFSET => -3600)` to restore last known good state

### 2.4 FastAPI service
- [ ] 🔵 ME: `app/routers/migration.py` — `POST /migrate` triggers full ingest→transform→load→validate pipeline, returns job status
- [ ] 🔵 ME: `app/routers/prices.py` — `GET /prices?symbol=AAPL&from=2024-01-01` queries Snowflake
- [ ] 🔵 ME: `app/routers/positions.py` — `GET /positions?as_of=2024-12-31` returns portfolio snapshot
- [ ] 🔵 ME: `tests/test_prices.py`, `tests/test_migration.py` using pytest + httpx

**Bugs planted for debugging practice (find these during prep):**
1. `transform.py`: DATETIME2 → TIMESTAMP_NTZ conversion drops timezone info for market-open times
2. `routers/prices.py`: pagination offset uses `page * size` not `(page-1) * size`
3. `validate.py`: checksum comparison fails for float precision (0.001 tolerance needed)
4. `migration.py` router: returns 200 even when validation fails (should be 422)

### 2.5 Docker + AKS
- [ ] 🔵 ME: `Dockerfile`, `k8s/` manifests (namespace, secret, deployment, service)
- [ ] 🟡 YOU: Run AKS deployment commands from `docs/cli-reference/azure-commands.md`
  ```bash
  az aks create --resource-group cmia-rg --name cmia-aks --node-count 2
  az acr create --resource-group cmia-rg --name cmiaregistry --sku Basic
  docker build + push + kubectl apply
  ```
- [ ] 🟡 YOU: Verify `curl http://<AKS-IP>/health` returns 200

---

## Phase 3 — Part 2: Flask + Snowflake → Amazon RDS + AWS (~2.5 hours build)

### Repo structure
```
part2-flask-aws/
├── app/
│   ├── __init__.py          # Flask app factory
│   ├── config.py            # env vars
│   ├── database/
│   │   ├── snowflake.py     # Snowflake connector (source)
│   │   └── rds.py           # SQLAlchemy for Amazon RDS (target)
│   └── routes/
│       ├── pipeline.py      # POST /run-pipeline — triggers ETL
│       └── analytics.py     # GET /analytics — reads from RDS
├── etl/
│   ├── extract.py           # Snowflake → pandas (aggregated)
│   ├── transform.py         # OLAP aggregates → OLTP serving schema
│   ├── load.py              # pandas → RDS (bulk insert)
│   └── validate.py          # counts + checksums
├── tests/
│   ├── test_routes.py
│   └── test_etl.py
├── k8s/
│   ├── deployment.yaml
│   └── service.yaml
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

### 3.1 ETL pipeline (Snowflake → RDS)
- [ ] 🔵 ME: `etl/extract.py` — queries Snowflake for pre-aggregated analytics (sector returns, rolling volatility, top movers)
- [ ] 🔵 ME: `etl/transform.py` — reshapes OLAP output → normalised OLTP rows for RDS
- [ ] 🔵 ME: `etl/load.py` — bulk insert to RDS with dedup check (no duplicates on re-run)
- [ ] 🔵 ME: `etl/validate.py` — same pattern as Part 1 (counts + checksums)

### 3.2 Flask service
- [ ] 🔵 ME: `app/routes/pipeline.py` — `POST /run-pipeline` triggers ETL
- [ ] 🔵 ME: `app/routes/analytics.py` — `GET /analytics/sector-returns`, `/top-movers`, `/volatility`
- [ ] 🔵 ME: `tests/` — pytest + Flask test client

**Bugs planted:**
1. `routes/pipeline.py`: `@app.get` instead of `@app.post` (405 on trigger)
2. `etl/load.py`: no dedup → re-runs double all rows
3. `etl/transform.py`: division by zero when previous close is 0 (happens on IPO day)
4. `etl/load.py`: `db.commit()` in exception handler instead of `db.rollback()`

### 3.3 Docker + AWS deploy
- [ ] 🔵 ME: `Dockerfile`, `k8s/` or ECS task definition
- [ ] 🟡 YOU: Run AWS deployment commands from `docs/cli-reference/aws-commands.md`
  ```bash
  aws ecr create-repository --repository-name cmia-flask
  aws eks create-cluster OR aws ecs create-cluster
  docker build + push + deploy
  ```
- [ ] 🟡 YOU: Verify `curl http://<AWS-IP>/health` returns 200

---

## Phase 4 — Debugging Practice (YOU, ~2 hours)

This is the interview simulation. Do this on Day 3 or Day 4.

- [ ] 🟡 YOU: Read each buggy file, find the bug without being told which line
- [ ] 🟡 YOU: Fix it, run the test to confirm
- [ ] 🟡 YOU: For each bug, write one sentence: "The bug was X, I found it by Y, the fix was Z"

**8 bugs total across both parts (listed above in 2.4 and 3.2).** These are the same class of bugs Cindy Tam will probe in the interview.

---

## Phase 5 — CLI Reference Files (🔵 ME, ongoing)

Built incrementally as commands are used:

- `docs/cli-reference/azure-commands.md` — `az aks`, `az acr`, `az sql`, `az login`, etc.
- `docs/cli-reference/aws-commands.md` — `aws eks`, `aws ecr`, `aws rds`, `aws configure`, etc.
- `docs/cli-reference/snowflake-commands.md` — SnowSQL, `COPY INTO`, `TIME_TRAVEL`, `SHOW TABLES`, etc.
- `docs/cli-reference/docker-k8s-commands.md` — `docker build/push`, `kubectl apply/get/logs/describe`, etc.

---

## Summary of who does what

| Phase | Owner | Prerequisite |
|---|---|---|
| 0 — Cloud setup | YOU | Nothing — start here |
| 1 — Data exploration | ME builds, YOU runs + reviews | Phase 0 done |
| 2.1–2.2 — Ingest | ME builds | Phase 1 approved |
| 2.3–2.4 — Migration + API | ME builds | Phase 2.2 done |
| 2.5 — AKS deploy | YOU runs commands | Phase 2.4 done |
| 3.1–3.2 — ETL + Flask | ME builds | Phase 2 done + AWS decision made |
| 3.3 — AWS deploy | YOU runs commands | Phase 3.2 done |
| 4 — Debug practice | YOU | Both parts built |

---

## Interview talking points this project gives you

### When Mark asks about migration approach
> "The source was Azure SQL — OLTP, normalised 3NF schema, T-SQL stored procedures for position calculations. The target was Snowflake — OLAP, denormalised star schema, columnar storage. The migration wasn't just a data copy: the schema changed because the query pattern changed. In Azure SQL we joined symbols to prices at query time. In Snowflake we pre-flatten that so a single table scan gives you the full portfolio without joins — that's what makes Snowflake fast for analytics."

### When Mark asks about validation
> "Three layers: row counts (source vs target must match), checksum on close price sum (financial correctness), and business rules — no future dates, no negative prices, no missing symbols from the source list. If any check fails the migration rolls back using Snowflake TIME_TRAVEL to the previous clean state."

### When Mark asks about rollback
> "Snowflake TIME_TRAVEL lets you query any table as it existed up to 90 days ago. So the rollback is: drop the current target tables, recreate from the TIME_TRAVEL snapshot at offset -3600 seconds. That's deterministic and testable — I can write a test that intentionally corrupts the target and verifies the rollback restores the correct checksum."

### When Cindy asks about a bug you fixed
> Use one of the 8 planted bugs. Format: what the symptom was, how you isolated it (which test failed, what the error said), what the root cause was, what the fix was, how you verified the fix didn't break anything else.

---

## What is NOT in this plan (and why)

| Excluded | Reason |
|---|---|
| EKS as Part 1 target | Not in JD — OTPP is Azure-first |
| SQLite as source | Not a real database server — doesn't simulate SQL Server |
| Synthetic seed data | Violates data-first principle |
| CAP as primary DB selector | Wrong lens for migration project — ACID + OLTP/OLAP is correct framing |
| LeetCode problems | Covered separately in daily prep — not part of this project |
