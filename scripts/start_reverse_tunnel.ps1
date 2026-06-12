$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ServerHost = if ($env:SERVER_HOST) { $env:SERVER_HOST } else { "121.41.4.126" }
$ServerUser = if ($env:SERVER_USER) { $env:SERVER_USER } else { "root" }
$RemoteBindPort = if ($env:REMOTE_BIND_PORT) { $env:REMOTE_BIND_PORT } else { "18781" }
$LocalApiPort = if ($env:LOCAL_API_PORT) { $env:LOCAL_API_PORT } else { "18081" }
$ServerSshPort = if ($env:SERVER_SSH_PORT) { $env:SERVER_SSH_PORT } else { "22" }

ssh `
  -o ExitOnForwardFailure=yes `
  -o ServerAliveInterval=30 `
  -o ServerAliveCountMax=3 `
  -N `
  -p $ServerSshPort `
  -R ("127.0.0.1:{0}:127.0.0.1:{1}" -f $RemoteBindPort, $LocalApiPort) `
  ("{0}@{1}" -f $ServerUser, $ServerHost)
