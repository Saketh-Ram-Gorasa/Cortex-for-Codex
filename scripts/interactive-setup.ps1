#Requires -Version 5.1
param([Parameter(Mandatory=$false)][string]$scriptPath = $PSScriptRoot)
$ErrorActionPreference = "Stop"

Write-Host "`n================== Azure SecondCortex Deployment - Interactive Setup ==================`n" -ForegroundColor Cyan

Write-Host "ℹ Checking Azure CLI installation..." -ForegroundColor Cyan
try {
    $azVersion = az --version 2>&1 | Select-Object -First 1
    Write-Host "✓ Azure CLI found: $azVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ Azure CLI not found. Please install from https://docs.microsoft.com/cli/azure/install-azure-cli" -ForegroundColor Red
    exit 1
}

Write-Host "`n================== Step 1: Login to Your PRIMARY Azure Account ==================`n" -ForegroundColor Cyan
Write-Host "ℹ This will open your browser for authentication..." -ForegroundColor Cyan
Write-Host "ℹ Use the account where you want App Service & PostgreSQL" -ForegroundColor Cyan

az login
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ Login failed" -ForegroundColor Red
    exit 1
}
Write-Host "✓ Logged into primary account" -ForegroundColor Green

Write-Host "`n================== Step 2: Choose PRIMARY Subscription (App Service & PostgreSQL) ==================`n" -ForegroundColor Cyan

$primarySubscriptions = @(az account list --output json | ConvertFrom-Json)

if ($primarySubscriptions.Count -eq 0) {
    Write-Host "✗ No subscriptions found. Login may have failed." -ForegroundColor Red
    exit 1
}

Write-Host "ℹ Available subscriptions:" -ForegroundColor Cyan
for ($i = 0; $i -lt $primarySubscriptions.Count; $i++) {
    Write-Host "  [$($i + 1)] $($primarySubscriptions[$i].name) ($($primarySubscriptions[$i].id))" -ForegroundColor Yellow
}

$primaryChoice = Read-Host "Enter subscription number (1-$($primarySubscriptions.Count))"
$primaryIndex = [int]$primaryChoice - 1

if ($primaryIndex -lt 0 -or $primaryIndex -ge $primarySubscriptions.Count) {
    Write-Host "✗ Invalid choice" -ForegroundColor Red
    exit 1
}

$primarySubscription = $primarySubscriptions[$primaryIndex].id
$primaryName = $primarySubscriptions[$primaryIndex].name

Write-Host "✓ Selected primary subscription: $primaryName" -ForegroundColor Green
Write-Host "✓ ID: $primarySubscription" -ForegroundColor Green

az account set --subscription $primarySubscription
Write-Host "✓ Switched to primary subscription" -ForegroundColor Green

Write-Host "`n================== Step 3: Configure SECONDARY Subscription (Search & Cosmos) ==================`n" -ForegroundColor Cyan
$useSecondary = Read-Host "Use different Azure account for Search/Cosmos? (y/n)"

