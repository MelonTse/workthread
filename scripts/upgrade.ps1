#requires -Version 5.1
param([Parameter(Mandatory=$true)][string]$InstallRoot,
      [string]$ReleaseDirectory, [switch]$Apply)
$ErrorActionPreference = 'Stop'
$exe = Join-Path (Split-Path -Parent $PSScriptRoot) 'app\WorkThread.exe'
& $exe --maintenance inspect $InstallRoot
if ($LASTEXITCODE -ne 0) { throw 'Could not identify installation; original data untouched.' }
if (-not $Apply) { return }
if (-not $ReleaseDirectory) { throw 'Supply the directory containing the signed ZIP, update.json and update.sig.' }
$manifest = Get-Content -LiteralPath (Join-Path $ReleaseDirectory 'update.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($manifest.asset -notmatch '^WorkThread-[0-9.]+(rc[0-9]+)?-windows-x64\.zip$') { throw 'Invalid ZIP filename.' }
$zip = Join-Path $ReleaseDirectory $manifest.asset
if ((Read-Host 'Close WorkThread and WorkBuddy. Type UPDATE to snapshot both workspaces and switch versions') -cne 'UPDATE') { return }
& $exe --maintenance bootstrap $InstallRoot $zip $ReleaseDirectory --confirmed
if ($LASTEXITCODE -ne 0) { throw 'Upgrade did not complete. Inspect the diagnostic before retrying.' }
