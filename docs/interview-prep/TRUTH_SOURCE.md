# OTPP Interview — Truth Source
> Single source of truth for all prep decisions. Do not override with assumptions.
> Last updated: 2026-04-14

---

## 1. The Role

**Title:** Senior Developer Python/SQL  
**Company:** Ontario Teachers' Pension Plan Board (OTPP)  
**Team:** Capital Market Investment Analytics (CMIA)  
**Recruiter vendor:** Procom  
**Interview format:** 1.5 hour in-person, panel (2 interviewers), pseudocode exercises confirmed by recruiter

---

## 2. The Interviewers

### Mark Segal — Senior Manager
- Ex-AWS background
- Cloud transformation, DevOps, delivery frameworks
- AI + data engineering focus
- Has worked with financial systems and quant strategies
- **What he tests:** cloud migration thinking, architecture decisions, DevOps maturity, delivery + reliability, tradeoffs over syntax
- **Does NOT care about:** reversing linked lists, LeetCode tricks

### Cindy Tam — Lead Software Developer
- 13 years engineering, degree in Math + CS
- Long-term OTPP engineer, hands-on coder
- Strong fundamentals
- **What she tests:** clean code, edge cases, SQL correctness, debugging, thinking under pressure

---

## 3. What the role actually is

Not a generic backend role. Three distinct workstreams:

| Workstream | What it means |
|---|---|
| Data migration | Move SQL Server / Oracle databases + stored procedures → Snowflake |
| Script migration | Move Python analytics scripts → Azure AKS (containerised) |
| App migration | Move React/Django web apps → Azure AKS |

**The CMIA team supports:** trading systems, execution systems, investment research systems. Correctness and reliability matter more than cleverness.

---

## 4. Migration direction (verified from JD)

```
FROM (legacy)                     TO (cloud)
─────────────────────────────     ──────────────────────────────
SQL Server / Oracle (data)   →    Snowflake  (data warehouse)
Python scripts (bare metal)  →    Azure AKS  (containerised)
React/Django apps            →    Azure AKS  (containerised)
Stored procedures            →    Snowflake  (rewrite required)
```

**Not Snowflake → Azure. Not Azure → Snowflake. Both are targets, from separate legacy sources.**  
EKS (AWS) does not appear in the JD. Azure is the cloud. Snowflake is the data warehouse.

---

## 5. Must-know tech (from JD, in priority order)

| Priority | Technology | Why |
|---|---|---|
| 1 | Python | Core language, pipelines, analytics scripts |
| 2 | SQL (T-SQL / Snowflake SQL) | Core language, queries, migrations |
| 3 | Snowflake | Migration target, data warehouse |
| 4 | Azure AKS | Deployment target for scripts + apps |
| 5 | Docker / Kubernetes | Containerisation for AKS deployment |
| 6 | SQL Server / Oracle | Source systems being migrated from |
| 7 | Git / Jenkins | CI/CD, DevOps |
| 8 | Flask / FastAPI | Nice to have, web frameworks |
| 9 | Airflow / DBT / SSIS | Nice to have, data engineering tools |
| 10 | PowerBI | Nice to have, reporting |

---

## 6. Interview structure (predicted with high confidence)

| Time | Segment | Led by |
|---|---|---|
| 0–15 min | Intro + resume walkthrough + why OTPP | Both |
| 15–40 min | Deep project grilling: migration, pipelines, failures, tradeoffs | Mark |
| 40–70 min | Technical: Python pseudocode or SQL (similar difficulty to round 1) | Cindy |
| 70–85 min | System/migration design discussion: Snowflake, AKS, validation, rollback | Mark |
| 85–90 min | Behavioural + your questions | Both |

---

## 7. What round 1 looked like (your actual signal)

- Python: greedy problem
- SQL: filtering (odd IDs), COALESCE usage
- Follow-up: explain your approach, debug output, justify SQL choices
- Takeaway: they care about reasoning and communication, not just the answer

Round 2 (in-person) will be same style but:
- More emphasis on real-world project stories
- Migration and system thinking added
- Slightly more practical SQL (window functions possible)
- Debugging broken code is likely (not just write from scratch)

---

## 8. The hidden rubric — what they are actually evaluating

1. **Can you build real systems?** Not toy problems. Real pipelines with real edge cases.
2. **Can you migrate legacy → cloud?** This is literally the job description.
3. **Can you think like a production engineer?** Validation, rollback, monitoring, reliability.
4. **Can you work with finance people?** Traders and analysts are your users, not engineers.
5. **Can you communicate precisely?** Round 1 already tested this. Round 2 will test it harder.

---

## 9. DB selection — correct framing (NOT just CAP)

**Wrong approach:** "I chose PostgreSQL because of CAP theorem."  
**Right approach:**

> "I used PostgreSQL as the source because it's a CP system — financial positions need strong consistency, you can't tolerate stale reads when those positions back trading decisions. For the target I chose Snowflake because the query pattern shifts from transactional point-lookups to analytical aggregations across the whole portfolio. That's the OLTP-to-OLAP migration pattern — the normalised source schema becomes a denormalised fact/dimension structure in Snowflake to optimise for scan performance."

