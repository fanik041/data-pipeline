# Requirements Analysis — Data Migration Project
_Critical breakdown before any implementation decisions are locked in._

---

## What the user said (verbatim decomposition)

1. "use a public data source for our data"
2. "host the data in a free tool somewhere or in Azure/AWS"
3. "build the code around the data"
4. "for DB we need to use CAP method to show seniority"
5. "Kaggle for demo data but if you have any other option"
6. "FastAPI + AKS" and "Flask + EKS" as the two deployment targets

---

## Statement-by-statement analysis

---

### 1. "Use a public data source"

**What it means:** Real-world data instead of synthetic seed data.

**Why it's RIGHT:**
- Real data has authentic messiness: nulls, encoding quirks, inconsistent types, duplicates. This is exactly what a migration project should exercise.
- More credible in an interview — you can say "I used real market data from X" and show actual outputs.
- Demonstrates data-first thinking, which is senior behaviour.

**What's missing from this statement:** Type of data. For OTPP / CMIA context the relevant domain is capital markets — so we want stock prices, portfolio positions, or trade history. A generic public dataset (e.g. Titanic, Iris) would look disconnected from the role.

**Options ranked for OTPP relevance:**

| Source | Type | Free? | Requires key? | Best for |
|--------|------|--------|---------------|----------|
| **yfinance** (Yahoo Finance) | Live OHLCV, options, dividends | Yes | No | Stock prices, portfolio positions |
| **Alpha Vantage** | OHLCV, fundamentals, forex | Yes (500/day) | Yes (free) | Structured time-series |
| **FRED** (Federal Reserve) | Rates, macro, inflation | Yes | No | Economic context |
| **Kaggle datasets** | Static CSVs, varies | Yes | Account needed | Historical bulk data |
| **SEC EDGAR** | 10-K/10-Q filings | Yes | No | Company financials |

**Recommendation: yfinance.** No API key, Python-native, returns pandas DataFrames directly, covers OHLCV for any symbol + options chains + fundamentals. Can simulate a realistic CMIA positions table with real prices.

---

### 2. "Host the data in a free tool or Azure/AWS"

**This statement is ambiguous and that ambiguity matters.**

A migration project has TWO databases:
- **Source DB** (the legacy system being migrated FROM)
- **Target DB** (where data lands after migration)

"Host the data" probably refers to the source, but this needs to be explicit. The architecture is completely different depending on the answer.

**Sub-analysis — Source DB hosting options (free tier):**

| Platform | DB type | Free limit | Best for |
|----------|---------|-----------|---------|
| **Supabase** | PostgreSQL | 500 MB, 2 projects | Source DB, good DX |
| **Neon.tech** | Serverless PostgreSQL | 512 MB, 1 project | Source DB, fast spin-up |
| **CockroachDB Cloud** | Distributed PostgreSQL | 10 GB | CP system, interesting for CAP demo |
| **Railway** | PostgreSQL | $5 credit | Quick projects |
| **ElephantSQL** | PostgreSQL | 20 MB | Too small |

**Sub-analysis — Target DB options (most relevant to OTPP):**

| Platform | Type | Free? | OTPP Relevance |
|----------|------|--------|----------------|
| **Snowflake trial** | Cloud data warehouse (OLAP) | 30 days / $400 credit | ⭐⭐⭐ Highest — this is literally OTPP's platform |
| **Azure SQL / Azure PostgreSQL** | OLTP/OLAP | 12-month free tier | ⭐⭐ Good — AKS-native |
| **PostgreSQL on AKS/EKS** | OLTP | Free (compute cost only) | ⭐ Lower — not a real migration, just copy |
| **AWS RDS PostgreSQL** | OLTP | 12-month free tier | ⭐ Reasonable |

**Critical observation:** If the target is just PostgreSQL on AKS, you're migrating PostgreSQL → PostgreSQL. That's not a migration in the OTPP sense — it's a copy. OTPP is migrating OLTP systems → Snowflake (OLAP). The architectural story is fundamentally different.

