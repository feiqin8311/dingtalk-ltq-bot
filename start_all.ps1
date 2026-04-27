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

function Test-NapCatHttp {
    param(
        [string]$BaseUrl,
        [string]$Token = ""
    )
    try {
        $Headers = @{}
        if ($Token) {
            $Headers = @{ 'Authorization' = "Bearer $Token" }
        }
        $Response = Invoke-RestMethod `
            -Method Post `
            -Uri (($BaseUrl.TrimEnd("/")) + "/get_status") `
            -Headers $Headers `
            -ContentType "application/json" `
            -Body "{}" `
            -TimeoutSec 3
        return $null -ne $Response
    } catch {
        return $false
    }
}

function Wait-NapCatHttp {
    param(
        [string]$BaseUrl,
        [string]$Token,
        [int]$WaitSeconds
    )

    $Deadline = (Get-Date).AddSeconds($WaitSeconds)
    while ((Get-Date) -lt $Deadline) {
        if (Test-NapCatHttp -BaseUrl $BaseUrl -Token $Token) {
            return
        }
        Start-Sleep -Seconds 2
    }
    throw "NapCat HTTP API is not available at $BaseUrl after $WaitSeconds seconds."
}

$EnvPath = Join-Path $ProjectDir ".env"
$EnvValues = Read-DotEnv -Path $EnvPath

$QQApiBaseUrl = $EnvValues["QQ_API_BASE_URL"]
if (-not $QQApiBaseUrl) {
    $QQApiBaseUrl = "http://127.0.0.1:6702"
}
$QQApiToken = $EnvValues["QQ_API_TOKEN"]
if (-not $QQApiToken) {
    $QQApiToken = ""
}

$NapCatWaitSeconds = 90
if ($EnvValues["NAPCAT_WAIT_SECONDS"]) {
    $NapCatWaitSeconds = [int]$EnvValues["NAPCAT_WAIT_SECONDS"]
}

$NapCatLauncher = $EnvValues["NAPCAT_LAUNCHER_PATH"]
if (-not $NapCatLauncher) {
    $NapCatLauncher = Join-Path $ProjectDir "NapCat.Shell\launcher.bat"
}
if (-not [System.IO.Path]::IsPathRooted($NapCatLauncher)) {
    $NapCatLauncher = Join-Path $ProjectDir $NapCatLauncher
}

if (-not (Test-NapCatHttp -BaseUrl $QQApiBaseUrl -Token $QQApiToken)) {
    if (-not (Test-Path $NapCatLauncher)) {
        throw "NapCat launcher not found: $NapCatLauncher. Put NapCat.Shell under the project root or set NAPCAT_LAUNCHER_PATH in .env."
    }
    Start-Process -FilePath $NapCatLauncher -WorkingDirectory (Split-Path -Parent $NapCatLauncher)
    Wait-NapCatHttp -BaseUrl $QQApiBaseUrl -Token $QQApiToken -WaitSeconds $NapCatWaitSeconds
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
