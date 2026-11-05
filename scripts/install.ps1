#requires -Version 5.1
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding
$root = Split-Path -Parent $PSScriptRoot
$exe = Join-Path $root 'app\WorkThread.exe'
if (!(Test-Path -LiteralPath $exe -PathType Leaf)) { throw 'WorkThread.exe missing; extract the whole candidate ZIP first' }
if (Get-Process WorkThread -ErrorAction SilentlyContinue) { throw 'Close WorkThread before initializing this installation' }
foreach ($space in @('workspace', 'acceptance')) {
    $work = Join-Path $root $space
    & $exe --workspace $work init
    if ($LASTEXITCODE -ne 0) { throw "Initialization requires attention: $space; inspect the deployment report, custom files are preserved" }
    & $exe --workspace $work doctor
    if ($LASTEXITCODE -ne 0) { throw "Health check failed: $space" }
}
Write-Host 'Both independent workspaces initialized. Start.cmd opens the formal workspace; acceptance remains empty until an explicit demo command.'
Write-Host 'WorkBuddy: use GUI Open Folder on workspace\agent-workspace or acceptance\agent-workspace, then confirm trust. No formal schedules are installed.'
