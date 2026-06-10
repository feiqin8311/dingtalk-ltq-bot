$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectDir = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))
Set-Location $ProjectDir

$ApiScript = Join-Path $ProjectDir "scripts\windows\start_api.ps1"
$TunnelScript = Join-Path $ProjectDir "scripts\start_reverse_tunnel.ps1"

Start-Process powershell -ArgumentList @(
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    $ApiScript
) -WorkingDirectory $ProjectDir

Start-Sleep -Seconds 2

if ($env:USE_TAILSCALE_UPSTREAM -eq "1") {
    Write-Host "USE_TAILSCALE_UPSTREAM=1, skipping reverse SSH tunnel."
    exit 0
}

& $TunnelScript