**Recommendation:** Source = Supabase (free PostgreSQL, simulates legacy SQL Server). Target = Snowflake 30-day trial. This is the exact stack OTPP uses and the exact challenge the JD describes.

---

### 3. "Build the code around the data" (data-first architecture)

**This is CORRECT senior engineering thinking. Do not reverse it.**

The current plan (already written) got this backwards — it designed models and APIs first, then seeded synthetic data to fill them. That produces a project that demonstrates coding skill but not data engineering judgment.

The right sequence:
1. Identify and pull real data (yfinance → stock prices)
2. Inspect the actual data shape (dtypes, nulls, cardinality, edge cases)
3. Design source schema to match what the data actually looks like (not an idealised version)
4. Design target schema to serve the analytical queries we want
5. Write the migration + transformation logic between them
6. Build the API layer on top of the target schema

**Why this matters for the interview:** When Mark Segal asks "how did you design this?", answering "I looked at what the data actually contained and worked backwards" is a senior answer. Answering "I designed a schema and filled it with test data" is a junior answer.

---

### 4. "Use CAP method to show seniority"

**This is the statement that needs the most critical pushback.**

#### What CAP Theorem actually is

CAP (Brewer's Theorem, 2000) says: in a distributed system you can guarantee at most 2 of:
- **C**onsistency: every read sees the most recent write
- **A**vailability: every request gets a response
- **P**artition Tolerance: system works despite network partition

Modern nuance: you always need P (network partitions happen in reality), so the real tradeoff is C vs A under partition:
- **CP** systems: PostgreSQL (single-node), MySQL, MongoDB (default), CockroachDB, Spanner
- **AP** systems: Cassandra, DynamoDB (default), Couchbase, CouchDB

#### Why applying CAP to THIS project is problematic

**Problem 1: CAP is about distributed databases, not migration pipelines.**
If you run a single PostgreSQL instance (which is what most demo projects do), CAP is not really in play — there's no partition scenario. Citing CAP without a genuine distributed architecture underneath looks like name-dropping.

**Problem 2: For financial data, the answer is obvious and uninteresting.**
Financial positions require consistency. CAP → you choose CP → you choose PostgreSQL or similar. That's the right answer, but it doesn't require sophistication to reach it. Every engineer would make the same choice.

**Problem 3: Snowflake doesn't fit neatly into CAP.**
Snowflake is a cloud data warehouse, not a traditional distributed database in the CAP sense. It's backed by cloud object storage (S3/ADLS), has separate compute, and is optimised for OLAP. Framing Snowflake through CAP is a category mismatch.

#### What ACTUALLY shows seniority for this context

These concepts are more directly applicable and more impressive:

**ACID vs BASE:**
- ACID (Atomic, Consistent, Isolated, Durable): PostgreSQL, SQL Server, Oracle → needed for source OLTP
- BASE (Basically Available, Soft-state, Eventually consistent): Cassandra, DynamoDB → not appropriate for financial positions
- For migration: the source must be ACID; the target's consistency model is a design decision

**OLTP vs OLAP (the most relevant concept for this project):**
- OLTP (Online Transaction Processing): normalised schema, row-based, optimised for writes and point lookups → SQL Server, PostgreSQL
- OLAP (Online Analytical Processing): denormalised, columnar, optimised for aggregations and scans → Snowflake, BigQuery, Redshift
- This is EXACTLY the OTPP migration pattern: moving from OLTP systems to Snowflake (OLAP)
- Designing for this tradeoff (and articulating why the schemas differ) is senior behaviour

**Isolation levels:**
- For migration: what isolation level do you use on the source during extraction? READ COMMITTED? REPEATABLE READ? SERIALIZABLE?
- For financial data mid-day: positions are changing. Do you snapshot at market close? Use a transaction to get a consistent read?

**Idempotency:**
- Can you re-run the migration without creating duplicates?
- This is a senior concern: if the migration fails halfway through, can you restart it?

**Schema evolution:**
- How do you handle added/removed columns in the source between migration runs?
- Alembic for versioned schema changes

#### How to mention CAP without looking shallow

If you want to mention CAP at OTPP, tie it to a specific scenario:
> "For the source PostgreSQL, I chose a CP system because financial positions require strong consistency — we can't afford stale reads when positions are backing trading decisions. An AP system like Cassandra would give us eventual consistency, which is unacceptable for this use case."

That's correct, credible, and shows you understand the tradeoff rather than just the terminology.

**Recommendation:** Lead with OLTP→OLAP distinction and ACID guarantees. Mention CAP in the context of source DB selection (CP for financial data). Don't let CAP drive the architecture.

---

### 5. "Kaggle for demo data"

**Feasible but suboptimal for this use case.**

**Kaggle pros:**
- Many financial datasets available (stock prices, company fundamentals, options)
- Realistic messy data
- Free download

**Kaggle cons:**
- Static files only — not a live "source system"
- Requires Kaggle account and API token (adds setup friction)
- Data may be outdated
- Doesn't simulate a live database being migrated

**Better alternative for the migration story:** Use yfinance to pull real stock data → load into the source database → then migrate it. This gives you:
- Live data (prices change, making the project dynamic)
- No API key friction
- Python-native (`pip install yfinance`)
- Realistic schema: OHLCV data + calculated positions

Good yfinance data to use:
```python
import yfinance as yf
# 2 years of daily prices for 20 symbols
symbols = ["AAPL","MSFT","GOOGL","AMZN","TSLA","JPM","GS","MS","BRK-B","BLK",
           "BAC","C","WFC","SCHW","CME","ICE","SPGI","MCO","BX","KKR"]
data = yf.download(symbols, start="2023-01-01", end="2024-12-31", group_by="ticker")
```

This gives ~14,000 rows per symbol × 20 symbols = 280,000 rows of real market data. Realistic, interesting, directly relevant to capital markets.

---

## Similarities found across statements

| Across statements | Pattern |
|---|---|
| Statements 3 + 5 | Both point to data-first design: pick data first, then build schema |
| Statements 2 + 4 | Both are about DB selection but from different angles (hosting vs theory) — these should be unified into one decision |
| Statements 1 + 3 | Both say the same thing: real data, not synthetic |
| CAP + OTPP JD | The JD mentions Snowflake explicitly. CAP and Snowflake don't map well — OLTP/OLAP is the right lens |

---

## What is RIGHT

- Data-first architecture thinking ✓
- Wanting real public data ✓
- Wanting the project to be deployable (not just local) ✓
- Separating the two deployment targets (AKS vs EKS) ✓
- yfinance or Kaggle financial data ✓ (yfinance is better)

---

## What is FEASIBLE

| Decision | Feasibility | Caveat |
|---|---|---|
| yfinance as data source | Very feasible | No key, pip install, works today |
| Supabase as source DB | Very feasible | Free, instant setup, real PostgreSQL |
| Snowflake as target | Feasible | 30-day trial, most OTPP-relevant |
| Azure SQL as target | Feasible | 12-month free tier |
| PostgreSQL on AKS/EKS as target | Very feasible | Least impressive for OTPP story |
| Kaggle as source | Feasible | Extra setup (account + token) |
| CAP-driven DB choice | Technically feasible | But architecturally shallow for this project |

---

## What is WRONG

| Issue | Why |
|---|---|
| Current plan uses SQLite as source | SQLite is a file, not a database server. It doesn't simulate a legacy SQL Server/Oracle environment. Not a convincing migration story. |
| Current plan seeds synthetic data | Misses the data-first principle the user just stated |
| Applying CAP as the primary DB selection framework | CAP is for distributed systems design. For a migration project, ACID and OLTP→OLAP distinction are far more relevant and impressive |
| PostgreSQL → PostgreSQL migration | Not a real migration challenge. Same engine, same SQL dialect, no schema transformation needed. Doesn't resemble the OTPP use case at all. |
| Source and target are the same DB type | Doesn't demonstrate understanding of why Snowflake is different from OLTP databases |

---

## Options available (full comparison)

### Option A: yfinance → Supabase (source) → Snowflake (target)
**Stack:** yfinance + Supabase + Snowflake trial + FastAPI on AKS + Flask on EKS

- **Pro:** Most OTPP-relevant. Exactly mirrors what Mark Segal's team does. Shows OLTP→OLAP migration.
- **Pro:** All free (Supabase free tier + Snowflake $400 trial credit)
- **Pro:** Snowflake's SQL dialect differences from PostgreSQL give you real migration challenges to solve (stored procedures, semi-structured data, TIME_TRAVEL)
- **Con:** Snowflake trial expires in 30 days
- **Con:** Slightly more setup (Snowflake account + connector library)

### Option B: yfinance → Neon.tech (source) → Azure SQL (target)
**Stack:** yfinance + Neon.tech + Azure SQL + FastAPI on AKS + Flask on EKS

- **Pro:** Azure ecosystem coherence (AKS + Azure SQL = natural fit)
- **Pro:** Azure SQL free tier lasts 12 months
- **Pro:** Still a real migration (PostgreSQL → SQL Server dialect differences)
- **Con:** Less OTPP-specific than Snowflake
- **Con:** Azure SQL and PostgreSQL are different dialects but both OLTP — misses the OLAP story

### Option C: yfinance → Supabase (source) → PostgreSQL on AKS/EKS (target)
**Stack:** yfinance + Supabase + PostgreSQL + FastAPI on AKS + Flask on EKS

- **Pro:** Simplest setup, guaranteed to work, no trial expiry
- **Pro:** Fully free
- **Con:** Not a real migration — same engine, same SQL. Just a copy.
- **Con:** Won't demonstrate the OLTP→OLAP understanding that OTPP cares about

### Option D: Kaggle + Supabase (source) → Snowflake (target)
**Stack:** Kaggle dataset + Supabase + Snowflake + FastAPI on AKS + Flask on EKS

- **Pro:** Rich historical dataset, realistic messy data
- **Con:** Kaggle requires account setup and API token
- **Con:** Static data — no live prices
- **Con:** Adds friction without meaningful benefit over yfinance

---

## Recommendation

**Go with Option A: yfinance → Supabase → Snowflake → FastAPI on AKS + Flask on EKS**

Reasoning:
1. yfinance is the lowest friction real-data option — zero setup, Python-native, live market data
2. Supabase simulates a legacy PostgreSQL/SQL Server source — free, real network database, not a local file
3. Snowflake is literally what OTPP is migrating to. When Mark Segal asks "have you worked with Snowflake?", you have a real answer.
4. The OLTP (Supabase/PG) → OLAP (Snowflake) distinction gives you an intelligent answer to "why did you choose these databases" without needing to stretch CAP theorem into places it doesn't fit
5. AKS and EKS remain the deployment targets exactly as planned

**DB selection talking point for the interview:**
> "I used PostgreSQL as the source because it's a CP system with full ACID guarantees — appropriate for operational data where every position needs to be consistent. For the target I chose Snowflake because the query pattern shifted from transactional point-lookups to analytical aggregations across the whole portfolio — that's exactly the OLTP-to-OLAP migration pattern. The schema design changed significantly: the normalised OLTP schema became a denormalised fact/dimension structure in Snowflake to optimise for scan performance."

That answer demonstrates CAP awareness, ACID understanding, OLTP/OLAP distinction, and schema design — all in three sentences.

---

## What needs to be decided before building

One decision gates everything else: **Target database.**

If Snowflake → architecture, schema, ETL code, and Snowflake-specific features (ELT vs ETL, VARIANT columns, TIME_TRAVEL, COPY INTO) all change.

If Azure SQL / plain PostgreSQL → different story, different schema transformations.

This single decision determines more about the project than any other choice.

---
_Document created: 2026-04-14. Analysis complete. Awaiting target DB decision before revising implementation plan._
