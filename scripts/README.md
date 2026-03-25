# Azure CLI Infrastructure as Code - Complete Guide

Complete automated setup for SecondCortex backend using Azure CLI and PowerShell scripts. All resources provisioned programmatically, no manual Portal clicks required.

## Overview

| Script | Purpose | Time |
|--------|---------|------|
| `azure-setup.ps1` | Provision all Azure resources | 10-15 min |
| `save-credentials.ps1` | Export credentials to JSON | <1 min |
| `create-search-index.ps1` | Create Search index schema | <1 min |
| `app-service-deploy.ps1` | Deploy backend code to App Service | 2-5 min |
| `AZURE_CLI_QUICKSTART.md` | Step-by-step guide | Reference |

## Quick Start (3 Commands)

```powershell
# 1. Provision infrastructure
.\scripts\azure-setup.ps1 `
    -primarySubscription "your-primary-sub-id" `
    -secondarySubscription "your-secondary-sub-id" `
    -resourceGroupName "secondcortex-rg" `
    -location "East US" `
    -appServiceName "secondcortex-app" `
    -environment "production"

# 2. Save credentials
.\scripts\save-credentials.ps1 `
    -resourceGroupName "secondcortex-rg" `
    -appServiceName "secondcortex-app"

# 3. Deploy backend
.\scripts\app-service-deploy.ps1 `
    -appServiceName "secondcortex-app" `
    -resourceGroupName "secondcortex-rg"
```

**Done!** Your entire infrastructure is deployed and backend is live.

## Detailed Workflow

### Phase 1: Infrastructure Provisioning

**Script:** `azure-setup.ps1`

Creates all Azure resources with proper configuration:

```powershell
.\azure-setup.ps1 `
    -primarySubscription "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" `
    -secondarySubscription "yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy" `
    -resourceGroupName "secondcortex-rg" `
    -location "East US" `
    -appServiceName "secondcortex-app" `
    -environment "production"
```

**Parameters:**
- `primarySubscription`: Subscription for App Service & PostgreSQL
- `secondarySubscription`: Subscription for Search & Cosmos (can be same)
- `resourceGroupName`: Azure resource group name
- `location`: Azure region (e.g., "East US", "West Europe")
- `appServiceName`: Must be globally unique (forms basis for all service names)
- `environment`: "dev", "staging", or "production" (controls SKU sizing)

**What it creates:**
```
PostgreSQL Server (secondcortex-app-postgres)
├── Database: secondcortex
├── Admin user: dbadmin
└── Firewall: Open to Azure services

Azure AI Search (secondcortex-app-search)
├── SKU: Standard
├── Replicas: 1
└── Capability ready for indexes

Azure Cosmos DB (secondcortex-app-cosmos)
├── Database: secondcortex
├── Container: snapshots
│   ├── Partition key: /user_id
│   └── Throughput: 400 RU/s
└── Connection string: Saved

App Service (secondcortex-app)
├── Plan: secondcortex-app-plan
├── Runtime: Python 3.11
├── Application settings: 8 configured
└── URL: https://secondcortex-app.azurewebsites.net
```

**Output:**
- Resource group with all services
- Credentials printed to console (copy to safe location)
- App Service pre-configured with connection strings

### Phase 2: Credentials Management

**Script:** `save-credentials.ps1`

Exports all deployment credentials to `credentials.json`:

```powershell
.\scripts\save-credentials.ps1 `
    -resourceGroupName "secondcortex-rg" `
    -appServiceName "secondcortex-app"
```

**Creates:** `credentials.json` containing:
```json
{
  "postgresql": {
    "host": "secondcortex-app-postgres.postgres.database.azure.com",
    "connection_string": "postgresql://..."
  },
  "search": {
    "endpoint": "https://secondcortex-app-search.search.windows.net",
    "api_key": "..."
  },
  "cosmos": {
    "connection_string": "..."
  },
  "appService": {
    "url": "https://secondcortex-app.azurewebsites.net"
  }
}
```

**⚠️ Security:** Do NOT commit credentials.json to git. Keep in safe location (Azure Key Vault recommended for production).

### Phase 3: Database Initialization

