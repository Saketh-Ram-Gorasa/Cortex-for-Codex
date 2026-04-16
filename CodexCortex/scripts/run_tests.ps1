param(
    [switch]$BackendMcpOnly,
    [switch]$CodexCortexOnly
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (!(Test-Path $pythonExe)) {
    throw "Missing venv python at $pythonExe. Run .\CodexCortex\scripts\setup_env.cmd or .\CodexCortex\scripts\setup_env.ps1 first."
}

Set-Location $repoRoot

$env:PYTHONPATH = @(
    (Join-Path $repoRoot "CodexCortex"),
    (Join-Path $repoRoot "secondcortex-backend")
) -join ";"

if ($BackendMcpOnly -and $CodexCortexOnly) {
    throw "Use only one of -BackendMcpOnly or -CodexCortexOnly."
}

if (!$BackendMcpOnly) {
    Write-Host "Running CodexCortex adapter tests..."
    & $pythonExe -m unittest discover -s (Join-Path $repoRoot "CodexCortex\tests") -v
}

if (!$CodexCortexOnly) {
    Write-Host "Running backend MCP contract tests..."
    & $pythonExe -m pytest `
        (Join-Path $repoRoot "secondcortex-backend\tests\test_mcp_security_and_keys.py") `
        (Join-Path $repoRoot "secondcortex-backend\tests\test_mcp_fact_search.py") `
        -q
}
