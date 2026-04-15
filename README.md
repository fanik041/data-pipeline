# CMIA — Capital Markets Intelligence & Analytics

A full-stack stock prediction and database migration demo built for a senior engineering interview context.
Ingests OHLCV price data and technical indicators for 20 S&P 500 equities, surfaces next-day BUY/SELL signals via a rule-based ML pipeline, and lets you compare query latency between an Azure SQL (OLTP) source and a Snowflake (OLAP) target in real time.

---

## What It Does

| Layer | What happens |
|-------|-------------|
| **Ingest** | `yfinance` pulls 2 years of OHLCV data for 20 symbols and loads it into Azure SQL |
| **Feature engineering** | RSI-14, MACD, Bollinger Band position, 5/20-day MAs, 20-day volatility computed per symbol |
| **Prediction** | Rule-based signal: RSI + MACD crossover → BUY / SELL label stored in `reports.v_latest_features` |
| **Migration** | Same schema mirrored to Snowflake CMIA_DW; identical queries run on both DBs for latency comparison |
| **API** | FastAPI service with a `?backend=azure\|snowflake` switch on every endpoint |
| **Frontend** | React SPA — login, dashboard, market chart, ML predictor, sector explorer, live DB comparison |

---

## Architecture

```
yfinance
   │
   ▼
Azure SQL (OLTP)              ← source of truth, row-store
   │  ref.symbols / ref.sectors
   │  prices.daily_prices
   │  features.technical_indicators
   │  reports.v_*  (views)
   │
   ├── FastAPI  (:8000)       ← Python migration/query service
   │      │  ?backend=azure|snowflake
   │      ▼
   │   Snowflake (OLAP)       ← CMIA_DW.MARTS.V_*  columnar target
   │
   └── React + Vite  (:5173)  ← dark trading terminal UI
```

---

## Tech Stack

- **Python 3.11** — FastAPI, pymssql, snowflake-connector-python, yfinance, pandas, scikit-learn
- **Azure SQL** — OLTP source DB (row-store, normalised schema)
- **Snowflake** — OLAP target DB (columnar, micro-partition pruning)
- **React 18** + Vite — frontend SPA
- **Recharts** — interactive price charts
- **Lucide React** — icon set
- **pytest + httpx** — API test suite (15 tests)
- **Docker + AKS** — containerised backend deployed on Azure Kubernetes Service
- **Azure Container Registry** — private Docker image registry
- **Azure Static Web Apps** — frontend CDN hosting with GitHub Actions CI/CD

---

## Cloud Deployment

### Architecture

```
GitHub (push to main)
   │
   ├── GitHub Actions: deploy-backend.yml
   │       ├── docker build + push → ACR (cmiaregistry.azurecr.io)
   │       └── kubectl set image  → AKS (cmia-aks)
   │                                     └── Pod: cmia-api
   │                                           └── Service: LoadBalancer → public IP
   │
   └── GitHub Actions: azure-static-web-apps-*.yml (auto-generated)
           └── npm run build → Azure Static Web Apps (cmia-frontend)
                                     └── /api/* proxy → AKS public IP
```

### Frontend — Azure Static Web Apps

1. Create the resource in the portal (`cmia-frontend`, Free tier, `cmia-source-db` RG)
2. Connect to GitHub: `fanik041/data-pipeline`, branch `main`
3. Build settings: App location `app/frontend`, Output location `dist`, API location blank
4. Azure auto-commits a workflow file to your repo — every push to `main` redeploys

### Backend — Docker + ACR + AKS

#### One-time infrastructure setup

```bash
# Create ACR
az acr create --name cmiaregistry --resource-group cmia-source-db \
  --sku Basic --admin-enabled true

# Create AKS (1 node is enough for a demo)
az aks create --name cmia-aks --resource-group cmia-source-db \
  --node-count 1 --node-vm-size Standard_B2s \
  --attach-acr cmiaregistry --generate-ssh-keys

# Pull credentials so kubectl works locally
az aks get-credentials --name cmia-aks --resource-group cmia-source-db
```

#### First manual deploy

```bash
# Build and push image to ACR
az acr login --name cmiaregistry
docker build -t cmiaregistry.azurecr.io/cmia-api:latest .
docker push cmiaregistry.azurecr.io/cmia-api:latest

# Fill in k8s/secret.yaml (base64-encode each value: echo -n "value" | base64)
# then apply all manifests
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml

# Watch pod come up, then get the public IP
kubectl get pods -w
kubectl get service cmia-api-svc   # copy EXTERNAL-IP — this is your backend URL
```

#### CI/CD (subsequent deploys)

Add these secrets to GitHub repo → Settings → Secrets:

