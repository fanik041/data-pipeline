# Project Status
_Updated: 2026-04-14 — session 4 (end of session — user left)_

---

## What this project is

Interview prep for OTPP Senior Developer Python/SQL role.
Interview: **2026-04-15 at 11am**, in-person, 1.5 hours.
Interviewers: Mark Segal (Senior Manager, ex-AWS, cloud/migration) + Cindy Tam (Lead Dev, 13yr, Math/CS, clean code/debugging).
Full context: `docs/interview-prep/TRUTH_SOURCE.md`

---

## Architecture (locked — do not change)

```
yfinance (live market data)
        │
        ▼
  Azure SQL (OLTP source)          ← Part 1 source, simulates legacy SQL Server
        │
        │  FastAPI migration service (Part 1)
        ▼
  Snowflake (OLAP target)          ← Part 1 target + Part 2 source
        │
        │  Flask ETL pipeline (Part 2)
        ▼
  Amazon RDS PostgreSQL (OLTP)     ← Part 2 target

  Deployment: both parts on Azure AKS
  CI/CD: GitHub Actions → builds Docker image → pushes to ACR → deploys to AKS
```

---

## What is DONE

### Data
- `data/raw/prices_raw.csv` — 15,040 rows, OHLCV for 20 symbols, 2022–2024
- `data/raw/prices_features.csv` — 15,040 rows, OHLCV + 10 technical indicators + ML target label
- `data/raw/benchmarks.csv` — 3,760 rows, SPY/QQQ/IEF/GLD/TLT daily close
- `data/raw/company_metadata.csv` — 20 rows, sector/industry/market_cap per symbol
- Script: `scripts/extract_data.py` (already fixed bb_lower bug — good debugging story)

### DB Infrastructure — Azure SQL (11 files total, 1,531 lines)
- `db/azure-sql/01_schemas.sql` — 5 schemas: market, ref, audit, rls, reports
- `db/azure-sql/02_tables.sql` — 6 tables (sectors, symbols, daily_prices, price_features, benchmark_prices, user_sector_access, etl_log)
- `db/azure-sql/03_indexes.sql` — 8 indexes with documented query patterns
- `db/azure-sql/04_rls.sql` — Inline TVF predicate + SECURITY POLICY. Roles: cmia_admin, cmia_analyst
- `db/azure-sql/05_stored_procedures.sql` — sp_upsert_daily_prices (MERGE), sp_get_symbol_time_series, sp_get_migration_extract (watermark pattern), sp_log_etl_start/end
- `db/azure-sql/06_views.sql` — v_daily_prices_enriched, v_latest_features, v_sector_summary (checksum col)

### DB Infrastructure — Snowflake
- `db/snowflake/01_setup.sql` — 2 warehouses, database CMIA_DW, 5 schemas, 4 roles
- `db/snowflake/02_dimensions.sql` — DIM_SECTOR, DIM_SYMBOL, DIM_DATE (auto-populated)
- `db/snowflake/03_facts.sql` — FACT_PRICES, FACT_FEATURES, FACT_BENCHMARKS, RAW landing, AUDIT log
- `db/snowflake/04_rls.sql` — Row Access Policy + Column Masking Policy on market_cap
- `db/snowflake/05_views_and_marts.sql` — enriched views, QUALIFY window, MART_ROLLING_RETURNS, Snowflake Task

### Azure SQL DDL — all 6 files run in portal Query Editor ✅
- `01_schemas.sql` — 5 schemas created (market, ref, audit, rls, reports)
- `02_tables.sql` — 7 tables created
- `03_indexes.sql` — 11 indexes created (partial run; portal confirmed duplicates = already exists)
- `04_rls.sql` — roles, grants, predicate function, security policies, seed data
- `05_stored_procedures.sql` — run ✅
- `06_views.sql` — run ✅

### Snowflake DDL — all 5 files run in Snowflake UI ✅
- All warehouses, databases, schemas, dimensions, facts, views, tasks created

### Cloud Infrastructure
- **Azure SQL instance** — `cmia-source-db` on `cmia-source-server.database.windows.net` ✅
- **AKS cluster** — `cmia-aks`, Central US, 1 node (Standard_D2ps_v6), Free tier ✅
- **ACR** — `cmiaregistry.azurecr.io`, Basic SKU, linked to AKS ✅
- `.env.example` — all fields defined (Azure SQL, Snowflake, RDS, AKS, ACR) ✅
- `.gitignore` — created, `.env` excluded ✅

### Docs
- `docs/interview-prep/TRUTH_SOURCE.md` — ground truth, read before every session
- `docs/superpowers/specs/2026-04-14-requirements-analysis.md` — full architecture analysis
- `docs/superpowers/plans/2026-04-14-implementation-plan-v2.md` — full plan with owner labels
- `CLAUDE.md` — project rules, 3-layer doc standard, CLI reference paths
- `docs/superpowers/plans/2026-04-14-data-migration-project.md` — **SUPERSEDED, ignore**

---

## What is NEXT (priority order)

### 1. Run ingest scripts — IN PROGRESS (session 4)
- [x] Switched from `pyodbc` + `msodbcsql18` (brew bottleneck) → `pymssql` (pure pip) ✅
- [x] `.venv/bin/pip install pymssql` ✅
- [x] `scripts/ingest_to_azure_sql.py` updated: all `pyodbc` → `pymssql`, `?` → `%s` placeholders ✅
- [x] Discovered `sp_upsert_daily_prices` was never created in portal — replaced with direct IF NOT EXISTS INSERT ✅
- [x] Fixed column mismatches: `market_cap_usd` → `market_cap`, added `symbol_code` to prices + features INSERTs ✅
- [x] Sample test (3 rows AAPL) passed — prices + features both clean ✅
- [ ] **Full ingest running** — prices (15,040 rows) in progress as of session end
- [ ] FastAPI migration service moves data Azure SQL → Snowflake (step 2)

