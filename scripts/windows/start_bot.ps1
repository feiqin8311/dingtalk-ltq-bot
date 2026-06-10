$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectDir = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))
Set-Location $ProjectDir

function Resolve-PlaywrightChromium {
    param([string]$PythonExe)

    $Script = @'
import sys
from playwright.sync_api import sync_playwright
try:
    with sync_playwright() as p:
        path = p.chromium.executable_path
        if path:
            sys.stdout.write(path)
except Exception:
    pass
'@

    try {
        $ResolvedPath = (& $PythonExe -c $Script).Trim()
        if ($ResolvedPath -and (Test-Path $ResolvedPath)) {
            return $ResolvedPath
        }
    } catch {
        return ""
    }

    return ""
}

function Read-DotEnv {
    param([string]$Path)
    $Values = @{}
    if (-not (Test-Path $Path)) {
        return $Values
    }

    Get-Content -LiteralPath $Path -Encoding UTF8 | ForEach-Object {
        $Line = $_.Trim()
        if (-not $Line -or $Line.StartsWith("#") -or -not $Line.Contains("=")) {
            return
        }
        $Key, $Value = $Line.Split("=", 2)
        $Values[$Key.Trim()] = $Value.Trim().Trim('"').Trim("'")
    }
    return $Values
}

function Merge-DotEnvFiles {
    param([string[]]$Paths)
    $Merged = @{}
    foreach ($Path in $Paths) {
        $Current = Read-DotEnv -Path $Path
        foreach ($Key in $Current.Keys) {
            $Merged[$Key] = $Current[$Key]
        }
    }
    return $Merged
}

$VenvPython = Join-Path $ProjectDir ".venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    $PythonExe = $VenvPython
} else {
    $PythonExe = "python"
}

$EnvValues = Merge-DotEnvFiles -Paths @(
    (Join-Path $ProjectDir ".env"),
    (Join-Path $ProjectDir ".env.windows")
)

if (-not $env:LOCAL_CDP_BROWSER_BIN -and $EnvValues["LOCAL_CDP_BROWSER_BIN"]) {
    $env:LOCAL_CDP_BROWSER_BIN = $EnvValues["LOCAL_CDP_BROWSER_BIN"]
}

$ResolvedCdpBrowser = Resolve-PlaywrightChromium -PythonExe $PythonExe
if ($ResolvedCdpBrowser) {
    $env:LOCAL_CDP_BROWSER_BIN = $ResolvedCdpBrowser
}

& $PythonExe (Join-Path $ProjectDir 'main.py')
