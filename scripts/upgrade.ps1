param([Parameter(Mandatory=$true)][string]$CandidateDirectory)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$exe = Join-Path $root 'app/WorkThread.exe'
$candidate = Join-Path $CandidateDirectory 'app'
if (!(Test-Path (Join-Path $candidate 'WorkThread.exe'))) { throw 'Candidate app missing' }
if (Get-Process WorkThread -ErrorAction SilentlyContinue) { throw 'Close WorkThread before upgrading' }
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backup = Join-Path $root "upgrade-$stamp.7z"
& $exe --workspace (Join-Path $root 'workspace') backup $backup
if ($LASTEXITCODE -ne 0) { throw 'Backup failed; upgrade aborted' }
$old = Join-Path $root "app-rollback-$stamp"
Move-Item (Join-Path $root 'app') $old
try {
    Copy-Item $candidate (Join-Path $root 'app') -Recurse
    & $exe --workspace (Join-Path $root 'workspace') doctor
    if ($LASTEXITCODE -ne 0) { throw 'Candidate health check failed' }
    Write-Host "Upgrade complete. Keep $backup and $old until acceptance."
} catch {
    Remove-Item (Join-Path $root 'app') -Recurse -Force
    Move-Item $old (Join-Path $root 'app')
    Write-Host 'Previous program restored. Restore the matching encrypted backup before using an older schema.'
    throw
}