**Manual step:** Initialize PostgreSQL schema

```bash
psql -h secondcortex-app-postgres.postgres.database.azure.com \
     -U dbadmin \
     -d secondcortex \
     -f secondcortex-backend/database/migrations/001_create_schema.sql
```

This creates:
- `users` table
- `projects` table  
- `snapshots` table with proper indexes
- Constraints and triggers

### Phase 4: Search Index Creation

**Script:** `create-search-index.ps1`

Creates Azure AI Search index:

```powershell
.\scripts\create-search-index.ps1 `
    -searchServiceName "secondcortex-app-search" `
    -apiKey "<api-key-from-credentials.json>"
```

Index schema created:
```
Index: "snapshots"
├── Fields:
│   ├── id (Key, String)
│   ├── user_id (Filterable, String)
│   ├── project_id (Filterable, String)
│   ├── summary (Searchable, String)
│   ├── active_file (String)
│   ├── git_branch (String)
│   ├── timestamp (Filterable, DateTime)
│   ├── entities (String)
│   └── embedding (Vector, 1536-dim)
├── Vector Search: Enabled (HNSW)
├── Semantic Search: Enabled
└── Vectorizer: Azure OpenAI (text-embedding-3-small)
```

**⚠️ IMPORTANT:** After creation, update vectorizer credentials with your actual Azure OpenAI:
- Edit index in Azure Portal
- Or run: `az search index update --name snapshots --service-name secondcortex-app-search ...`

### Phase 5: Backend Deployment

**Script:** `app-service-deploy.ps1`

Deploys backend code to App Service:

```powershell
.\scripts\app-service-deploy.ps1 `
    -appServiceName "secondcortex-app" `
    -resourceGroupName "secondcortex-rg"
```

**What it does:**
1. Creates deployment package (second cortex-backend)
2. Deploys to App Service
3. Restarts app service
4. Streams logs during startup
5. Validates with health check
6. Shows App Service URL

**Staging deployments:**
```powershell
# Deploy to staging slot (no production traffic)
.\app-service-deploy.ps1 `
    ... parameters ... `
    -deploymentSlot "staging"

# Script offers to swap slot to production after validation
```

## Environment Customization

### Development (`-environment dev`)

```powershell
.\azure-setup.ps1 -environment "dev" ... # other params
```

Creates minimal-cost resources:
- PostgreSQL: Standard_B1ms (1 vCore, 2 GB RAM)
- Search: Standard (1 partition)
- Cosmos: 400 RU/s
- App Service: B1 (Basic tier)
- **Estimated cost:** ~$150-200/month

### Staging (`-environment staging`)

```powershell
.\azure-setup.ps1 -environment "staging" ... # other params
```

Creates medium-capacity resources:
- PostgreSQL: Standard_D2s_v3 (2 vCore, 8 GB RAM)
- Search: Standard (2 partitions)
- Cosmos: 4,000 RU/s
- App Service: S1 (Standard tier)
- **Estimated cost:** ~$600-800/month

### Production (`-environment production`)

```powershell
.\azure-setup.ps1 -environment "production" ... # other params
```

Creates high-availability resources:
- PostgreSQL: Standard_D4s_v3 (4 vCore, 16 GB RAM) with HA
- Search: Standard (3 partitions)
- Cosmos: 10,000+ RU/s autoscale
- App Service: P1V2 (Premium tier)
- **Estimated cost:** ~$1,500-2,000/month

## Cross-Account Setup

If using separate Azure subscriptions:

```powershell
# Primary account (where you run az cli from)
$primary = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

# Secondary account (Search, Cosmos)
$secondary = "yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy"

.\azure-setup.ps1 `
    -primarySubscription $primary `
    -secondarySubscription $secondary `
    ... other params ...
```

**What this requires:**
1. Both subscriptions must be in same Azure AD tenant
2. Your user must have Owner or Contributor role in both subscriptions
3. Network path must be open between accounts:
   - Option A: Firewall rules allowing App Service IP
   - Option B: Private Endpoints (recommended for production)
   - Option C: Service principals with proper permissions

**Verify access:**
```bash
# Primary account resources
az resource list --subscription $primary --query "[].name"

