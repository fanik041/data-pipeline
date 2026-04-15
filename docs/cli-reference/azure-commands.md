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
az acr create \
  --resource-group cmia-source-db \
  --name cmiaregistry \
  --sku Basic
```

### Log in to ACR (required before docker push)
```bash
az acr login --name cmiaregistry
```

### Build and push Docker image via ACR (no local Docker needed)
```bash
az acr build \
  --registry cmiaregistry \
  --image fastapi-migration:latest \
  --file services/fastapi/Dockerfile \
  .
```

---

## 6. AKS Cluster

```bash
az aks create \
  --resource-group cmia-source-db \
  --name cmia-aks \
  --location centralus \
  --node-count 1 \
  --node-vm-size Standard_D2ps_v6 \
  --tier free \
  --attach-acr cmiaregistry \
  --generate-ssh-keys
```

### Get kubectl credentials
```bash
az aks get-credentials \
  --resource-group cmia-source-db \
  --name cmia-aks
```

### Verify nodes are running
```bash
kubectl get nodes
```

### Deploy FastAPI to AKS
```bash
kubectl apply -f k8s/fastapi-deployment.yaml
kubectl apply -f k8s/fastapi-service.yaml
```

### Check pod status
```bash
kubectl get pods
kubectl logs <pod-name>          # view logs
kubectl describe pod <pod-name>  # debug a failing pod
```

---

## 7. GitHub Actions — Service Principal

### Create service principal for GitHub Actions to authenticate with Azure
```bash
az ad sp create-for-rbac \
  --name "cmia-github-actions" \
  --role contributor \
  --scopes /subscriptions/773cbc80-612b-4a05-955f-823edaa4fe93 \
  --sdk-auth
# Copy the full JSON output → paste into GitHub secret AZURE_CREDENTIALS
```

### Get ACR credentials for GitHub secrets
```bash
az acr credential show --name cmiaregistry
# ACR_USERNAME = username field
# ACR_PASSWORD = passwords[0].value field
```

---

## 8. Azure Static Web Apps (React frontend)

```bash
az staticwebapp create \
  --name cmia-frontend \
  --resource-group cmia-source-db \
  --location centralus \
  --sku Free \
  --source https://github.com/<your-username>/data-pipeline \
  --branch main \
  --app-location /services/react \
  --output-location build
```

---

## 9. Useful Diagnostics

```bash
# List all resources in resource group
az resource list --resource-group cmia-source-db --output table

# Check AKS cluster status
az aks show --resource-group cmia-source-db --name cmia-aks --query provisioningState

# Stream AKS pod logs
kubectl logs -f deployment/fastapi-migration

# Scale AKS node pool up/down
az aks scale \
  --resource-group cmia-source-db \
  --name cmia-aks \
  --node-count 2

# Get AKS external IP after service deploy
kubectl get service fastapi-service --watch
```