if ($useSecondary -eq 'y') {
    Write-Host "ℹ Logging into secondary Azure account..." -ForegroundColor Cyan
    Write-Host "ℹ This will open your browser for authentication..." -ForegroundColor Cyan
    
    az login
    if ($LASTEXITCODE -ne 0) {
        Write-Host "✗ Login failed" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "✓ Logged into secondary account" -ForegroundColor Green
    
    $allSubscriptions = @(az account list --output json | ConvertFrom-Json)
    
    Write-Host "ℹ Available subscriptions in secondary account:" -ForegroundColor Cyan
    for ($i = 0; $i -lt $allSubscriptions.Count; $i++) {
        Write-Host "  [$($i + 1)] $($allSubscriptions[$i].name) ($($allSubscriptions[$i].id))" -ForegroundColor Yellow
    }
    
    $secondaryChoice = Read-Host "Enter subscription number for secondary account (1-$($allSubscriptions.Count))"
    $secondaryIndex = [int]$secondaryChoice - 1
    
    if ($secondaryIndex -lt 0 -or $secondaryIndex -ge $allSubscriptions.Count) {
        Write-Host "✗ Invalid choice" -ForegroundColor Red
        exit 1
    }
    
    $secondarySubscription = $allSubscriptions[$secondaryIndex].id
    $secondaryName = $allSubscriptions[$secondaryIndex].name
    
    Write-Host "✓ Selected secondary subscription: $secondaryName" -ForegroundColor Green
    Write-Host "✓ ID: $secondarySubscription" -ForegroundColor Green
    
    az account set --subscription $primarySubscription
    Write-Host "✓ Switched back to primary subscription" -ForegroundColor Green
} else {
    $secondarySubscription = $primarySubscription
    Write-Host "✓ Using same subscription for both accounts" -ForegroundColor Green
}

Write-Host "`n================== Step 4: Configure Resource Names ==================`n" -ForegroundColor Cyan

$resourceGroupName = Read-Host "Resource group name (default: secondcortex-rg)"
if ([string]::IsNullOrWhiteSpace($resourceGroupName)) { $resourceGroupName = "secondcortex-rg" }

$appServiceName = Read-Host "App service name (must be globally unique, e.g., secondcortex-app-<yourname>)"
if ([string]::IsNullOrWhiteSpace($appServiceName)) {
    Write-Host "✗ App service name is required" -ForegroundColor Red
    exit 1
}

if ($appServiceName -notmatch '^[a-z0-9-]{1,60}$') {
    Write-Host "✗ Invalid app service name. Use lowercase, numbers, hyphens only (max 60 chars)" -ForegroundColor Red
    exit 1
}

$location = "East US"
$environment = "production"

Write-Host "ℹ Configuration confirmed:" -ForegroundColor Cyan
Write-Host "  Primary Subscription: $primaryName" -ForegroundColor Green
Write-Host "  Secondary Subscription: $(if($secondarySubscription -eq $primarySubscription) { 'Same as primary' } else { 'Different account' })" -ForegroundColor Green
Write-Host "  Resource Group: $resourceGroupName" -ForegroundColor Green
Write-Host "  App Service Name: $appServiceName" -ForegroundColor Green
Write-Host "  Location: $location" -ForegroundColor Green
Write-Host "  Environment: $environment" -ForegroundColor Green

$confirm = Read-Host "Proceed with deployment? (yes/no)"
if ($confirm -ne 'yes') {
    Write-Host "⚠ Deployment cancelled" -ForegroundColor Yellow
    exit 0
}

Write-Host "`n================== Step 5: Running Deployment ==================`n" -ForegroundColor Cyan
Write-Host "ℹ This will take 10-15 minutes..." -ForegroundColor Cyan

$deploymentScript = Join-Path $scriptPath "azure-setup.ps1"
if (-not (Test-Path $deploymentScript)) {
    Write-Host "✗ Deployment script not found: $deploymentScript" -ForegroundColor Red
    exit 1
}

& $deploymentScript `
    -primarySubscription $primarySubscription `
    -secondarySubscription $secondarySubscription `
    -resourceGroupName $resourceGroupName `
    -location $location `
    -appServiceName $appServiceName `
    -environment $environment

if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ Deployment failed with exit code: $LASTEXITCODE" -ForegroundColor Red
    exit 1
}

Write-Host "✓ Deployment completed successfully!" -ForegroundColor Green

Write-Host "`n================== Step 6: Save Credentials ==================`n" -ForegroundColor Cyan

$saveCredentials = Read-Host "Save credentials to file? (y/n)"
if ($saveCredentials -eq 'y') {
    $credentialsScript = Join-Path $scriptPath "save-credentials.ps1"
    if (Test-Path $credentialsScript) {
        Write-Host "ℹ Saving credentials..." -ForegroundColor Cyan
        & $credentialsScript `
            -resourceGroupName $resourceGroupName `
            -appServiceName $appServiceName
        Write-Host "✓ Credentials saved to credentials.json" -ForegroundColor Green
    }
}

Write-Host "`n================== Deployment Complete! ==================`n" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Green
Write-Host ""
Write-Host "1. Initialize PostgreSQL schema:" -ForegroundColor Yellow
Write-Host "   psql -h $appServiceName-postgres.postgres.database.azure.com -U dbadmin -d secondcortex -f secondcortex-backend/database/migrations/001_create_schema.sql"
Write-Host ""
Write-Host "2. Create Search index:" -ForegroundColor Yellow
Write-Host "   .\scripts\create-search-index.ps1 -searchServiceName $appServiceName-search -apiKey <api-key>"
Write-Host ""
Write-Host "3. Deploy backend code:" -ForegroundColor Yellow
Write-Host "   .\scripts\app-service-deploy.ps1 -appServiceName $appServiceName -resourceGroupName $resourceGroupName"
Write-Host ""
Write-Host "4. Seed demo data (optional):" -ForegroundColor Yellow
Write-Host "   python .\secondcortex-backend\scripts\seed_demo_snapshots.py"
Write-Host ""
Write-Host "Your new App Service URL:" -ForegroundColor Cyan
Write-Host "   https://$appServiceName.azurewebsites.net"
Write-Host ""
