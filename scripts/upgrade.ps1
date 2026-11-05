#requires -Version 5.1
param([string]$CandidateDirectory)
$ErrorActionPreference = 'Stop'
throw 'rc2 requires a fresh installation in a new directory. Use Install.cmd in the new package. In-place upgrade is disabled; existing app, workspace and backups are preserved.'
