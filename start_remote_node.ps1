$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectDir

$ApiScript = Join-Path $ProjectDir "start_api.ps1"
$TunnelScript = Join-Path $ProjectDir "scripts\start_reverse_tunnel.ps1"

Start-Process powershell -ArgumentList @(
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    $ApiScript
) -WorkingDirectory $ProjectDir

Start-Sleep -Seconds 2

& $TunnelScript
