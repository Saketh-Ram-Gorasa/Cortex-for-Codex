param(
    [string]$PythonLauncher = "py",
    [string]$PythonVersion = "3.13",
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$venvPath = Join-Path $repoRoot ".venv"
$pythonExe = Join-Path $venvPath "Scripts\python.exe"

Set-Location $repoRoot

function Get-PythonCommand {
    param(
        [string]$Launcher,
        [string]$Version
    )

    if (Test-Path -LiteralPath $Launcher) {
        return @{
            Command = $Launcher
            Args    = @()
        }
    }

    if ($Launcher -eq "py") {
        if (Get-Command "py" -ErrorAction SilentlyContinue) {
            return @{
                Command = "py"
                Args    = @("-$Version")
            }
        }

        if (Get-Command "python" -ErrorAction SilentlyContinue) {
            return @{
                Command = "python"
                Args    = @()
            }
        }

        throw "Python launcher 'py' and fallback 'python' were not found. Install CPython $Version, then rerun this script."
    }

    if (!(Get-Command $Launcher -ErrorAction SilentlyContinue)) {
        throw "Python launcher '$Launcher' was not found. Install CPython $Version or pass -PythonLauncher <path-to-python.exe>."
    }

    return @{
        Command = $Launcher
        Args    = @()
    }
}

$python = Get-PythonCommand -Launcher $PythonLauncher -Version $PythonVersion
$pythonVersion = (& $python.Command @($python.Args) -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')").Trim()

if ($pythonVersion -ne $PythonVersion) {
    throw "Expected Python $PythonVersion, but '$($python.Command)' resolved to Python $pythonVersion. Install CPython $PythonVersion and rerun."
}

$launcherText = if ($python.Args.Count -gt 0) { "$($python.Command) $($python.Args -join ' ')" } else { $python.Command }

Write-Host "Creating Python environment at $venvPath using $launcherText"
& $python.Command @($python.Args) -m venv --clear $venvPath

if (!(Test-Path $pythonExe)) {
    throw "Expected venv python was not created at $pythonExe"
}

if ($SkipInstall) {
    Write-Host "Created venv and skipped dependency installation."
    exit 0
}

& $pythonExe -m ensurepip --upgrade
& $pythonExe -m pip install --upgrade pip setuptools wheel
& $pythonExe -m pip install -r (Join-Path $repoRoot "requirements-codex.txt")

Write-Host "Codex environment ready."
Write-Host "Python: $pythonExe"
Write-Host "MCP command: $(Join-Path $venvPath 'Scripts\codexcortex-mcp.exe')"
