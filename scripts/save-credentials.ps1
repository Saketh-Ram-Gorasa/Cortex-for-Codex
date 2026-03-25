#Requires -Version 5.1
<#
.SYNOPSIS
    Save Azure deployment credentials to a secure local file
.PARAMETER resourceGroupName
    Resource group name
.PARAMETER appServiceName
    App Service name (used to derive resource names)
.PARAMETER subscriptionId
    Subscription ID (for reference)
.EXAMPLE
    .\save-credentials.ps1 -resourceGroupName "secondcortex-rg" -appServiceName "secondcortex-app"
#>

param(
    [Parameter(Mandatory=$true)]
    [string]$resourceGroupName,

    [Parameter(Mandatory=$true)]
    [string]$appServiceName,

    [Parameter(Mandatory=$false)]
    [string]$subscriptionId = (az account show --query id -o tsv)
)

$ErrorActionPreference = "Stop"

Write-Host "Retrieving deployment credentials..." -ForegroundColor Cyan

# PostgreSQL
$postgresServerName = "$appServiceName-postgres"
$postgresAdmin = az postgres flexible-server show `
    --name $postgresServerName `
    --resource-group $resourceGroupName `
    --query administratorLogin -o tsv

$postgresHost = az postgres flexible-server show `
    --name $postgresServerName `
    --resource-group $resourceGroupName `
    --query fullyQualifiedDomainName -o tsv

# Azure Search
$searchServiceName = "$appServiceName-search"
$searchEndpoint = "https://$searchServiceName.search.windows.net"
$searchApiKey = az search admin-key show `
    --name $searchServiceName `
    --resource-group $resourceGroupName `
    --query primaryKey -o tsv

# Cosmos DB
$cosmosAccountName = "$appServiceName-cosmos"
$cosmosConnectionString = az cosmosdb keys list-connection-strings `
    --name $cosmosAccountName `
    --resource-group $resourceGroupName `
    --query connectionStrings[0].connectionString -o tsv

# App Service
$appServiceUrl = az webapp show `
    --name $appServiceName `
    --resource-group $resourceGroupName `
    --query defaultHostName -o tsv

# App Service settings (for reference)
$appSettings = az webapp config appsettings list `
    --name $appServiceName `
    --resource-group $resourceGroupName | ConvertFrom-Json

# Build credentials object
$credentials = @{
    deployment = @{
        subscriptionId = $subscriptionId
        resourceGroup = $resourceGroupName
        location = (az group show --name $resourceGroupName --query location -o tsv)
        deploymentDate = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    }
    postgresql = @{
        serverName = $postgresServerName
        host = $postgresHost
        database = "secondcortex"
        username = $postgresAdmin
        port = 5432
        connectionString = "postgresql://${postgresAdmin}@${postgresHost}:5432/secondcortex"
    }
    search = @{
        serviceName = $searchServiceName
        endpoint = $searchEndpoint
        indexName = "snapshots"
        apiKey = $searchApiKey
    }
    cosmos = @{
        accountName = $cosmosAccountName
        database = "secondcortex"
        container = "snapshots"
        connectionString = $cosmosConnectionString
    }
    appService = @{
        name = $appServiceName
        url = "https://$appServiceUrl"
        host = $appServiceUrl
    }
    appSettings = @{}
}

# Add app settings (excluding sensitive values)
foreach ($setting in $appSettings) {
    if ($setting.name -notlike "*KEY*" -and $setting.name -notlike "*PASSWORD*") {
        $credentials.appSettings[$setting.name] = $setting.value
    }
}

# Save to JSON file
$credentialsFile = Join-Path (Get-Location) "credentials.json"
$credentials | ConvertTo-Json -Depth 3 | Out-File -FilePath $credentialsFile -Encoding UTF8

Write-Host "✓ Credentials saved to: $credentialsFile" -ForegroundColor Green
Write-Host ""
Write-Host "Deployment Summary:" -ForegroundColor Green
Write-Host "  Subscription: $subscriptionId"
Write-Host "  Resource Group: $resourceGroupName"
Write-Host "  PostgreSQL Host: $postgresHost"
Write-Host "  Search Service: $searchServiceName"
Write-Host "  Cosmos Account: $cosmosAccountName"
Write-Host "  App Service: https://$appServiceUrl"
Write-Host ""
Write-Host "⚠ IMPORTANT: Keep credentials.json secure!" -ForegroundColor Yellow
Write-Host "  - Do NOT commit to version control"
Write-Host "  - Do NOT share publicly"
Write-Host "  - Consider encrypting before backups"
Write-Host ""

# Offer to open credentials file
$response = Read-Host "Open credentials file? (y/n)"
if ($response -eq 'y') {
    notepad $credentialsFile
}
