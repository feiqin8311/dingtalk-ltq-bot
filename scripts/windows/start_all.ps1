$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)

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

function Resolve-AbsolutePath {
    param(
        [string]$PathValue,
        [string]$BaseDir
    )

    if (-not $PathValue) {
        return ""
    }
    if ([System.IO.Path]::IsPathRooted($PathValue)) {
        return [System.IO.Path]::GetFullPath($PathValue)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $BaseDir $PathValue))
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

function Write-CdpDiagnostics {
    param(
        [string]$CdpUrl,
        [string]$BrowserPath,
        [string[]]$BrowserArgs,
        [System.Diagnostics.Process]$StartedProcess = $null
    )

    Write-Warning "CDP diagnostics:"
    Write-Warning "  url=$CdpUrl"
    Write-Warning "  browser=$BrowserPath"
    Write-Warning "  user_data_dir=$($env:LOCAL_CDP_USER_DATA_DIR)"
    Write-Warning "  args=$($BrowserArgs -join ' ')"
    if ($StartedProcess) {
        Write-Warning "  started_process_id=$($StartedProcess.Id)"
        try {
            Write-Warning "  started_process_has_exited=$($StartedProcess.HasExited)"
        } catch {
            Write-Warning "  started_process_has_exited=<unavailable>"
        }
    }

    try {
        $PortConnections = Get-NetTCPConnection -LocalPort ([int]$env:LOCAL_CDP_PORT) -ErrorAction Stop
        if ($PortConnections) {
            foreach ($Connection in $PortConnections) {
                Write-Warning "  port_listener state=$($Connection.State) local=$($Connection.LocalAddress):$($Connection.LocalPort) remote=$($Connection.RemoteAddress):$($Connection.RemotePort) owning_pid=$($Connection.OwningProcess)"
            }
        } else {
            Write-Warning "  port_listener=<none>"
        }
    } catch {
        Write-Warning "  port_listener_check_failed=$($_.Exception.Message)"
    }

    try {
        $Request = Invoke-WebRequest -Method Get -Uri (($CdpUrl.TrimEnd("/")) + "/json/version/") -TimeoutSec 2 -UseBasicParsing
        Write-Warning "  http_status=$($Request.StatusCode)"
        Write-Warning "  http_body=$($Request.Content)"
    } catch {
        Write-Warning "  http_probe_failed=$($_.Exception.Message)"
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
    $env:LOCAL_CDP_USER_DATA_DIR = Resolve-AbsolutePath -PathValue $env:LOCAL_CDP_USER_DATA_DIR -BaseDir $ProjectDir
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
    $StartedProcess = Start-Process -FilePath $env:LOCAL_CDP_BROWSER_BIN -ArgumentList $Args -WorkingDirectory $ProjectDir -PassThru

    $Deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $Deadline) {
        if (Test-CdpHttp -CdpUrl $env:LOCAL_CDP_URL) {
            Write-Host "Started shared CDP: $($env:LOCAL_CDP_URL)"
            return
        }
        Start-Sleep -Milliseconds 500
    }
    Write-CdpDiagnostics -CdpUrl $env:LOCAL_CDP_URL -BrowserPath $env:LOCAL_CDP_BROWSER_BIN -BrowserArgs $Args -StartedProcess $StartedProcess
    throw "Shared CDP did not become ready: $($env:LOCAL_CDP_URL). Chrome may have attached to an existing profile without enabling remote debugging. Close all Chrome/Edge processes and remove LOCAL_CDP_USER_DATA_DIR: $($env:LOCAL_CDP_USER_DATA_DIR)"
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

$EnvValues = Merge-DotEnvFiles -Paths @(
    (Join-Path $ProjectDir ".env"),
    (Join-Path $ProjectDir ".env.windows")
)

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

Ensure-SharedCdp -EnvValues $EnvValues

$ApiHost = if ($EnvValues["API_HOST"]) { $EnvValues["API_HOST"] } else { "0.0.0.0" }
$ApiPort = if ($EnvValues["API_PORT"]) { $EnvValues["API_PORT"] } else { "18081" }

& $PythonExe (Join-Path $ProjectDir 'scripts\run_all.py') --api-host $ApiHost --api-port $ApiPort