Key concepts to demonstrate:
- **ACID vs BASE** — financial data requires ACID (PostgreSQL/SQL Server), not BASE (Cassandra)
- **OLTP vs OLAP** — the migration is about changing query patterns, not just moving data
- **CAP** — mention it briefly for source DB choice (CP = PostgreSQL = right), then move on
- **Idempotency** — can the migration be re-run safely?
- **Isolation levels** — what isolation do you use on source during extraction?

---

## 10. Four stories you must prepare

Each story should follow: situation → what you owned → what went wrong or was hard → what you decided → how you validated → outcome.

| Story | What it covers |
|---|---|
| **Migration story** | Old system → new system. Focus on validation, rollback, business continuity. |
| **Pipeline story** | Python + SQL together. Data flow, edge cases, failures, monitoring. |
| **Debugging story** | Something broke in production or testing. How you diagnosed and fixed it. |
| **Stakeholder story** | Explaining technical decisions to non-technical users (traders / analysts). |

---

## 11. Four-day prep plan

### Day 1 (today) — Foundation
- 20 Python problems: arrays, hashmap, strings, greedy, sliding window
- 3 hrs SQL: JOINs, GROUP BY, CASE WHEN, COALESCE, window functions, nulls
- 4 hrs system design: design a data pipeline (ingest → transform → store → query)
- 2 hrs migration basics: Snowflake vs PostgreSQL, ETL vs ELT, AKS intro

### Day 2 — Real engineering
- 4 hrs: Build mini pipeline (Python → fetch data → store in DB → query via SQL)
- 3 hrs: Debugging practice (broken code → fix → explain)
- 3 hrs: Migration deep dive (SQL Server → Snowflake, stored procedures, validation)
- 2 hrs: 8 problem review + 1 SQL
- 2 hrs: System design ("analytics platform for trading data")

### Day 3 — Cloud + AKS
- 4 hrs: AKS / Docker (image, deployment, scaling, logs)
- 3 hrs: Python deep dive (dict/set mastery, edge cases, clean structure)
- 3 hrs: Data validation (row counts, checksums, sampling, business validation)
- 2 hrs: 8 problem review
- 2 hrs: System design ("migration system on-prem → cloud")

### Day 4 — Simulation
- 4 hrs: Full mock interview (30 min project discussion + 30 min coding + 30 min migration)
- 3 hrs: Fix weak areas
- 3 hrs: SQL + Python polish
- 2 hrs: Behavioural prep (4 stories above)
- 2 hrs: Light review

### Day 5 (interview day, 11am)
- Morning: review notes, 2–3 easy problems, NO heavy studying

---

## 12. Biggest mistakes to avoid

| Mistake | Why it's fatal |
|---|---|
| Talking only at high level | They will drill into specifics. "We migrated to the cloud" is not an answer. |
| LeetCode-only prep | This is a migration/data engineering interview, not a FAANG screen |
| Not mentioning validation | For financial systems, "it works" means nothing without proof. Always mention checksums, row counts, business validation. |
| Not mentioning rollback | Every migration answer needs a rollback plan. This is non-negotiable in finance. |
| Sounding like a generic dev | You must sound like an investment data engineer who happens to code, not a coder who happens to touch finance. |

---

## 13. Winning mindset to carry into the room

> "I'm not just a developer. I build reliable data systems that support decision-making at scale."

Every answer should reinforce: correctness, reliability, tradeoffs, communication, business impact.

---

## 14. Project being built for prep (status)

**Goal:** Stock signal/prediction API (FastAPI) with a DB migration exercise underneath it.

**The narrative:** "We had a running FastAPI app backed by Azure SQL. We migrated the data to Snowflake and re-pointed the same API via a backend flag — same endpoints, same queries, faster results, no data loss. That's the migration validated."

**Data source:** yfinance — 15,040 rows, 20 symbols, 2022–2024, OHLCV + 10 technical indicators  
**Source DB:** Azure SQL (`cmia-source-db` on `cmia-source-server.database.windows.net`) — simulates legacy SQL Server  
**Migration target:** Snowflake (`CMIA_DW`) — OLAP star schema, already DDL'd  
**Deployment:** Azure AKS (`cmia-aks`, Central US) + ACR (`cmiaregistry.azurecr.io`)  
**CI/CD:** GitHub Actions → ACR → AKS

**FastAPI endpoints (6):**
1. `GET /health` — liveness probe
2. `GET /symbols` — all symbols with sector info
3. `GET /prices/{symbol}` — OHLCV time series
4. `GET /predict/{symbol}` — latest technical signals + next_day_up label
5. `GET /sector/{sector}` — all symbols in sector with latest signal
6. `GET /summary/{symbol}` — latest price + signal + sector metadata in one call

**DB backend flag:** `DB_BACKEND=azure|snowflake` env var — same API, swappable backend. Used to compare performance pre/post migration.

**What's done:**
- All Azure SQL DDL run in portal (schemas, tables, indexes, RLS, views)
- All Snowflake DDL run in UI (warehouses, dims, facts, views, tasks)
- Data ingested to Azure SQL (ingest running as of 2026-04-14 session 4)
- `scripts/ingest_to_azure_sql.py` — uses `pymssql`, idempotent IF NOT EXISTS

**What's next:**
1. Build FastAPI app → wire to Azure SQL
2. Run migration script (Azure SQL → Snowflake)
3. Add Snowflake backend, test same endpoints
4. Compare response times → that's the migration payoff story
