#Requires -Version 5.1
<#
.SYNOPSIS
    Deploy SecondCortex backend to Azure App Service
.PARAMETER appServiceName
    Name of the App Service
.PARAMETER resourceGroupName
    Resource group name
.PARAMETER backendPath
    Path to backend directory (default: ./secondcortex-backend)
.PARAMETER deploymentSlot
    Deployment slot name (optional, for staged deployments)
.EXAMPLE
    .\app-service-deploy.ps1 `
        -appServiceName "secondcortex-app" `
        -resourceGroupName "secondcortex-rg"
#>

param(
    [Parameter(Mandatory=$true)]
    [string]$appServiceName,

    [Parameter(Mandatory=$true)]
    [string]$resourceGroupName,

    [Parameter(Mandatory=$false)]
    [string]$backendPath = "./secondcortex-backend",

    [Parameter(Mandatory=$false)]
    [string]$deploymentSlot = $null,

    [Parameter(Mandatory=$false)]
    [ValidateSet("production", "staging", "development")]
    [string]$environment = "production"
)

$ErrorActionPreference = "Stop"

Write-Host "Starting App Service deployment..." -ForegroundColor Cyan

# Validate backend directory
if (-not (Test-Path $backendPath)) {
    Write-Host "✗ Backend directory not found: $backendPath" -ForegroundColor Red
    exit 1
}

Write-Host "✓ Backend directory found: $backendPath" -ForegroundColor Green

# Create deployment package
$zipFile = "deployment-$((Get-Date).ToString('yyyyMMdd-HHmmss')).zip"
$zipPath = Join-Path (Get-Location) $zipFile

Write-Host "Creating deployment package: $zipFile" -ForegroundColor Cyan

# Build Python requirements
Write-Host "Installing Python dependencies..." -ForegroundColor Cyan
$requirementsFile = Join-Path $backendPath "requirements.txt"
if (Test-Path $requirementsFile) {
    # Create temp directory for dependencies
    $tempDir = Join-Path $backendPath "temp_deploy"
    if (Test-Path $tempDir) {
        Remove-Item $tempDir -Recurse -Force
    }
    New-Item -ItemType Directory -Path $tempDir | Out-Null
    
    # Install to temp directory
    pip install -r $requirementsFile -t $tempDir --quiet
    Write-Host "✓ Dependencies installed" -ForegroundColor Green
}

# Compress backend code
Write-Host "Packaging code..." -ForegroundColor Cyan
Compress-Archive `
    -Path "$backendPath/*" `
    -DestinationPath $zipPath `
    -Force

Write-Host "✓ Package created: $zipPath" -ForegroundColor Green

# Deploy to App Service
Write-Host "Deploying to App Service..." -ForegroundColor Cyan

if ($deploymentSlot) {
    Write-Host "Deploying to slot: $deploymentSlot" -ForegroundColor Yellow
    az webapp deployment source config-zip `
        --resource-group $resourceGroupName `
        --name $appServiceName `
        --slot $deploymentSlot `
        --src-path $zipPath
    
    Write-Host "✓ Deployed to slot: $deploymentSlot" -ForegroundColor Green
    Write-Host ""
    Write-Host "Swap slot to production?"
    $response = Read-Host "Enter 'yes' to swap now, or 'no' to skip"
    if ($response -eq 'yes') {
        az webapp deployment slot swap `
            --resource-group $resourceGroupName `
            --name $appServiceName `
            --slot $deploymentSlot
        Write-Host "✓ Slot swapped to production" -ForegroundColor Green
    }
} else {
    az webapp deployment source config-zip `
        --resource-group $resourceGroupName `
        --name $appServiceName `
        --src-path $zipPath
    
    Write-Host "✓ Deployed to production" -ForegroundColor Green
}

# Restart App Service
Write-Host "Restarting App Service..." -ForegroundColor Cyan
az webapp restart `
    --resource-group $resourceGroupName `
    --name $appServiceName

Write-Host "✓ App Service restarted" -ForegroundColor Green

# Stream logs
Write-Host ""
Write-Host "Streaming logs (press Ctrl+C to stop)..." -ForegroundColor Cyan
Write-Host ""

try {
    az webapp log tail `
        --resource-group $resourceGroupName `
        --name $appServiceName
} catch {
    Write-Host "Log streaming ended" -ForegroundColor Yellow
}

# Verify deployment
Write-Host ""
Write-Host "Verifying deployment..." -ForegroundColor Cyan
$appServiceUrl = az webapp show `
    --name $appServiceName `
    --resource-group $resourceGroupName `
    --query defaultHostName -o tsv

$healthUrl = "https://$appServiceUrl/health"
Write-Host "Health check endpoint: $healthUrl" -ForegroundColor Cyan

$maxRetries = 10
$retryCount = 0
while ($retryCount -lt $maxRetries) {
    try {
        $response = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 5
        if ($response.StatusCode -eq 200) {
            Write-Host "✓ Health check passed!" -ForegroundColor Green
            Write-Host ""
            Write-Host "Deployment complete!" -ForegroundColor Green
            Write-Host "App Service URL: https://$appServiceUrl" -ForegroundColor Green
            break
        }
    } catch {
        $retryCount++
        Write-Host "⏳ Waiting for app to start ($retryCount/$maxRetries)..." -ForegroundColor Yellow
        Start-Sleep -Seconds 5
    }
}

if ($retryCount -eq $maxRetries) {
    Write-Host "⚠ Health check failed after $maxRetries attempts" -ForegroundColor Yellow
    Write-Host "Check logs at: https://portal.azure.com/"
}

# Cleanup
Write-Host ""
$response = Read-Host "Clean up deployment package? (y/n)"
if ($response -eq 'y') {
    Remove-Item $zipPath -Force
    Write-Host "✓ Deployment package removed" -ForegroundColor Green
}

# Cleanup temp directory if exists
$tempDir = Join-Path $backendPath "temp_deploy"
if (Test-Path $tempDir) {
    Remove-Item $tempDir -Recurse -Force -ErrorAction SilentlyContinue
}
