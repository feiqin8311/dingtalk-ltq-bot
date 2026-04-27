$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
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

$VenvPython = Join-Path $ProjectDir ".venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    $PythonExe = $VenvPython
} else {
    $PythonExe = "python"
}

$ResolvedCdpBrowser = Resolve-PlaywrightChromium -PythonExe $PythonExe
if ($ResolvedCdpBrowser) {
    $env:LOCAL_CDP_BROWSER_BIN = $ResolvedCdpBrowser
}

& $PythonExe (Join-Path $ProjectDir 'main.py')
