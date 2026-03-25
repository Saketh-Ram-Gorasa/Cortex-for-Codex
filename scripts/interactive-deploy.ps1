$ErrorActionPreference = "Stop"
Write-Host "`n======= Azure SecondCortex - Interactive Deployment =======`n" -ForegroundColor Cyan

Write-Host "[*] Checking Azure CLI..." -ForegroundColor Cyan
try { $null = az version; Write-Host "[+] Azure CLI found" -ForegroundColor Green }
catch { Write-Host "[-] Azure CLI not found" -ForegroundColor Red; exit 1 }

Write-Host "`n======= Step 1: Login to PRIMARY Azure Account =======`n" -ForegroundColor Cyan
Write-Host "[*] Browser will open for authentication" -ForegroundColor Cyan
az login | Out-Null
Write-Host "[+] Logged in" -ForegroundColor Green

Write-Host "`n======= Step 2: Select PRIMARY Subscription =======`n" -ForegroundColor Cyan
$subs = az account list --output json | ConvertFrom-Json
if ($subs.Count -eq 0) { Write-Host "[-] No subscriptions" -ForegroundColor Red; exit 1 }

Write-Host "[*] Available subscriptions:" -ForegroundColor Cyan
for ($i = 0; $i -lt $subs.Count; $i++) {
    Write-Host "  [$($i+1)] $($subs[$i].name)" -ForegroundColor Yellow
}
$choice = [int](Read-Host "Select number (1-$($subs.Count))") - 1
if ($choice -lt 0 -or $choice -ge $subs.Count) { Write-Host "[-] Invalid choice" -ForegroundColor Red; exit 1 }

$primarSubId = $subs[$choice].id
$primaryName = $subs[$choice].name
Write-Host "[+] Selected: $primaryName" -ForegroundColor Green
az account set --subscription $primarSubId | Out-Null

Write-Host "`n======= Step 3: Configure SECONDARY Subscription =======`n" -ForegroundColor Cyan
$useSec = Read-Host "Use different Azure account for Search/Cosmos? (y/n)"
if ($useSec -eq 'y') {
    Write-Host "[*] Logging into secondary account..." -ForegroundColor Cyan
    az login | Out-Null
    Write-Host "[+] Logged in" -ForegroundColor Green
    
    $allSubs = az account list --output json | ConvertFrom-Json
    Write-Host "[*] Available subscriptions:" -ForegroundColor Cyan
    for ($i = 0; $i -lt $allSubs.Count; $i++) {
        Write-Host "  [$($i+1)] $($allSubs[$i].name)" -ForegroundColor Yellow
    }
    $secChoice = [int](Read-Host "Select number (1-$($allSubs.Count))") - 1
    if ($secChoice -lt 0 -or $secChoice -ge $allSubs.Count) { Write-Host "[-] Invalid" -ForegroundColor Red; exit 1 }
    
    $secondarySubId = $allSubs[$secChoice].id
    $secondaryName = $allSubs[$secChoice].name
    Write-Host "[+] Selected: $secondaryName" -ForegroundColor Green
    az account set --subscription $primarSubId | Out-Null
} else {
    $secondarySubId = $primarSubId
    Write-Host "[+] Using same subscription for both" -ForegroundColor Green
}

Write-Host "`n======= Step 4: Resource Names =======`n" -ForegroundColor Cyan
$rgName = Read-Host "Resource group name (default: secondcortex-rg)"
if ([string]::IsNullOrWhiteSpace($rgName)) { $rgName = "secondcortex-rg" }

$appName = Read-Host "App Service name (globally unique, e.g., secondcortex-app-yourname)"
if ([string]::IsNullOrWhiteSpace($appName)) { Write-Host "[-] Name required" -ForegroundColor Red; exit 1 }
if ($appName -notmatch '^[a-z0-9-]{1,60}$') { Write-Host "[-] Only lowercase, numbers, hyphens allowed (max 60 chars)" -ForegroundColor Red; exit 1 }

$location = "East US"
$environment = "production"

Write-Host "`n======= Configuration Summary =======`n" -ForegroundColor Cyan
Write-Host "Primary Subscription: $primaryName" -ForegroundColor Green
Write-Host "Secondary Subscription: $(if ($secondarySubId -eq $primarSubId) { 'Same as primary' } else { $secondaryName })" -ForegroundColor Green
Write-Host "Resource Group: $rgName" -ForegroundColor Green
Write-Host "App Service Name: $appName" -ForegroundColor Green
Write-Host "Location: $location" -ForegroundColor Green

$confirm = Read-Host "`nProceed with deployment? (type 'yes' to continue)"
if ($confirm -ne 'yes') { Write-Host "`n[!] Deployment cancelled" -ForegroundColor Yellow; exit 0 }

Write-Host "`n======= Step 5: Deploying Infrastructure =======`n" -ForegroundColor Cyan
Write-Host "[*] This takes 10-15 minutes..." -ForegroundColor Cyan

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$deployScript = Join-Path $scriptDir "azure-setup.ps1"

if (-not (Test-Path $deployScript)) {
    Write-Host "[-] Deployment script not found: $deployScript" -ForegroundColor Red
    exit 1
}

& $deployScript -primarySubscription $primarSubId -secondarySubscription $secondarySubId -resourceGroupName $rgName -location $location -appServiceName $appName -environment $environment

if ($LASTEXITCODE -ne 0) {
    Write-Host "`n[-] Deployment failed" -ForegroundColor Red
    exit 1
}

Write-Host "`n[+] Deployment completed successfully!" -ForegroundColor Green

Write-Host "`n======= Step 6: Save Credentials =======`n" -ForegroundColor Cyan
$save = Read-Host "Save credentials to JSON file? (y/n)"
if ($save -eq 'y') {
    $credScript = Join-Path $scriptDir "save-credentials.ps1"
    if (Test-Path $credScript) {
        & $credScript -resourceGroupName $rgName -appServiceName $appName
        Write-Host "[+] Credentials saved to credentials.json" -ForegroundColor Green
    }
}

Write-Host "`n======= DEPLOYMENT COMPLETE =======`n" -ForegroundColor Cyan
Write-Host "Next Steps:" -ForegroundColor Green
Write-Host ""
Write-Host "1. Initialize PostgreSQL schema:" -ForegroundColor Yellow
Write-Host "   psql -h $appName-postgres.postgres.database.azure.com -U dbadmin -d secondcortex -f secondcortex-backend/database/migrations/001_create_schema.sql"
Write-Host ""
Write-Host "2. Create Azure Search index:" -ForegroundColor Yellow
Write-Host "   .\scripts\create-search-index.ps1 -searchServiceName $appName-search -apiKey <api-key-from-portal>"
Write-Host ""
Write-Host "3. Deploy backend to App Service:" -ForegroundColor Yellow
Write-Host "   .\scripts\app-service-deploy.ps1 -appServiceName $appName -resourceGroupName $rgName"
Write-Host ""
Write-Host "4. Seed demo data (optional):" -ForegroundColor Yellow
Write-Host "   python .\secondcortex-backend\scripts\seed_demo_snapshots.py"
Write-Host ""
Write-Host "Your new App Service URL:" -ForegroundColor Cyan
Write-Host "   https://$appName.azurewebsites.net"
Write-Host ""