# Secondary account resources  
az resource list --subscription $secondary --query "[].name"

# Switch between subscriptions
az account set --subscription $primary
az account set --subscription $secondary
```

## Troubleshooting

### Script fails with "subscription not found"

```powershell
# List your subscriptions
az account list --output table

# Use correct subscription ID
az account set --subscription "<correct-id>"
```

### PostgreSQL connection fails

```bash
# Check server is accessible
psql -h <postgres-host> -U dbadmin -c "SELECT version();"

# Add firewall rule for your IP
az postgres flexible-server firewall-rule create \
    --name my-postgres \
    --resource-group secondcortex-rg \
    --rule-name "MyIP" \
    --start-ip-address "YOUR.IP.ADDRESS" \
    --end-ip-address "YOUR.IP.ADDRESS"

# Or allow all (dev only)
az postgres flexible-server firewall-rule create \
    --name my-postgres \
    --resource-group secondcortex-rg \
    --rule-name "AllowAll" \
    --start-ip-address "0.0.0.0" \
    --end-ip-address "255.255.255.255"
```

### Search index creation fails

```bash
# Verify Search service exists
az search service list \
    --resource-group secondcortex-rg \
    --query "[].name"

# Check if index already exists
az search index list \
    --name secondcortex-app-search \
    --resource-group secondcortex-rg

# Delete old index and re-create
az search index delete \
    --name snapshots \
    --service-name secondcortex-app-search \
    --resource-group secondcortex-rg

# Re-run creation script
.\create-search-index.ps1 ...
```

### App Service won't start

```bash
# Stream logs to see error
az webapp log tail \
    --name secondcortex-app \
    --resource-group secondcortex-rg

# Check app settings are deployed
az webapp config appsettings list \
    --name secondcortex-app \
    --resource-group secondcortex-rg

# Restart app
az webapp restart \
    --name secondcortex-app \
    --resource-group secondcortex-rg
```

### Cross-account services not accessible from App Service

```bash
# Solution 1: Allow App Service outbound IP
$appServiceIp = az webapp show \
    --name secondcortex-app \
    --resource-group secondcortex-rg \
    --query outboundIpAddresses

# Add to Search/Cosmos firewall rules in secondary account

# Solution 2: Use Private Endpoints (recommended)
# Must create vnet and private endpoints in secondary account
# Then create vnet link in primary account

# Solution 3: Use Managed Identity (long-term best practice)
# Enable managed identity on App Service
# Assign permissions in secondary account resource
```

## Next Steps

After deployment, recommend:

1. **Set up CI/CD pipeline:**
   - GitHub Actions
   - Azure DevOps
   - Auto-deploy on code changes

2. **Enable Private Endpoints:**
   - Removes need for firewall rules
   - Improves security for cross-account access
   - Requires vnet setup

3. **Upgrade to Managed Identity:**
   - Eliminate API key storage
   - Better security than key-based auth
   - Requires Entra ID setup

4. **Configure monitoring:**
   - Application Insights
   - Alerts for failures
   - Performance baselines

5. **Set up backups:**
   - PostgreSQL automatic backup
   - Cosmos continuous backup
   - Snapshots to Azure Blob Storage

6. **Cost optimization:**
   - Review resource sizing
   - Enable autoscaling
   - Set up budget alerts

## Support

- **Detailed steps:** See [AZURE_CLI_QUICKSTART.md](AZURE_CLI_QUICKSTART.md)
- **Manual checklist:** See [../AZURE_DEPLOYMENT_CHECKLIST.md](../AZURE_DEPLOYMENT_CHECKLIST.md)
- **Script help:** 
  ```powershell
  Get-Help .\azure-setup.ps1 -Full
  Get-Help .\create-search-index.ps1 -Full
  Get-Help .\app-service-deploy.ps1 -Full
  ```

## Resources

- [Azure CLI Install](https://docs.microsoft.com/cli/azure/install-azure-cli)
- [Azure CLI Reference](https://docs.microsoft.com/cli/azure/reference-index)
- [Azure Services Pricing](https://azure.microsoft.com/pricing)
- [SecondCortex Backend Docs](../secondcortex-backend/README.md)