### CLAUDE SCREWUP LOG (so it doesn't happen again)
- Ran `pip install` against system Python before venv was activated — contaminated base Python
- Ran `brew install msodbcsql18` in background multiple times → left stale lock at `/opt/homebrew/Cellar/msodbcsql18`
- Ran full 15K row ingest without sample-testing first — wasted time debugging live
- Fix: CLAUDE.md now requires **3-row sample test before any full ingest**
- Fix: CLAUDE.md now requires all Python installs go through `.venv/bin/pip` only

### 2. FastAPI stock prediction API — NEXT SESSION

**Design decisions locked (do not re-discuss):**
- 6 endpoints: `/health`, `/symbols`, `/prices/{symbol}`, `/predict/{symbol}`, `/sector/{sector}`, `/summary/{symbol}`
- DB backend switch: query param `?backend=azure|snowflake` (per-request, not env var restart)
- Same API hits both DBs — used to compare response times pre/post migration
- Azure SQL views: `reports.v_daily_prices_enriched`, `reports.v_latest_features`, `reports.v_sector_summary`
- Snowflake views: `CMIA_DW.MARTS.V_PRICES_ENRICHED`, `V_LATEST_FEATURES`, `V_SECTOR_DAILY_SUMMARY`
- `app/models.py` stub already created — do NOT rewrite, build on top of it

**Build order next session:**
1. Run `/production-feature-builder` to build the FastAPI app (wire to Azure SQL first)
2. Run migration script (Azure SQL → Snowflake) to populate Snowflake
3. Add Snowflake backend leg, test `?backend=snowflake`
4. Run `/fullstack-wiring-validator` to validate end-to-end
5. Compare timings — that's the migration payoff story
6. Dockerfile + AKS deployment

**Open questions for next session (brainstorming was cut short — need answers before building):**
1. **Date range for `/prices/{symbol}`** — return all 3 years by default, or last N days? Should there be `?start` / `?end` query params?
2. **`/predict/{symbol}` output** — just return the pre-computed `target_next_day_up` label from `price_features`, or also include a confidence score / signal summary? Keep it simple or add interpretation?
3. **Error handling on bad symbol** — return 404 with message, or empty list? Consistent across all endpoints?
4. **Snowflake credentials in `.env`** — are the Snowflake account/user/password/warehouse values already filled in `.env` (not just `.env.example`)? Need to confirm before wiring.
5. **Migration script** — `scripts/ingest_to_snowflake.py` exists but was it written this session or is it a stub? Need to verify it's runnable before relying on it.
6. **`app/models.py` stub** — I created it but got interrupted. Does the user want to review it before building on top of it, or just proceed?
7. **Response time comparison** — should timing be added as a response header (e.g. `X-Response-Time-Ms`) or logged server-side only?
8. **Auth** — any API key or is this fully open (it's a demo, so probably open — just confirm)?

### 3. GitHub Actions CI/CD (ME + YOU)
- ME: write `.github/workflows/deploy.yml`
- YOU: create service principal + add GitHub secrets

### 4. React UI skeleton (ME)
- Hosted on Azure Static Web Apps (free tier)

### 5. Part 2 — deferred
- Flask ETL: Snowflake → AWS RDS PostgreSQL
- AWS RDS setup

### 3. GitHub Actions setup (after apps are built)
- Create service principal: `az ad sp create-for-rbac --name "cmia-github-actions" --role contributor --scopes /subscriptions/<id> --sdk-auth`
- Add GitHub repo secrets: `AZURE_CREDENTIALS`, `ACR_LOGIN_SERVER`, `ACR_USERNAME`, `ACR_PASSWORD`
- Workflow triggers on push to `main` → builds image → pushes to ACR → applies k8s manifests to AKS

---

## Key interview talking points this codebase gives you

1. **On migration approach:** "Source was Azure SQL — OLTP, normalised 3NF, T-SQL stored procs. Target is Snowflake — OLAP, denormalised star schema, CLUSTER BY for micro-partition pruning. The schema changed because the query pattern changed."
2. **On RLS:** "Azure SQL uses inline TVF predicates with SECURITY POLICY — must be schema-bound for performance. Snowflake uses Row Access Policy objects attached to tables, plus separate Column Masking for sensitive fields like market_cap."
3. **On validation:** "Three layers: row counts, SUM(close_price) checksum (same view exists in both DBs for direct comparison), business rules (no negative prices, no future dates)."
4. **On the bb_lower bug:** "I had a NameError — used `bb_lower` as a local variable but I'd only assigned it as `grp['bb_lower']`. Found it by reading the traceback, fixed by using the DataFrame column reference consistently."
5. **On CI/CD:** "GitHub Actions builds the Docker image on every push to main, pushes to ACR, then applies kubectl manifests to AKS. The service principal has contributor scope on the subscription."
6. **On AKS choice:** "Chose AKS over EKS because both services run in Azure — keeps network latency low between the migration service and Azure SQL source, and simplifies IAM since everything is in one cloud."

---

## Decisions still open
- GitHub repo — needs to exist for GitHub Actions to work. Create if not already done.
