#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'WorkThread'),
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-fA-F0-9]{64}$')][string]$ExpectedSha256,
    [string]$PackagePath
)
$ErrorActionPreference = 'Stop'
# WorkBuddy or pwsh can launch Windows PowerShell with a Core-only module path.
if ($PSVersionTable.PSEdition -eq 'Desktop') {
    $env:PSModulePath = (Join-Path $PSHOME 'Modules') + [IO.Path]::PathSeparator + $env:PSModulePath
}
$version = '1.0.0rc7'
$name = "WorkThread-$version-windows-x64"
$system = Get-CimInstance Win32_OperatingSystem
$arch = (Get-CimInstance Win32_Processor | Select-Object -First 1).Architecture
if ($arch -ne 9 -or [int]$system.BuildNumber -lt 19045) { throw 'Requires Windows x64 build 19045 or later.' }
$root = [IO.Path]::GetFullPath($InstallRoot).TrimEnd('\')
if ($root -notmatch '^[a-zA-Z]:\\' -or $root.Length -lt 4) { throw 'Choose a directory on a local drive.' }
if (Test-Path -LiteralPath $root) {
    $identity = Join-Path $root 'BUILD_INFO.json'
    if (Test-Path -LiteralPath $identity -PathType Leaf) {
        $info = Get-Content -LiteralPath $identity -Raw -Encoding UTF8 | ConvertFrom-Json
        $pointer = Join-Path $root '.workthread-updates\active.json'
        if (Test-Path -LiteralPath $pointer -PathType Leaf) {
            $sha = (Get-Content -LiteralPath $pointer -Raw -Encoding UTF8 | ConvertFrom-Json).commit_sha
            if ($sha -match '^[a-f0-9]{40}$') {
                $active = Join-Path $root ".workthread-updates\versions\$sha\BUILD_INFO.json"
                $info = Get-Content -LiteralPath $active -Raw -Encoding UTF8 | ConvertFrom-Json
            }
        }
        throw "Existing WorkThread $($info.version) ($($info.commit_sha)) at $root. Use another destination or the installed update procedure."
    }
    if (!(Test-Path -LiteralPath $root -PathType Container) -or (Get-ChildItem -LiteralPath $root -Force | Select-Object -First 1)) {
        throw "Destination contains existing files: $root"
    }
}
$drive = [IO.DriveInfo]::new([IO.Path]::GetPathRoot($root))
if ($drive.DriveType -ne 'Fixed') { throw 'Choose a fixed local drive.' }
$parent = Split-Path -Parent $root
[IO.Directory]::CreateDirectory($parent) | Out-Null
for ($dir = [IO.DirectoryInfo]::new($root); $null -ne $dir; $dir = $dir.Parent) {
    if ($dir.Exists -and ($dir.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw "Unsupported linked destination: $dir" }
}
$stage = Join-Path $parent ('.workthread-install-' + [guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($stage) | Out-Null
try {
    if (!$PackagePath) {
        $PackagePath = Join-Path $stage "$name.zip"
        Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/MelonTse/workthread/releases/download/v$version/$name.zip" -OutFile $PackagePath
    }
    $hasher = [Security.Cryptography.SHA256]::Create()
    $stream = [IO.File]::OpenRead($PackagePath)
    try { $actual = [BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-','') }
    finally { $stream.Dispose(); $hasher.Dispose() }
    if ($actual -ne $ExpectedSha256) { throw 'Program ZIP SHA-256 mismatch.' }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($PackagePath)
    try { $bytes = ($zip.Entries | Measure-Object -Property Length -Sum).Sum }
    finally { $zip.Dispose() }
    if ($drive.AvailableFreeSpace -lt ($bytes + 256MB)) { throw 'Insufficient free space for first installation.' }
    [IO.Compression.ZipFile]::ExtractToDirectory($PackagePath, $stage)
    $package = Join-Path $stage $name
    $info = Get-Content -LiteralPath (Join-Path $package 'BUILD_INFO.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($info.version -ne $version -or $info.machine -notin @('AMD64','x86_64') -or $info.runner_os -ne 'Windows' -or $info.commit_sha -notmatch '^[0-9a-f]{40}$') { throw 'Unexpected package identity.' }
    $trust = Join-Path $package 'app\_internal\workthread\updating\release-public.hex'
    if (!(Test-Path -LiteralPath $trust) -or (Get-Content -Raw -LiteralPath $trust).Trim() -notmatch '^[0-9a-fA-F]{64}$') { throw 'Package lacks an update verification key.' }
    if ([IO.Directory]::Exists($root)) { [IO.Directory]::Delete($root, $false) } # Empty only; fails if files appeared.
    [IO.Directory]::Move($package, $root)
    & (Join-Path $root 'Install.cmd') /quiet
    if ($LASTEXITCODE -ne 0) { throw "Initialization failed at $root (exit $LASTEXITCODE)." }
    [pscustomobject]@{ version=$version; commit=$info.commit_sha; installRoot=$root; acceptanceProject=(Join-Path $root 'acceptance\agent-workspace'); formalProject=(Join-Path $root 'workspace\agent-workspace') } | ConvertTo-Json -Compress
} finally {
    Remove-Item -LiteralPath $stage -Recurse -Force
}
