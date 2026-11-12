<#
.SYNOPSIS
  End-to-end check of installer.nsi's install, update, rollback and recovery logic.

.DESCRIPTION
  Default mode builds two installers (1.0.0 and 2.0.0) from tiny fake application folders with the
  test-only define TEST_USER_LEVEL (RequestExecutionLevel user, registry under HKCU with a test key
  name, shortcut beside the test folder), so no UAC prompt appears and nothing outside the work folder
  and that one HKCU key is touched. The real dist is never needed.

  With -Installer, the given (real) installer is used as both the old and the new version instead; CI
  runs it against the release build. That installer is admin level and registers itself normally.

  Everything happens under -WorkDir (a new temp folder by default). Exit code 0 = all scenarios passed.
  Windows PowerShell 5.1 and PowerShell 7 compatible.
#>
param(
    [string]$MakeNsis = '',
    [string]$Installer = '',
    [string]$WorkDir = '',
    [int]$TimeoutSeconds = 300,
    [switch]$Keep
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$testKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\AkisKurguAI-InstallerTest'
if (-not $WorkDir) {
    $base = $env:RUNNER_TEMP
    if (-not $base) { $base = $env:TEMP }
    $WorkDir = Join-Path $base ('akis-installer-test-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
}
New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null
$WorkDir = (Resolve-Path -LiteralPath $WorkDir).Path
$results = New-Object System.Collections.Generic.List[string]
$failures = 0

function Write-Bytes([string]$path, [byte[]]$bytes) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $path) | Out-Null
    [IO.File]::WriteAllBytes($path, $bytes)
}
function Write-Text([string]$path, [string]$text) { Write-Bytes $path ([Text.Encoding]::UTF8.GetBytes($text)) }

function New-FakeDist([string]$folder, [string]$version, [string[]]$extra) {
    # A real, harmless program as the exe (ping.exe) so the "app is running" scenario can start it; the
    # version is appended as overlay bytes, which keeps it runnable and makes each version's hash distinct.
    $ping = [IO.File]::ReadAllBytes((Join-Path $env:WINDIR 'System32\PING.EXE'))
    $tag = [Text.Encoding]::ASCII.GetBytes("akis-fake-$version")
    Write-Bytes (Join-Path $folder 'AkisKurguAI.exe') ($ping + $tag)
    Write-Bytes (Join-Path $folder '_internal\ffmpeg.exe') ($ping + $tag)
    Write-Text (Join-Path $folder '_internal\core.dll') "core $version"
    Write-Text (Join-Path $folder '_internal\sub\data.txt') "data $version"
    foreach ($name in $extra) { Write-Text (Join-Path $folder "_internal\$name") "$name $version" }
}

function Build-Installer([string]$version, [string]$dist, [string]$output) {
    $list = Join-Path $WorkDir "uninstall-$version.nsh"
    & python (Join-Path $repo 'scripts\generate-nsis-uninstall.py') $dist $list
    if ($LASTEXITCODE -ne 0) { throw "generate-nsis-uninstall.py failed for $version" }
    $arguments = @('/V2', "/DPRODUCT_VERSION=$version", "/DSOURCE_DIR=$dist", "/DOUTPUT_FILE=$output",
                   "/DUNINSTALL_LIST=$list", '/DTEST_USER_LEVEL', '/DPRODUCT_NAME=Akis Kurgu AI Installer Test',
                   '/DUNINSTALL_KEY_NAME=AkisKurguAI-InstallerTest', (Join-Path $repo 'installer.nsi'))
    & $MakeNsis @arguments
    if ($LASTEXITCODE -ne 0) { throw "makensis failed for $version ($LASTEXITCODE)" }
}

function Invoke-Setup([string]$exe, [string[]]$arguments) {
    $p = Start-Process -FilePath $exe -ArgumentList $arguments -PassThru
    $null = $p.Handle  # keeps the handle so ExitCode is available afterwards
    if (-not $p.WaitForExit(1000 * $TimeoutSeconds)) {
        Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
        throw "$([IO.Path]::GetFileName($exe)) $($arguments -join ' ') did not finish in $TimeoutSeconds s (waiting for a click?)"
    }
    return $p.ExitCode
}

