param([switch]$Child)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$out = Join-Path $root 'artifacts\rc10-qa'
if ($Child) {
    $env:TEMP = Join-Path $out 'temporary'
    $env:TMP = $env:TEMP
    New-Item -ItemType Directory -Path $env:TEMP -Force | Out-Null
    $env:PYTHONPATH = Join-Path $root 'src'
    $env:PYTHONIOENCODING = 'utf-8'
    Set-Location $root
    & "$root\.venv\Scripts\python.exe" -X utf8 "$PSScriptRoot\qualify_rc10_windows.py" --output $out
    exit $LASTEXITCODE
}
# Only used on a disposable Actions runner; never included in the user tool.
New-Item -ItemType Directory -Path $out -Force | Out-Null
$name = 'WTRc10QA'
$password = ConvertTo-SecureString ('Q1!' + [guid]::NewGuid().ToString('N')) -AsPlainText -Force
$user = New-LocalUser -Name $name -Password $password -AccountNeverExpires
try {
    $users = Get-LocalGroup -SID 'S-1-5-32-545'
    Add-LocalGroupMember -Group $users -Member $user
    & icacls.exe $out /grant ('{0}:(OI)(CI)M' -f $name) | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Cannot prepare synthetic QA output directory' }
    $credentials = [pscredential]::new("$env:COMPUTERNAME\$name", $password)
    $p = Start-Process "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -Credential $credentials -LoadUserProfile -WorkingDirectory $root -ArgumentList ('-NoProfile -File "{0}" -Child' -f $PSCommandPath) -RedirectStandardOutput "$out\standard-user.stdout.txt" -RedirectStandardError "$out\standard-user.stderr.txt" -Wait -PassThru
    Get-Content "$out\standard-user.stdout.txt" -Encoding UTF8
    Get-Content "$out\standard-user.stderr.txt" -Encoding UTF8
    if ($p.ExitCode -ne 0) { throw "Standard-user qualification failed: $($p.ExitCode)" }
} finally {
    Remove-LocalUser -Name $name
}
