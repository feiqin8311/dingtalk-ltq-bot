$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
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

$VenvPython = Join-Path $ProjectDir ".venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    $PythonExe = $VenvPython
} else {
    $PythonExe = "python"
}

$EnvPath = Join-Path $ProjectDir ".env"
$EnvValues = Read-DotEnv -Path $EnvPath

if (-not $env:API_HOST -and $EnvValues["API_HOST"]) {
    $env:API_HOST = $EnvValues["API_HOST"]
}
if (-not $env:API_PORT -and $EnvValues["API_PORT"]) {
    $env:API_PORT = $EnvValues["API_PORT"]
}
if (-not $env:API_AUTH_TOKEN -and $EnvValues["API_AUTH_TOKEN"]) {
    $env:API_AUTH_TOKEN = $EnvValues["API_AUTH_TOKEN"]
}

$ApiHost = if ($env:API_HOST) { $env:API_HOST } else { "0.0.0.0" }
$ApiPort = if ($env:API_PORT) { $env:API_PORT } else { "8000" }

& $PythonExe -m uvicorn api_server:app --host $ApiHost --port $ApiPort