function Get-Snapshot([string]$folder) {
    $lines = Get-ChildItem -LiteralPath $folder -Recurse -Force | Sort-Object FullName | ForEach-Object {
        $relative = $_.FullName.Substring($folder.Length)
        if ($_.PSIsContainer) { "D $relative" } else { "F $relative $((Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash)" }
    }
    return ($lines -join "`n")
}

function Assert([bool]$condition, [string]$message) { if (-not $condition) { throw $message } }
function Assert-Clean([string]$folder) {
    foreach ($name in 'AkisKurguAI.exe.old', '_internal.old', 'AkisKurguAI.exe.new') {
        Assert (-not (Test-Path -LiteralPath (Join-Path $folder $name))) "$name left behind"
    }
}
function Assert-Version([string]$folder, [string]$dist) {
    Assert ((Get-FileHash -LiteralPath (Join-Path $folder 'AkisKurguAI.exe')).Hash -eq (Get-FileHash -LiteralPath (Join-Path $dist 'AkisKurguAI.exe')).Hash) "exe is not the expected version"
    Get-ChildItem -LiteralPath (Join-Path $dist '_internal') -Recurse -File | ForEach-Object {
        $installed = Join-Path $folder ('_internal' + $_.FullName.Substring((Join-Path $dist '_internal').Length))
        Assert (Test-Path -LiteralPath $installed) "missing $installed"
        Assert ((Get-FileHash -LiteralPath $installed).Hash -eq (Get-FileHash -LiteralPath $_.FullName).Hash) "wrong content: $installed"
    }
}
function Assert-Log([string]$log, [string]$pattern) {
    Assert (Test-Path -LiteralPath $log) "log $log missing"
    Assert ((Get-Content -Raw -LiteralPath $log) -match $pattern) "log does not match '$pattern': $(Get-Content -Raw -LiteralPath $log)"
}

function Scenario([string]$name, [scriptblock]$body) {
    try {
        & $body
        $results.Add("PASS  $name")
        Write-Host "PASS  $name"
    } catch {
        $script:failures++
        $results.Add("FAIL  $name : $($_.Exception.Message)")
        Write-Host "FAIL  $name : $($_.Exception.Message)" -ForegroundColor Red
    }
}

function Install-Fresh([string]$setup, [string]$folder) {
    $code = Invoke-Setup $setup @('/S', "/D=$folder")
    Assert ($code -eq 0) "fresh install exit code $code"
    Assert (Test-Path -LiteralPath (Join-Path $folder 'AkisKurguAI.exe')) 'exe missing after fresh install'
}

