# Azure CLI Setup Quickstart for SecondCortex

Complete Infrastructure as Code setup using Azure CLI and PowerShell scripts.

## Prerequisites

1. **Azure CLI** installed:
   ```bash
   # Windows
   choco install azure-cli
   
   # Or download from https://docs.microsoft.com/cli/azure/install-azure-cli
   ```

2. **PowerShell 5.1+** (Windows 10/11 default)

3. **psql** (PostgreSQL client) for schema initialization:
   ```bash
   # Windows
   choco install postgresql
   
   # Or download from https://www.postgresql.org/download/windows/
   ```

4. **Azure Account** with two subscriptions or use the same subscription for all resources

## Step 1: Login to Azure

```powershell
# Login to Azure
az login

# Switch to primary subscription
az account set --subscription "<primary-subscription-id>"

# View available subscriptions
az account list --output table
```

## Step 2: Run Automated Setup

```powershell
cd scripts

# Execute main setup script
.\azure-setup.ps1 `
    -primarySubscription "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" `
    -secondarySubscription "yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy" `
    -resourceGroupName "secondcortex-rg" `
    -location "East US" `
    -appServiceName "secondcortex-app" `
    -environment "production"
```

**What this does:**
- ✓ Creates resource group
- ✓ Creates PostgreSQL server with database
- ✓ Creates Azure AI Search service
- ✓ Creates Azure Cosmos DB account with container
- ✓ Creates App Service Plan
- ✓ Creates App Service
- ✓ Configures all app settings
- ✓ Sets up networking and firewall rules

**Output:** Credentials and connection strings (save these!)

## Step 3: Save Credentials

```powershell
# Save all deployment credentials to credentials.json
.\save-credentials.ps1 `
    -resourceGroupName "secondcortex-rg" `
    -appServiceName "secondcortex-app"
```

This creates `credentials.json` with all connection strings and API keys.

## Step 4: Initialize PostgreSQL Schema

```bash
# Using psql (after installing PostgreSQL client)
# Replace <host> and <username> with values from credentials.json

psql -h <postgres-host> -U <username> -d secondcortex -f ..\secondcortex-backend\database\migrations\001_create_schema.sql

# When prompted, enter the PostgreSQL password saved from step 2
```

Or use az cli:

```bash
# List PostgreSQL servers to get connection details
az postgres flexible-server show `
    --name secondcortex-app-postgres `
    --resource-group secondcortex-rg
```

## Step 5: Create Azure Search Index

```powershell
# Create the snapshots index
.\create-search-index.ps1 `
    -searchServiceName "secondcortex-app-search" `
    -apiKey "<api-key-from-credentials.json>"
```

⚠️ **IMPORTANT**: The script creates index with placeholder Azure OpenAI credentials. You MUST update:

```powershell
# Update with your actual Azure OpenAI credentials
$searchServiceName = "secondcortex-app-search"
$apiKey = "<your-api-key>"
$resourceGroupName = "secondcortex-rg"

# Get current index
$currentIndex = az search index show `
    --name "snapshots" `
    --service-name $searchServiceName `
    --resource-group $resourceGroupName `
    --api-key $apiKey

# Update vectorizer credentials in Azure Portal UI or JSON
# Then reapply with: az search index update ...
```

Or update in Azure Portal:
1. Go to Cognitive Search service
2. Click "Indexes" → "snapshots"
3. Edit "embedding" field
4. Update "vectorSearchConfiguration" with actual Azure OpenAI endpoint and key

## Step 6: Deploy Backend Code

### Option A: Deploy from local directory

```bash
# From project root
cd secondcortex-backend

# Publish to App Service
az webapp deployment source config-zip `
    --resource-group secondcortex-rg `
    --name secondcortex-app `
    --src-path ./

# Or use Zip Deploy
.\app-service-deploy.ps1 -appServiceName "secondcortex-app" -resourceGroupName "secondcortex-rg"
```

### Option B: Deploy from GitHub

```bash
# Set up GitHub deployment in Azure Portal
az webapp deployment github-actions add `
    --repo <owner/repo> `
    --branch main `
    --service-principal-id <sp-id> `
    --service-principal-password <sp-password> `
    --service-principal-tenant <tenant-id>
```

## Step 7: Seed Demo Data (Optional)

```powershell
# Set environment variable
$env:POSTGRES_CONNECTION_STRING = "postgresql://username:password@host:5432/secondcortex"

# Run seeding script
cd secondcortex-backend
python scripts/seed_demo_snapshots.py
```

This creates:
- 1 test user
- 1 test project
- 50 demo snapshots with realistic data

## Step 8: Verify Deployment