| Secret | Where to get it |
|--------|----------------|
| `ACR_USERNAME` | Portal → Container registries → cmiaregistry → Access keys |
| `ACR_PASSWORD` | Same page |
| `KUBE_CONFIG` | `cat ~/.kube/config \| base64` after running `az aks get-credentials` |

After that, every push to `main` that touches `app/`, `Dockerfile`, or `k8s/` triggers `.github/workflows/deploy-backend.yml` — it builds a new image tagged with the git SHA and does a zero-downtime rolling update on AKS.

#### Key Kubernetes files

| File | Purpose |
|------|---------|
| `Dockerfile` | Builds the FastAPI image on `python:3.11-slim` |
| `k8s/secret.yaml` | DB credentials — never baked into the image |
| `k8s/deployment.yaml` | Runs 1 replica, readiness/liveness probes on `/health` |
| `k8s/service.yaml` | LoadBalancer — Azure provisions a public IP |

---

## Local Setup

### 1. Clone & create virtual environment

```bash
git clone https://github.com/fanik041/data-pipeline
cd data-pipeline
python3 -m venv .venv
source .venv/bin/activate
.venv/bin/pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env   # fill in Azure SQL and Snowflake credentials
```

### 3. Ingest data into Azure SQL

```bash
.venv/bin/python app/scripts/ingest_to_azure_sql.py
```

### 4. Start the FastAPI backend

```bash
uvicorn app.main:app --reload --port 8000
# API docs: http://localhost:8000/docs
```

### 5. Start the React frontend

```bash
cd app/frontend
npm install
npm run dev
# Open: http://localhost:5173
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | DB connectivity check |
| GET | `/symbols?backend=azure` | All tracked symbols + sectors |
| GET | `/prices/{symbol}?backend=azure&start=YYYY-MM-DD&end=YYYY-MM-DD` | OHLCV history (default last 14 days) |
| GET | `/predict/{symbol}?backend=azure` | Latest technical indicators + BUY/SELL signal |
| GET | `/sector/{sector}?backend=azure` | All symbols in a sector |
| GET | `/summary/{symbol}?backend=azure` | Signal summary with MACD interpretation |
| POST | `/auth/login` | Validate credentials, returns bearer token |

Add `?backend=snowflake` to any read endpoint to hit the OLAP target instead.

---

## Running Tests

```bash
source .venv/bin/activate
pytest tests/ -v
```

All 15 tests pass — health checks, CRUD flows, 404 handling, and lowercase symbol normalisation.

---

## UI Screenshots

> **Note:** Screenshots require the `docs/screenshots/` PNGs to be committed to git. Run `git add docs/screenshots/ && git commit` if they don't appear on GitHub.

### Login
![Login](docs/screenshots/login.png)

### Dashboard
Loads all 20 symbols, computes BUY/SELL distribution, top bullish signals, and sector breakdown.

![Dashboard](docs/screenshots/dashboard.png)

### ML Predictor
Select any symbol to see RSI, Bollinger Band position, MACD crossover, moving averages, and next-day direction signal.

![Predictor](docs/screenshots/predictor.png)

### DB Comparison
Runs the same query against Azure SQL and Snowflake simultaneously. Demonstrates the OLTP → OLAP migration payoff: Snowflake's micro-partition pruning returns analytical queries 2–3× faster than Azure SQL's row-level scans as data volume grows.

![DB Comparison](docs/screenshots/comparison.png)

---

## Project Structure

```
data-pipeline/
├── app/
│   ├── db.py            # Connection factory (Azure SQL + Snowflake)
│   ├── queries.py       # Query layer — normalises column case across DBs
│   ├── models.py        # Pydantic request/response models
│   ├── main.py          # FastAPI routes + auth
│   ├── scripts/         # Ingest and feature-engineering scripts
│   │   └── ingest_to_azure_sql.py
│   └── frontend/        # React + Vite SPA
│       └── src/
│           ├── pages/   # Dashboard, MarketData, Predictor, SectorView, Comparison
│           ├── context/ # AuthContext (backend toggle, token storage)
│           └── api.js   # Typed API client + compareBackends() helper
├── db/
│   ├── azure-sql/       # Azure SQL DDL
│   ├── snowflake/       # Snowflake DDL
│   └── data/            # Raw CSV seed files
├── k8s/
│   ├── secret.yaml      # K8s Secret — DB credentials (fill before applying)
│   ├── deployment.yaml  # Pod spec — 1 replica, health probes
│   └── service.yaml     # LoadBalancer — exposes port 80 → pod 8000
├── Dockerfile           # python:3.11-slim image for FastAPI
├── tests/
│   └── test_api.py      # 15 pytest tests
└── docs/
    └── screenshots/     # UI mockups and captured screenshots
```
