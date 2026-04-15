# Azure CLI Reference — CMIA Data Pipeline
# Everything done via the portal in this project, expressed as CLI commands.
# DO NOT RUN THIS FILE — it is a reference document only.
# Prerequisites: brew install azure-cli msodbcsql18 mssql-tools18
# Authenticate first: az login

---

## 1. Resource Group

```bash
az group create \
  --name cmia-source-db \
  --location centralus
```

---

## 2. Azure SQL Server

```bash
az sql server create \
  --name cmia-source-server \
  --resource-group cmia-source-db \
  --location centralus \
  --admin-user fahim \
  --admin-password Ottawa2021
```

### Add firewall rule — allow your local IP
```bash
# Get your current public IP
MY_IP=$(curl -s https://api.ipify.org)

az sql server firewall-rule create \
  --resource-group cmia-source-db \
  --server cmia-source-server \
  --name AllowMyIP \
  --start-ip-address $MY_IP \
  --end-ip-address $MY_IP
```

### Allow Azure services to access server
```bash
az sql server firewall-rule create \
  --resource-group cmia-source-db \
  --server cmia-source-server \
  --name AllowAzureServices \
  --start-ip-address 0.0.0.0 \
  --end-ip-address 0.0.0.0
```

---

## 3. Azure SQL Database

```bash
az sql db create \
  --resource-group cmia-source-db \
  --server cmia-source-server \
  --name cmia-source-db \
  --edition GeneralPurpose \
  --compute-model Serverless \
  --family Gen5 \
  --capacity 1 \
  --max-size 32GB \
  --auto-pause-delay 60
```

### Get connection string
```bash
az sql db show-connection-string \
  --server cmia-source-server \
  --name cmia-source-db \
  --client odbc
```

---

## 4. Run Azure SQL DDL files via sqlcmd

### Run all schema files in order
```bash
for f in $(ls db/azure-sql/*.sql | sort); do
  echo "Running $f..."
  sqlcmd \
    -S cmia-source-server.database.windows.net \
    -d cmia-source-db \
    -U fahim \
    -P Ottawa2021 \
    -i "$f" \
    -l 30
done
```

### Run a single file
```bash
sqlcmd \
  -S cmia-source-server.database.windows.net \
  -d cmia-source-db \
  -U fahim \
  -P Ottawa2021 \
  -i db/azure-sql/01_schemas.sql
```

### Run an inline query (useful for quick validation)
```bash
sqlcmd \
  -S cmia-source-server.database.windows.net \
  -d cmia-source-db \
  -U fahim \
  -P Ottawa2021 \
  -Q "SELECT COUNT(*) FROM market.daily_prices"
```

---

## 5. Azure Container Registry (ACR)

```bash
# Create ACR — admin-enabled exposes username/password for GitHub Actions secrets
az acr create \
  --resource-group cmia-source-db \
  --name cmiaregistry \
  --sku Basic \
  --admin-enabled true
```

### Log in to ACR (required before docker push)
```bash
az acr login --name cmiaregistry
```

### Build and push Docker image locally
```bash
docker build -t cmiaregistry.azurecr.io/cmia-api:latest .
docker push cmiaregistry.azurecr.io/cmia-api:latest
```

### Tag with git SHA (used by CI/CD for immutable image references)
```bash
docker build -t cmiaregistry.azurecr.io/cmia-api:$(git rev-parse --short HEAD) .
docker push cmiaregistry.azurecr.io/cmia-api:$(git rev-parse --short HEAD)
```

### List images in ACR
```bash
az acr repository list --name cmiaregistry --output table
az acr repository show-tags --name cmiaregistry --repository cmia-api --output table
```

---

## 6. AKS Cluster

```bash
# --attach-acr grants AKS managed identity pull access to ACR — no credentials needed
az aks create \
  --resource-group cmia-source-db \
  --name cmia-aks \
  --location centralus \
  --node-count 1 \
  --node-vm-size Standard_B2s \
  --attach-acr cmiaregistry \
  --generate-ssh-keys
```

### Get kubectl credentials
```bash
az aks get-credentials \
  --resource-group cmia-source-db \
  --name cmia-aks

kubectl get nodes   # should show 1 node in Ready state
```

### Encode secrets before applying (each value must be base64)
```bash
echo -n "cmia-source-server.database.windows.net" | base64
echo -n "cmia-source-db"                           | base64
echo -n "your_username"                            | base64
echo -n "your_password"                            | base64
# Paste encoded values into k8s/secret.yaml, then:
```

### Deploy to AKS (first time)
```bash
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
```

### Check pod status
```bash
kubectl get pods
kubectl get service cmia-api-svc --watch   # wait for EXTERNAL-IP to appear
kubectl logs <pod-name>                    # view logs
kubectl describe pod <pod-name>            # debug a failing pod
```

### Rolling update (zero-downtime redeploy)
```bash
# AKS starts new pods, waits for /health readiness probe, then kills old pods
kubectl set image deployment/cmia-api \
  cmia-api=cmiaregistry.azurecr.io/cmia-api:<new-tag>
kubectl rollout status deployment/cmia-api --timeout=120s
```

### Rollback to previous version
```bash
kubectl rollout undo deployment/cmia-api
```

---

## 7. GitHub Actions — CI/CD Secrets

### Get ACR credentials for GitHub secrets
```bash
az acr credential show --name cmiaregistry
# ACR_USERNAME = username field
# ACR_PASSWORD = passwords[0].value field
# Add both to: GitHub repo → Settings → Secrets and variables → Actions
```

### Export kubeconfig as base64 for GitHub secret KUBE_CONFIG
```bash
cat ~/.kube/config | base64 | pbcopy
# Paste into GitHub secret: KUBE_CONFIG
```

---

## 8. Azure Static Web Apps (React frontend)

```bash
az staticwebapp create \
  --name cmia-frontend \
  --resource-group cmia-source-db \
  --location centralus \
  --sku Free \
  --source https://github.com/fanik041/data-pipeline \
  --branch main \
  --app-location app/frontend \
  --output-location dist
```

---

## 9. Useful Diagnostics

```bash
# List all resources in resource group
az resource list --resource-group cmia-source-db --output table

# Check AKS cluster status
az aks show --resource-group cmia-source-db --name cmia-aks --query provisioningState

# Stream live pod logs
kubectl logs -f deployment/cmia-api

# Scale AKS node pool
az aks scale \
  --resource-group cmia-source-db \
  --name cmia-aks \
  --node-count 2

# Get all K8s resources at once
kubectl get all

# Force restart all pods in deployment
kubectl rollout restart deployment/cmia-api
```
