#Requires -Version 5.1
<#
.SYNOPSIS
    Automated Azure deployment for SecondCortex migration (PostgreSQL + Azure Search + Cosmos DB)
.DESCRIPTION
    Provisions all required Azure resources via CLI using a cross-account setup:
    - Azure AI Search + Cosmos DB in secondary account
    - PostgreSQL, App Service in primary account
.PARAMETER primarySubscription
    Primary subscription ID (App Service, PostgreSQL)
.PARAMETER secondarySubscription
    Secondary subscription ID (Search, Cosmos) - optional, defaults to primary
.PARAMETER resourceGroupName
    Resource group name (created if doesn't exist)
.PARAMETER location
    Azure region (e.g., "East US", "West Europe")
.PARAMETER appServiceName
    App Service name (must be globally unique)
.PARAMETER environment
    Environment name: dev, staging, production
.EXAMPLE
    .\azure-setup.ps1 -primarySubscription "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" `
                      -secondarySubscription "yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy" `
                      -resourceGroupName "secondcortex-rg" `
                      -location "East US" `
                      -appServiceName "secondcortex-app" `
                      -environment "production"
#>

param(
    [Parameter(Mandatory=$true)]
    [string]$primarySubscription,

    [Parameter(Mandatory=$false)]
    [string]$secondarySubscription = $primarySubscription,

    [Parameter(Mandatory=$true)]
    [string]$resourceGroupName,

    [Parameter(Mandatory=$true)]
    [string]$location,

    [Parameter(Mandatory=$true)]
    [string]$appServiceName,

    [Parameter(Mandatory=$false)]
    [ValidateSet("dev", "staging", "production")]
    [string]$environment = "dev"
)

# Color output helpers
function Write-Success { Write-Host "✓ $args" -ForegroundColor Green }
function Write-Info { Write-Host "ℹ $args" -ForegroundColor Cyan }
function Write-Warning { Write-Host "⚠ $args" -ForegroundColor Yellow }
function Write-Error { Write-Host "✗ $args" -ForegroundColor Red }

$ErrorActionPreference = "Stop"

Write-Info "Starting Azure SecondCortex deployment"
Write-Info "Primary Subscription: $primarySubscription"
Write-Info "Secondary Subscription: $secondarySubscription"
Write-Info "Environment: $environment"

# 1. Setup subscriptions
Write-Info "Setting up subscriptions..."
az account set --subscription $primarySubscription
Write-Success "Switched to primary subscription"

# 2. Create resource group (primary account)
Write-Info "Creating resource group..."
az group create `
    --name $resourceGroupName `
    --location $location `
    --subscription $primarySubscription
Write-Success "Resource group created: $resourceGroupName"

# 3. Create PostgreSQL server
Write-Info "Creating PostgreSQL server..."
$postgresServerName = "$appServiceName-postgres"
$postgresAdminUser = "dbadmin"
$postgresPassword = "Pwd$(Get-Random -Minimum 100000 -Maximum 999999)!@#"

az postgres flexible-server create `
    --resource-group $resourceGroupName `
    --name $postgresServerName `
    --location $location `
    --subscription $primarySubscription `
    --admin-user $postgresAdminUser `
    --admin-password $postgresPassword `
    --tier Burstable `
    --sku-name Standard_B1ms `
    --storage-size 32 `
    --public-access "0.0.0.0" `
    --high-availability Disabled

Write-Success "PostgreSQL server created: $postgresServerName"
Write-Warning "PostgreSQL admin password: $postgresPassword (save this!)"

# Create database
az postgres flexible-server db create `
    --resource-group $resourceGroupName `
    --server-name $postgresServerName `
    --database-name "secondcortex" `
    --subscription $primarySubscription

Write-Success "Database created: secondcortex"

# 4. Create Azure AI Search service (secondary account)
Write-Info "Creating Azure AI Search service..."
$searchServiceName = "$appServiceName-search"

az search service create `
    --name $searchServiceName `
    --resource-group $resourceGroupName `
    --location $location `
    --subscription $secondarySubscription `
    --sku Standard

Write-Success "Search service created: $searchServiceName"

# Get Search service keys
$searchEndpoint = "https://$searchServiceName.search.windows.net"
$searchApiKey = az search admin-key show `
    --name $searchServiceName `
    --resource-group $resourceGroupName `
    --subscription $secondarySubscription `
    --query primaryKey -o tsv

Write-Success "Search endpoint: $searchEndpoint"
Write-Warning "Search API key: $searchApiKey (save this!)"

# 5. Create Azure Cosmos DB (secondary account)
Write-Info "Creating Azure Cosmos DB account..."
$cosmosAccountName = "$appServiceName-cosmos"

az cosmosdb create `
    --name $cosmosAccountName `
    --resource-group $resourceGroupName `
    --locations regionName=$location `
    --default-consistency-level Eventual `
    --subscription $secondarySubscription

Write-Success "Cosmos DB account created: $cosmosAccountName"

# Create database and container
az cosmosdb sql database create `
    --account-name $cosmosAccountName `
    --resource-group $resourceGroupName `
    --name "secondcortex" `
    --subscription $secondarySubscription

Write-Success "Cosmos database created: secondcortex"

az cosmosdb sql container create `
    --account-name $cosmosAccountName `
    --database-name "secondcortex" `
    --name "snapshots" `
    --partition-key-path "/user_id" `
    --throughput 400 `
    --resource-group $resourceGroupName `
    --subscription $secondarySubscription

Write-Success "Cosmos container created: snapshots"

# Get Cosmos connection string
$cosmosConnectionString = az cosmosdb keys list-connection-strings `
    --name $cosmosAccountName `
    --resource-group $resourceGroupName `
    --subscription $secondarySubscription `
    --query connectionStrings[0].connectionString -o tsv

Write-Warning "Cosmos connection string: $cosmosConnectionString (save this!)"

# 6. Create App Service Plan
Write-Info "Creating App Service Plan..."
$appServicePlanName = "$appServiceName-plan"

az appservice plan create `
    --name $appServicePlanName `
    --resource-group $resourceGroupName `
    --location $location `
    --sku B2 `
    --subscription $primarySubscription

Write-Success "App Service Plan created: $appServicePlanName"

# 7. Create App Service
Write-Info "Creating App Service..."
az webapp create `
    --name $appServiceName `
    --resource-group $resourceGroupName `
    --plan $appServicePlanName `
    --runtime "PYTHON|3.11" `
    --subscription $primarySubscription

Write-Success "App Service created: $appServiceName"

# 8. Configure PostgreSQL connection string
Write-Info "Configuring PostgreSQL connection string..."
$postgresHost = az postgres flexible-server show `
    --name $postgresServerName `
    --resource-group $resourceGroupName `
    --subscription $primarySubscription `
    --query fullyQualifiedDomainName -o tsv

$postgresConnectionString = "postgresql://${postgresAdminUser}:${postgresPassword}@${postgresHost}:5432/secondcortex"

# 9. Configure App Service settings
Write-Info "Configuring App Service application settings..."

az webapp config appsettings set `
    --name $appServiceName `
    --resource-group $resourceGroupName `
    --subscription $primarySubscription `
    --settings `
        POSTGRES_CONNECTION_STRING="$postgresConnectionString" `
        AZURE_SEARCH_ENDPOINT="$searchEndpoint" `
        AZURE_SEARCH_API_KEY="$searchApiKey" `
        AZURE_SEARCH_INDEX_NAME="snapshots" `
        AZURE_COSMOS_CONNECTION_STRING="$cosmosConnectionString" `
        ENVIRONMENT="$environment" `
        LOG_LEVEL="INFO" `
        WEBSITES_PORT="8000"

Write-Success "App Service settings configured"

# 10. Configure App Service to allow access from internet (for initial testing)
Write-Info "Configuring App Service networking..."
az webapp config access-restriction add `
    --name $appServiceName `
    --resource-group $resourceGroupName `
    --subscription $primarySubscription `
    --rule-name "AllowAll" `
    --action Allow `
    --priority 100 `
    --access-restriction-name "AllowAll"

Write-Success "App Service networking configured"

# 11. Configure PostgreSQL firewall to allow App Service
Write-Info "Configuring PostgreSQL firewall rules..."
az postgres flexible-server firewall-rule create `
    --name $postgresServerName `
    --resource-group $resourceGroupName `
    --subscription $primarySubscription `
    --rule-name "AllowAzureServices" `
    --start-ip-address "0.0.0.0" `
    --end-ip-address "255.255.255.255"

Write-Success "PostgreSQL firewall configured"

# 12. Summary
Write-Info "Azure deployment complete!"
Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "DEPLOYMENT SUMMARY" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "PostgreSQL:" -ForegroundColor Green
Write-Host "  Server: $postgresServerName"
Write-Host "  Host: $postgresHost"
Write-Host "  Database: secondcortex"
Write-Host "  Username: $postgresAdminUser"
Write-Host "  Password: $postgresPassword"
Write-Host "  Connection String: $postgresConnectionString"
Write-Host ""
Write-Host "Azure AI Search:" -ForegroundColor Green
Write-Host "  Service: $searchServiceName"
Write-Host "  Endpoint: $searchEndpoint"
Write-Host "  API Key: $searchApiKey"
Write-Host ""
Write-Host "Azure Cosmos DB:" -ForegroundColor Green
Write-Host "  Account: $cosmosAccountName"
Write-Host "  Database: secondcortex"
Write-Host "  Container: snapshots"
Write-Host "  Connection String: $cosmosConnectionString"
Write-Host ""
Write-Host "App Service:" -ForegroundColor Green
Write-Host "  Name: $appServiceName"
Write-Host "  Plan: $appServicePlanName"
Write-Host "  URL: https://$appServiceName.azurewebsites.net"
Write-Host ""
Write-Host "Resource Group: $resourceGroupName" -ForegroundColor Green
Write-Host "Location: $location" -ForegroundColor Green
Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "NEXT STEPS:" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "1. Save credentials file:"
Write-Host "   .\scripts\save-credentials.ps1 -resourceGroupName $resourceGroupName"
Write-Host ""
Write-Host "2. Initialize PostgreSQL schema:"
Write-Host "   psql -h $postgresHost -U $postgresAdminUser -d secondcortex -f secondcortex-backend/database/migrations/001_create_schema.sql"
Write-Host ""
Write-Host "3. Create Azure Search index:"
Write-Host "   .\scripts\create-search-index.ps1 -searchServiceName $searchServiceName -apiKey $searchApiKey"
Write-Host ""
Write-Host "4. Deploy backend code to App Service"
Write-Host ""
Write-Host "5. Seed demo data:"
Write-Host "   \$env:POSTGRES_CONNECTION_STRING='$postgresConnectionString'"
Write-Host "   python .\secondcortex-backend\scripts\seed_demo_snapshots.py"
Write-Host ""
