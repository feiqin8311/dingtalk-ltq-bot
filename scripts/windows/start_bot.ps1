$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectDir = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))
Set-Location $ProjectDir

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

function Resolve-SystemBrowser {
    $Candidates = @(
        (Join-Path ${env:ProgramFiles} "Google\Chrome\Application\chrome.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Google\Chrome\Application\chrome.exe"),
        (Join-Path ${env:ProgramFiles} "Microsoft\Edge\Application\msedge.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Microsoft\Edge\Application\msedge.exe")
    )
    foreach ($Candidate in $Candidates) {
        if ($Candidate -and (Test-Path $Candidate)) {
            return $Candidate
        }
    }
    return ""
}

function Test-CdpHttp {
    param([string]$CdpUrl)
    try {
        $Response = Invoke-RestMethod -Method Get -Uri (($CdpUrl.TrimEnd("/")) + "/json/version/") -TimeoutSec 2
        return [bool]$Response.webSocketDebuggerUrl
    } catch {
        return $false
    }
}

function Ensure-SharedCdp {
    param([hashtable]$EnvValues)

    foreach ($Key in @("LOCAL_CDP_HOST", "LOCAL_CDP_PORT", "LOCAL_CDP_URL", "LOCAL_CDP_USER_DATA_DIR", "LOCAL_CDP_BROWSER_BIN", "LOCAL_CDP_HEADLESS", "LOCAL_CDP_EXTERNAL_ONLY")) {
        if (-not (Get-Item "Env:$Key" -ErrorAction SilentlyContinue) -and $EnvValues[$Key]) {
            Set-Item "Env:$Key" $EnvValues[$Key]
        }
    }
    if (-not $env:LOCAL_CDP_HOST) { $env:LOCAL_CDP_HOST = "127.0.0.1" }
    if (-not $env:LOCAL_CDP_PORT) { $env:LOCAL_CDP_PORT = "19444" }
    if (-not $env:LOCAL_CDP_URL) { $env:LOCAL_CDP_URL = "http://$($env:LOCAL_CDP_HOST):$($env:LOCAL_CDP_PORT)" }
    if (-not $env:LOCAL_CDP_USER_DATA_DIR) { $env:LOCAL_CDP_USER_DATA_DIR = ".\data\chrome-cdp-windows" }
    $env:LOCAL_CDP_EXTERNAL_ONLY = "true"

    if (Test-CdpHttp -CdpUrl $env:LOCAL_CDP_URL) {
        Write-Host "Shared CDP is ready: $($env:LOCAL_CDP_URL)"
        return
    }
    if ($env:LOCAL_CDP_HOST -notin @("127.0.0.1", "localhost")) {
        throw "Shared CDP is not reachable at $($env:LOCAL_CDP_URL). Remote CDP must be started separately."
    }
    if (-not $env:LOCAL_CDP_BROWSER_BIN) {
        $env:LOCAL_CDP_BROWSER_BIN = Resolve-SystemBrowser
    }
    if (-not $env:LOCAL_CDP_BROWSER_BIN -or -not (Test-Path $env:LOCAL_CDP_BROWSER_BIN)) {
        throw "Chrome/Edge not found. Set LOCAL_CDP_BROWSER_BIN to a system Chrome or Edge path."
    }

    New-Item -ItemType Directory -Force -Path $env:LOCAL_CDP_USER_DATA_DIR | Out-Null
    $Args = @(
        "--remote-debugging-address=$($env:LOCAL_CDP_HOST)",
        "--remote-debugging-port=$($env:LOCAL_CDP_PORT)",
        "--user-data-dir=$($env:LOCAL_CDP_USER_DATA_DIR)",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
        "--new-window",
        "about:blank"
    )
    if (($env:LOCAL_CDP_HEADLESS).ToLower() -in @("1", "true", "yes", "on")) {
        $Args = @("--headless=new") + $Args
    }
    Start-Process -FilePath $env:LOCAL_CDP_BROWSER_BIN -ArgumentList $Args -WorkingDirectory $ProjectDir

    $Deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $Deadline) {
        if (Test-CdpHttp -CdpUrl $env:LOCAL_CDP_URL) {
            Write-Host "Started shared CDP: $($env:LOCAL_CDP_URL)"
            return
        }
        Start-Sleep -Milliseconds 500
    }
    throw "Shared CDP did not become ready: $($env:LOCAL_CDP_URL)"
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

Ensure-SharedCdp -EnvValues $EnvValues

& $PythonExe (Join-Path $ProjectDir 'main.py')