```bash
# Test App Service health
curl https://secondcortex-app.azurewebsites.net/health

# Test search endpoint
curl -X POST "https://secondcortex-app.azurewebsites.net/api/v1/snapshots/search" \
  -H "Authorization: Bearer <jwt-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "database error",
    "project_id": "<project-uuid>",
    "limit": 10
  }'

# Check App Service logs
az webapp log tail --name secondcortex-app --resource-group secondcortex-rg
```

## Troubleshooting

### PostgreSQL Connection Failed
```bash
# Check firewall rules
az postgres flexible-server firewall-rule list `
    --name secondcortex-app-postgres `
    --resource-group secondcortex-rg

# Add rule for your IP
az postgres flexible-server firewall-rule create `
    --name secondcortex-app-postgres `
    --resource-group secondcortex-rg `
    --rule-name "AllowMyIP" `
    --start-ip-address "YOUR.IP.ADDRESS" `
    --end-ip-address "YOUR.IP.ADDRESS"
```

### Search Service Not Accessible
```bash
# Verify search service exists
az search service list --resource-group secondcortex-rg --subscription <secondary-subscription-id>

# Check service status
az search service show `
    --name secondcortex-app-search `
    --resource-group secondcortex-rg `
    --subscription <secondary-subscription-id>
```

### App Service Can't Connect to Secondary Account Services
```bash
# Option 1: Add firewall rule to allow App Service outbound IP
$appServiceIp = az webapp show `
    --name secondcortex-app `
    --resource-group secondcortex-rg `
    --query outboundIpAddresses -o tsv

# Add to Search service firewall (if applicable)
# Add to Cosmos DB (disable public access, enable private endpoint)

# Option 2: Use Private Endpoints (recommended for production)
# This requires vnet setup - see Azure Portal guidance
```

### Check All Deployed Resources

```bash
# List all resources in the resource group
az resource list `
    --resource-group secondcortex-rg `
    --output table

# Detailed view
az resource list `
    --resource-group secondcortex-rg `
    --query "[].{name:name, type:type, status:resourceGroup}" `
    --output table
```

## Cross-Account Setup Notes

If using separate subscriptions for primary and secondary resources:

### Primary Account (App Service, PostgreSQL):
- Subscription: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`
- Resources: App Service, PostgreSQL, AppService Plan

### Secondary Account (Search, Cosmos):
- Subscription: `yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy`
- Resources: Azure AI Search, Cosmos DB
- Requirements:
  - Must grant permission to primary account's App Service
  - Network path must be open (firewall rules or private endpoints)
  - Connection strings must be valid cross-account

### Cross-Account Networking

```bash
# Get App Service managed identity (if using Entra ID)
$appServiceId = az webapp show `
    --name secondcortex-app `
    --resource-group secondcortex-rg `
    --query identity.principalId -o tsv

# Grant permissions in secondary subscription
az role assignment create `
    --subscription <secondary-subscription-id> `
    --assignee $appServiceId `
    --role "Cognitive Search Index Data Contributor" `
    --scope "/subscriptions/<secondary-subscription-id>/resourceGroups/secondcortex-rg"
```

## Cost Optimization

### Development Environment
```powershell
# Use smaller SKUs
.\azure-setup.ps1 `
    ... arguments ... `
    -environment "dev"
    
# In azure-setup.ps1, change:
# --sku-name Standard_B1ms (PostgreSQL)
# Standard tier, 1 partition (Search)
# 400 RU/s (Cosmos)
# Estimated cost: ~$150-200/month
```

### Production Environment
```powershell
# Use larger SKUs for HA
.\azure-setup.ps1 `
    ... arguments ... `
    -environment "production"

# In azure-setup.ps1, modify for production:
# --sku-name Standard_D2s_v3 (PostgreSQL)
# Standard tier, 3 partitions (Search - add via portal)
# 10000 RU/s autoscale (Cosmos)
# Estimated cost: ~$1500-2000/month
```

## Next Steps

1. ✅ Run `azure-setup.ps1` to provision resources
2. ✅ Run `save-credentials.ps1` to backup credentials
3. ✅ Initialize PostgreSQL schema with migration SQL
4. ✅ Create Azure Search index
5. ✅ Deploy backend code
6. ✅ Seed demo data (optional)
7. ✅ Validate endpoints
8. Later: Set up CI/CD pipeline
9. Later: Enable Private Endpoints for security
10. Later: Upgrade to Managed Identity authentication

## Support

For detailed guidance on each step, see:
- [AZURE_DEPLOYMENT_CHECKLIST.md](../AZURE_DEPLOYMENT_CHECKLIST.md) - Complete manual setup
- [azure-setup.ps1](azure-setup.ps1) - Automated provisioning script
- [create-search-index.ps1](create-search-index.ps1) - Search index creation
- [save-credentials.ps1](save-credentials.ps1) - Credentials management