try {
    if (-not $MakeNsis) {
        $candidate = Join-Path ${env:ProgramFiles(x86)} 'NSIS\makensis.exe'
        if (Test-Path -LiteralPath $candidate) { $MakeNsis = $candidate }
        else {
            $found = Get-Command makensis.exe -ErrorAction SilentlyContinue
            if ($found) { $MakeNsis = $found.Source }
        }
    }
    if ($Installer) {
        $Installer = (Resolve-Path -LiteralPath $Installer).Path
        $old = $Installer; $new = $Installer; $newDist = $null
    } else {
        if (-not $MakeNsis -or -not (Test-Path -LiteralPath $MakeNsis)) { throw 'makensis.exe not found; pass -MakeNsis or -Installer' }
        $oldDist = Join-Path $WorkDir 'dist-1.0.0\AkisKurguAI'
        $newDist = Join-Path $WorkDir 'dist-2.0.0\AkisKurguAI'
        New-FakeDist $oldDist '1.0.0' @('old-only.dll', 'sub\old-only.txt')
        New-FakeDist $newDist '2.0.0' @('new-only.dll')
        $old = Join-Path $WorkDir 'Setup-1.0.0.exe'
        $new = Join-Path $WorkDir 'Setup-2.0.0.exe'
        Build-Installer '1.0.0' $oldDist $old
        Build-Installer '2.0.0' $newDist $new
    }

    Scenario 'fresh install (/S /D=)' {
        $folder = Join-Path $WorkDir 'fresh\App'
        Install-Fresh $old $folder
        if ($newDist) { Assert-Version $folder $oldDist; Assert (Test-Path (Join-Path $folder '_internal\old-only.dll')) 'old-only.dll missing' }
        Assert (Test-Path (Join-Path $folder 'Uninstall-Akis.exe')) 'uninstaller missing'
        Assert-Clean $folder
    }

    Scenario 'update over existing install (/UPDATE, visible, unattended)' {
        $folder = Join-Path $WorkDir 'update\App'
        Install-Fresh $old $folder
        Write-Text (Join-Path $folder '_internal\stale-module.pyd') 'only in an older version'
        $log = Join-Path $WorkDir 'update\install.log'
        $code = Invoke-Setup $new @('/UPDATE', "/DIR=`"$folder`"", "/LOG=`"$log`"")
        Assert ($code -eq 0) "update exit code $code"
        Assert (-not (Test-Path (Join-Path $folder '_internal\stale-module.pyd'))) 'stale file survived the update'
        if ($newDist) {
            Assert-Version $folder $newDist
            Assert (-not (Test-Path (Join-Path $folder '_internal\old-only.dll'))) 'old-only.dll survived the update'
        }
        Assert-Clean $folder
        Assert-Log $log 'NSIS installation completed\.'
    }

    Scenario 'update with legacy helper flags (/VERYSILENT /NORESTART /SP- /DIR= /LOG=)' {
        $folder = Join-Path $WorkDir 'legacy\App'
        Install-Fresh $old $folder
        $log = Join-Path $WorkDir 'legacy\install.log'
        $code = Invoke-Setup $new @('/VERYSILENT', '/NORESTART', '/SP-', "/DIR=`"$folder`"", "/LOG=`"$log`"")
        Assert ($code -eq 0) "legacy update exit code $code"
        if ($newDist) { Assert-Version $folder $newDist }
        Assert-Clean $folder
        Assert-Log $log 'NSIS installation completed\.'
    }

    Scenario 'update while a file in _internal is held open (must fail, old install unchanged)' {
        $folder = Join-Path $WorkDir 'locked\App'
        Install-Fresh $old $folder
        $before = Get-Snapshot $folder
        $log = Join-Path $WorkDir 'locked\install.log'
        $handle = [IO.File]::Open((Join-Path $folder '_internal\sub\data.txt'), 'Open', 'Read', 'Read')
        try {
            $code = Invoke-Setup $new @('/UPDATE', "/DIR=`"$folder`"", "/LOG=`"$log`"")
        } finally { $handle.Dispose() }
        Assert ($code -eq 10) "expected exit code 10, got $code"
        Assert ((Get-Snapshot $folder) -eq $before) 'install folder changed'
        Assert-Clean $folder
        Assert-Log $log 'failed \(code 10\)'
    }

    if ($newDist) {
        Scenario 'update while the app exe is running (must fail, old install unchanged)' {
            $folder = Join-Path $WorkDir 'running\App'
            Install-Fresh $old $folder
            $before = Get-Snapshot $folder
            $app = Start-Process -FilePath (Join-Path $folder 'AkisKurguAI.exe') -ArgumentList @('-n', '120', '127.0.0.1') -WindowStyle Hidden -PassThru
            try {
                Start-Sleep -Milliseconds 500
                Assert (-not $app.HasExited) 'fake app did not start'
                $code = Invoke-Setup $new @('/UPDATE', "/DIR=`"$folder`"")
            } finally { Stop-Process -Id $app.Id -Force -ErrorAction SilentlyContinue; $app.WaitForExit(10000) | Out-Null }
            Assert ($code -eq 10) "expected exit code 10, got $code"
            Assert ((Get-Snapshot $folder) -eq $before) 'install folder changed'
        }

        Scenario 'update while an orphaned ffmpeg.exe runs from _internal (must fail, unchanged)' {
            $folder = Join-Path $WorkDir 'ffmpeg\App'
            Install-Fresh $old $folder
            $before = Get-Snapshot $folder
            $ffmpeg = Start-Process -FilePath (Join-Path $folder '_internal\ffmpeg.exe') -ArgumentList @('-n', '120', '127.0.0.1') -WindowStyle Hidden -PassThru
            try {
                Start-Sleep -Milliseconds 500
                $code = Invoke-Setup $new @('/S', "/D=$folder")
            } finally { Stop-Process -Id $ffmpeg.Id -Force -ErrorAction SilentlyContinue; $ffmpeg.WaitForExit(10000) | Out-Null }
            Assert ($code -eq 10) "expected exit code 10, got $code"
            Assert ((Get-Snapshot $folder) -eq $before) 'install folder changed'
        }
    }

    Scenario 'recovery from an interrupted update (.old present, exe missing)' {
        $folder = Join-Path $WorkDir 'recover\App'
        Install-Fresh $old $folder
        Write-Text (Join-Path $folder '_internal\stale-module.pyd') 'only in the old copy'
        Rename-Item -LiteralPath (Join-Path $folder 'AkisKurguAI.exe') 'AkisKurguAI.exe.old'
        Rename-Item -LiteralPath (Join-Path $folder '_internal') '_internal.old'
        Write-Text (Join-Path $folder '_internal\partial.bin') 'half-written new file'
        Write-Text (Join-Path $folder 'AkisKurguAI.exe.new') 'half-written new exe'
        $log = Join-Path $WorkDir 'recover\install.log'
        $code = Invoke-Setup $new @('/UPDATE', "/DIR=`"$folder`"", "/LOG=`"$log`"")
        Assert ($code -eq 0) "exit code $code"
        Assert (-not (Test-Path (Join-Path $folder '_internal\partial.bin'))) 'partial file survived'
        Assert (-not (Test-Path (Join-Path $folder '_internal\stale-module.pyd'))) 'restored old copy was not replaced'
        if ($newDist) { Assert-Version $folder $newDist }
        Assert-Clean $folder
        Assert-Log $log 'NSIS installation completed\.'
    }

    Scenario 'recovery that cannot complete exits 14 and destroys nothing' {
        # Interrupted swap whose .old folder is still in use: the restore cannot happen, so the installer
        # must stop with 14 before extracting anything, leaving the .old copies intact for a later run.
        $folder = Join-Path $WorkDir 'recover-blocked\App'
        Install-Fresh $old $folder
        Rename-Item -LiteralPath (Join-Path $folder 'AkisKurguAI.exe') 'AkisKurguAI.exe.old'
        Rename-Item -LiteralPath (Join-Path $folder '_internal') '_internal.old'
        $expected = Get-Snapshot $folder
        $handle = [IO.File]::Open((Join-Path $folder '_internal.old\sub\data.txt'), 'Open', 'Read', 'Read')
        try {
            $code = Invoke-Setup $new @('/UPDATE', "/DIR=`"$folder`"")
        } finally { $handle.Dispose() }
        Assert ($code -eq 14) "expected exit code 14, got $code"
        Assert (-not (Test-Path -LiteralPath (Join-Path $folder '_internal'))) 'new files were extracted'
        $after = Get-Snapshot $folder
        Assert ($after -eq $expected) 'the .old copies changed'
        # Once nothing holds it any more, the next run recovers and updates.
        $code = Invoke-Setup $new @('/S', "/D=$folder")
        Assert ($code -eq 0) "follow-up run exit code $code"
        if ($newDist) { Assert-Version $folder $newDist }
        Assert-Clean $folder
    }
    Scenario 'extraction failure rolls back to the old copy (exit 11)' {
        # A directory squatting on the temporary exe name makes writing the new exe fail after the old
        # copy was moved aside and the new _internal extracted: everything must be put back.
        $folder = Join-Path $WorkDir 'extract-fail\App'
        Install-Fresh $old $folder
        New-Item -ItemType Directory -Path (Join-Path $folder 'AkisKurguAI.exe.new') | Out-Null
        $before = Get-Snapshot $folder
        $log = Join-Path $WorkDir 'extract-fail\install.log'
        $code = Invoke-Setup $new @('/UPDATE', "/DIR=`"$folder`"", "/LOG=`"$log`"")
        Assert ($code -eq 11) "expected exit code 11, got $code"
        Assert ((Get-Snapshot $folder) -eq $before) 'old copy not restored exactly'
        Assert (-not (Test-Path (Join-Path $folder '_internal.old'))) '_internal.old left behind'
        Assert-Log $log 'failed \(code 11\)'
    }

    if ($newDist) {
        Scenario 'failure after extraction (shortcut) rolls back to the old copy (exit 13)' {
            # The test build puts its shortcut folder beside the install folder; a file in its place
            # makes CreateShortcut fail after all files are in place.
            $folder = Join-Path $WorkDir 'finish-fail\App'
            Install-Fresh $old $folder
            $shortcuts = Join-Path $WorkDir 'finish-fail\StartMenu'
            Remove-Item -LiteralPath $shortcuts -Recurse -Force
            Write-Text $shortcuts 'not a folder'
            $before = (Get-Snapshot $folder) -split "`n" | Where-Object { $_ -notmatch 'Uninstall-Akis\.exe' }
            $code = Invoke-Setup $new @('/UPDATE', "/DIR=`"$folder`"")
            Assert ($code -eq 13) "expected exit code 13, got $code"
            $after = (Get-Snapshot $folder) -split "`n" | Where-Object { $_ -notmatch 'Uninstall-Akis\.exe' }
            Assert (($after -join "`n") -eq ($before -join "`n")) 'old copy not restored exactly'
            Assert-Clean $folder
        }
    }

    Scenario 'leftover .old copies after a committed update are removed' {
        $folder = Join-Path $WorkDir 'leftover\App'
        Install-Fresh $old $folder
        Write-Text (Join-Path $folder '_internal.old\x.dll') 'leftover'
        Write-Text (Join-Path $folder 'AkisKurguAI.exe.old') 'leftover'
        $code = Invoke-Setup $new @('/S', "/D=$folder")
        Assert ($code -eq 0) "exit code $code"
        Assert-Clean $folder
    }

    Scenario 'uninstall keeps user files and removes leftover .old copies' {
        $folder = Join-Path $WorkDir 'uninstall\App'
        Install-Fresh $new $folder
        Write-Text (Join-Path $folder 'user-project.keep') 'preserve'
        Write-Text (Join-Path $folder '_internal.old\x.dll') 'leftover'
        $code = Invoke-Setup (Join-Path $folder 'Uninstall-Akis.exe') @('/S', "_?=$folder")
        Assert ($code -eq 0) "uninstall exit code $code"
        Assert (-not (Test-Path (Join-Path $folder 'AkisKurguAI.exe'))) 'exe not removed'
        Assert (-not (Test-Path (Join-Path $folder '_internal'))) '_internal not removed'
        Assert (Test-Path (Join-Path $folder 'user-project.keep')) 'user file deleted'
        Assert-Clean $folder
        if ($newDist) { Assert (-not (Test-Path -LiteralPath $testKey)) 'test uninstall key still present' }
    }
} catch {
    $failures++
    $results.Add("ERROR $($_.Exception.Message)")
    Write-Host "ERROR $($_.Exception.Message)" -ForegroundColor Red
} finally {
    if (-not $Installer) { Remove-Item -LiteralPath $testKey -Recurse -Force -ErrorAction SilentlyContinue }
    if (-not $Keep) { Remove-Item -LiteralPath $WorkDir -Recurse -Force -ErrorAction SilentlyContinue }
}
Write-Host ''
$results | ForEach-Object { Write-Host $_ }
if ($failures) { Write-Host "$failures scenario(s) failed" -ForegroundColor Red; exit 1 }
Write-Host 'All installer scenarios passed.'
exit 0
