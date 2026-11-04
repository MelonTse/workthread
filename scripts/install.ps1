$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
& (Join-Path $root 'app/WorkThread.exe') --workspace (Join-Path $root 'workspace') init
if ($LASTEXITCODE -ne 0) { throw 'Initialization failed' }
& (Join-Path $root 'app/WorkThread.exe') --workspace (Join-Path $root 'workspace') doctor
if ($LASTEXITCODE -ne 0) { throw 'Health check failed' }
Write-Host 'Initialized. Start with Start.cmd. Formal AI schedules remain disabled.'
