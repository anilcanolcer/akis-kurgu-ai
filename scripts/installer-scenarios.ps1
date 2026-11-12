<#
.SYNOPSIS
  End-to-end check of installer.nsi's install, update, wait, relaunch, rollback and recovery logic.

.DESCRIPTION
  Default mode builds two installers (1.0.0 and 2.0.0) from tiny fake application folders with the
  test-only define TEST_USER_LEVEL (RequestExecutionLevel user, registry under HKCU with a test key
  name, shortcut beside the test folder), so no UAC prompt appears and nothing outside the work folder
  and that one HKCU key is touched. The real dist is never needed. The fake AkisKurguAI.exe is a copy of
  cmd.exe: started without arguments (as the installer's relaunch does) it stays open, so the relaunch can
  be observed; started with "/c ping -n N 127.0.0.1" it plays an app that takes N-1 seconds to exit.

  With -Installer, the given (real) installer is used as both the old and the new version and only the
  scenarios that do not start the app run; CI uses this against the release build.

  Failure scenarios pass /S with /UPDATE so the installer's failure message box is answered by /SD and
  nothing waits for a click. Everything happens under -WorkDir (a new temp folder by default); processes
  started from it are stopped after each scenario. Exit code 0 = all scenarios passed.
  Windows PowerShell 5.1 and PowerShell 7 compatible.
#>
param(
    [string]$MakeNsis = '',
    [string]$Installer = '',
    [string]$WorkDir = '',
    [int]$TimeoutSeconds = 300,
    [string]$Repo = '',
    [switch]$Keep
)
$ErrorActionPreference = 'Stop'
$repo = $Repo
if (-not $repo) { $repo = Split-Path -Parent $PSScriptRoot }
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
    # The version is appended as overlay bytes: still runnable, and each version's hash is distinct.
    $cmd = [IO.File]::ReadAllBytes((Join-Path $env:WINDIR 'System32\cmd.exe'))
    $tag = [Text.Encoding]::ASCII.GetBytes("akis-fake-$version")
    Write-Bytes (Join-Path $folder 'AkisKurguAI.exe') ($cmd + $tag)
    Write-Bytes (Join-Path $folder '_internal\ffmpeg.exe') ($cmd + $tag)
    Write-Text (Join-Path $folder '_internal\core.dll') "core $version"
    Write-Text (Join-Path $folder '_internal\sub\data.txt') "data $version"
    foreach ($name in $extra) { Write-Text (Join-Path $folder "_internal\$name") "$name $version" }
}

function Build-Installer([string]$version, [string]$dist, [string]$output) {
    $list = Join-Path $WorkDir "uninstall-$version.nsh"
    $python = Join-Path $repo '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python)) { $python = 'python' }
    & $python (Join-Path $repo 'scripts\generate-nsis-uninstall.py') $dist $list
    if ($LASTEXITCODE -ne 0) { throw "generate-nsis-uninstall.py failed for $version" }
    $arguments = @('/V2', "/DPRODUCT_VERSION=$version", "/DSOURCE_DIR=$dist", "/DOUTPUT_FILE=$output",
                   "/DUNINSTALL_LIST=$list", '/DTEST_USER_LEVEL', '/DPRODUCT_NAME=Akis Kurgu AI Installer Test',
                   '/DUNINSTALL_KEY_NAME=AkisKurguAI-InstallerTest', (Join-Path $repo 'installer.nsi'))
    & $MakeNsis @arguments
    if ($LASTEXITCODE -ne 0) { throw "makensis failed for $version ($LASTEXITCODE)" }
}

function Invoke-Setup([string]$exe, [string[]]$arguments) {
    $p = Start-Process -FilePath $exe -ArgumentList $arguments -PassThru
    $null = $p.Handle
    if (-not $p.WaitForExit(1000 * $TimeoutSeconds)) {
        Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
        throw "$([IO.Path]::GetFileName($exe)) $($arguments -join ' ') did not finish in $TimeoutSeconds s (waiting for a click?)"
    }
    return $p.ExitCode
}

function Get-Running([string]$exe) {
    @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
        $path = $null
        try { $path = $_.Path } catch { }
        $path -and $path.Equals($exe, [StringComparison]::OrdinalIgnoreCase)
    })
}
function Wait-Started([string]$exe, [int]$seconds = 15) {
    $deadline = (Get-Date).AddSeconds($seconds)
    while ((Get-Date) -lt $deadline) {
        if ((Get-Running $exe).Count -gt 0) { return $true }
        Start-Sleep -Milliseconds 250
    }
    return $false
}
function Stop-WorkProcesses {
    Get-Process -ErrorAction SilentlyContinue | Where-Object {
        $path = $null
        try { $path = $_.Path } catch { }
        $path -and $path.StartsWith($WorkDir + '\', [StringComparison]::OrdinalIgnoreCase)
    } | ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue; $_.WaitForExit(10000) | Out-Null }
}
function Start-FakeApp([string]$exe, [int]$seconds) {
    $p = Start-Process -FilePath $exe -ArgumentList @('/c', 'ping', '-n', "$($seconds + 1)", '127.0.0.1') -WindowStyle Hidden -PassThru
    Start-Sleep -Milliseconds 500
    Assert (-not $p.HasExited) "fake process $exe did not start"
    return $p
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
    } finally {
        Stop-WorkProcesses
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
    $fake = [bool]$newDist

    Scenario 'fresh install (/S /D=)' {
        $folder = Join-Path $WorkDir 'fresh\App'
        Install-Fresh $old $folder
        if ($fake) { Assert-Version $folder $oldDist; Assert (Test-Path (Join-Path $folder '_internal\old-only.dll')) 'old-only.dll missing' }
        Assert (Test-Path (Join-Path $folder 'Uninstall-Akis.exe')) 'uninstaller missing'
        Assert-Clean $folder
        if ($fake) {
            $entry = Get-ItemProperty -LiteralPath $testKey
            Assert ($entry.InstallLocation -eq $folder) "InstallLocation is '$($entry.InstallLocation)'"
            Assert ($entry.DisplayIcon -eq (Join-Path $folder 'AkisKurguAI.exe')) "DisplayIcon is '$($entry.DisplayIcon)'"
            Assert ($entry.Publisher -and $entry.URLInfoAbout) 'Publisher or URLInfoAbout missing'
            Assert ($entry.EstimatedSize -gt 0) "EstimatedSize is '$($entry.EstimatedSize)'"
        }
    }

    Scenario 'update over existing install (/UPDATE, visible, unattended, app relaunched)' {
        $folder = Join-Path $WorkDir 'update\App'
        Install-Fresh $old $folder
        Write-Text (Join-Path $folder '_internal\stale-module.pyd') 'only in an older version'
        $log = Join-Path $WorkDir 'update\install.log'
        $arguments = @('/UPDATE', "/DIR=`"$folder`"", "/LOG=`"$log`"")
        if (-not $fake) { $arguments = @('/S') + $arguments }
        $code = Invoke-Setup $new $arguments
        Assert ($code -eq 0) "update exit code $code"
        Assert (-not (Test-Path (Join-Path $folder '_internal\stale-module.pyd'))) 'stale file survived the update'
        if ($fake) {
            Assert-Version $folder $newDist
            Assert (-not (Test-Path (Join-Path $folder '_internal\old-only.dll'))) 'old-only.dll survived the update'
            Assert (Wait-Started (Join-Path $folder 'AkisKurguAI.exe')) 'the updated app was not started'
        }
        Assert-Clean $folder
        Assert-Log $log 'NSIS installation completed\.'
    }

    Scenario 'update with legacy helper flags (/VERYSILENT /NORESTART /SP- /DIR= /LOG=), no relaunch' {
        $folder = Join-Path $WorkDir 'legacy\App'
        Install-Fresh $old $folder
        $log = Join-Path $WorkDir 'legacy\install.log'
        $code = Invoke-Setup $new @('/VERYSILENT', '/NORESTART', '/SP-', "/DIR=`"$folder`"", "/LOG=`"$log`"")
        Assert ($code -eq 0) "legacy update exit code $code"
        if ($fake) {
            Assert-Version $folder $newDist
            Assert (-not (Wait-Started (Join-Path $folder 'AkisKurguAI.exe') 3)) 'legacy mode started the app (the old helper does that)'
        }
        Assert-Clean $folder
        Assert-Log $log 'NSIS installation completed\.'
    }

    Scenario 'update while a file in _internal is held open (/WAIT=2: exit 10, unchanged)' {
        $folder = Join-Path $WorkDir 'locked\App'
        Install-Fresh $old $folder
        $before = Get-Snapshot $folder
        $log = Join-Path $WorkDir 'locked\install.log'
        $arguments = @('/UPDATE', '/S', '/WAIT=2', "/DIR=`"$folder`"", "/LOG=`"$log`"")
        $handle = [IO.File]::Open((Join-Path $folder '_internal\sub\data.txt'), 'Open', 'Read', 'Read')
        try {
            $code = Invoke-Setup $new $arguments
        } finally { $handle.Dispose() }
        Assert ($code -eq 10) "expected exit code 10, got $code"
        Assert ((Get-Snapshot $folder) -eq $before) 'install folder changed'
        Assert-Clean $folder
        Assert-Log $log 'failed \(code 10\)'
        if ($fake) { Assert (Wait-Started (Join-Path $folder 'AkisKurguAI.exe')) 'the previous version was not started again' }
    }

    if ($fake) {
        Scenario 'update waits for a slowly exiting app, then installs and relaunches' {
            $folder = Join-Path $WorkDir 'wait\App'
            Install-Fresh $old $folder
            $exe = Join-Path $folder 'AkisKurguAI.exe'
            $app = Start-FakeApp $exe 4
            $started = Get-Date
            $code = Invoke-Setup $new @('/UPDATE', '/S', '/WAIT=30', "/DIR=`"$folder`"")
            Assert ($code -eq 0) "exit code $code"
            Assert ($app.HasExited) 'installer finished while the app still ran'
            Assert (((Get-Date) - $started).TotalSeconds -ge 2) 'installer did not wait'
            Assert-Version $folder $newDist
            Assert-Clean $folder
            Assert (Wait-Started $exe) 'the updated app was not started'
        }

        Scenario 'app never exits (/WAIT=3): exit 10 after the wait, unchanged, not started twice' {
            $folder = Join-Path $WorkDir 'running\App'
            Install-Fresh $old $folder
            $before = Get-Snapshot $folder
            $exe = Join-Path $folder 'AkisKurguAI.exe'
            $app = Start-FakeApp $exe 120
            $started = Get-Date
            $code = Invoke-Setup $new @('/UPDATE', '/S', '/WAIT=3', "/DIR=`"$folder`"")
            Assert ($code -eq 10) "expected exit code 10, got $code"
            Assert (((Get-Date) - $started).TotalSeconds -ge 3) 'installer did not wait'
            Assert ((Get-Snapshot $folder) -eq $before) 'install folder changed'
            Start-Sleep -Seconds 2
            Assert ((Get-Running $exe).Count -eq 1) 'a second instance was started'
        }

        Scenario 'orphaned ffmpeg.exe running from _internal, /S: exit 10 at once, unchanged' {
            $folder = Join-Path $WorkDir 'ffmpeg\App'
            Install-Fresh $old $folder
            $before = Get-Snapshot $folder
            $null = Start-FakeApp (Join-Path $folder '_internal\ffmpeg.exe') 120
            $code = Invoke-Setup $new @('/S', "/D=$folder")
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
        $code = Invoke-Setup $new @('/UPDATE', '/S', "/DIR=`"$folder`"", "/LOG=`"$log`"")
        Assert ($code -eq 0) "exit code $code"
        Assert (-not (Test-Path (Join-Path $folder '_internal\partial.bin'))) 'partial file survived'
        Assert (-not (Test-Path (Join-Path $folder '_internal\stale-module.pyd'))) 'restored old copy was not replaced'
        if ($fake) { Assert-Version $folder $newDist }
        Assert-Clean $folder
        Assert-Log $log 'NSIS installation completed\.'
    }

    Scenario 'recovery that cannot complete exits 14 and destroys nothing' {
        $folder = Join-Path $WorkDir 'recover-blocked\App'
        Install-Fresh $old $folder
        Rename-Item -LiteralPath (Join-Path $folder 'AkisKurguAI.exe') 'AkisKurguAI.exe.old'
        Rename-Item -LiteralPath (Join-Path $folder '_internal') '_internal.old'
        $expected = Get-Snapshot $folder
        $handle = [IO.File]::Open((Join-Path $folder '_internal.old\sub\data.txt'), 'Open', 'Read', 'Read')
        try {
            $code = Invoke-Setup $new @('/UPDATE', '/S', "/DIR=`"$folder`"")
        } finally { $handle.Dispose() }
        Assert ($code -eq 14) "expected exit code 14, got $code"
        Assert (-not (Test-Path -LiteralPath (Join-Path $folder '_internal'))) 'new files were extracted'
        Assert ((Get-Snapshot $folder) -eq $expected) 'the .old copies changed'
        $code = Invoke-Setup $new @('/S', "/D=$folder")
        Assert ($code -eq 0) "follow-up run exit code $code"
        if ($fake) { Assert-Version $folder $newDist }
        Assert-Clean $folder
    }

    Scenario 'extraction failure rolls back to the old copy (exit 11)' {
        $folder = Join-Path $WorkDir 'extract-fail\App'
        Install-Fresh $old $folder
        New-Item -ItemType Directory -Path (Join-Path $folder 'AkisKurguAI.exe.new') | Out-Null
        $before = Get-Snapshot $folder
        $log = Join-Path $WorkDir 'extract-fail\install.log'
        $code = Invoke-Setup $new @('/UPDATE', '/S', "/DIR=`"$folder`"", "/LOG=`"$log`"")
        Assert ($code -eq 11) "expected exit code 11, got $code"
        Assert ((Get-Snapshot $folder) -eq $before) 'old copy not restored exactly'
        Assert (-not (Test-Path (Join-Path $folder '_internal.old'))) '_internal.old left behind'
        Assert-Log $log 'failed \(code 11\)'
        if ($fake) { Assert (Wait-Started (Join-Path $folder 'AkisKurguAI.exe')) 'the restored version was not started again' }
    }

    if ($fake) {
        Scenario 'failure after extraction (shortcut) rolls back to the old copy (exit 13)' {
            $folder = Join-Path $WorkDir 'finish-fail\App'
            Install-Fresh $old $folder
            $shortcuts = Join-Path $WorkDir 'finish-fail\StartMenu'
            Remove-Item -LiteralPath $shortcuts -Recurse -Force
            Write-Text $shortcuts 'not a folder'
            $before = (Get-Snapshot $folder) -split "`n" | Where-Object { $_ -notmatch 'Uninstall-Akis\.exe' }
            $code = Invoke-Setup $new @('/UPDATE', '/S', "/DIR=`"$folder`"")
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
        if ($fake) { Assert (-not (Test-Path -LiteralPath $testKey)) 'test uninstall key still present' }
    }

    if ($fake) {
        Scenario 'uninstall while the app runs, /S: exit 10, nothing removed' {
            $folder = Join-Path $WorkDir 'uninstall-running\App'
            Install-Fresh $new $folder
            $before = Get-Snapshot $folder
            $null = Start-FakeApp (Join-Path $folder 'AkisKurguAI.exe') 120
            $code = Invoke-Setup (Join-Path $folder 'Uninstall-Akis.exe') @('/S', "_?=$folder")
            Assert ($code -eq 10) "expected exit code 10, got $code"
            Assert ((Get-Snapshot $folder) -eq $before) 'install folder changed'
            Assert (Test-Path -LiteralPath $testKey) 'uninstall key removed'
        }
    }
} catch {
    $failures++
    $results.Add("ERROR $($_.Exception.Message)")
    Write-Host "ERROR $($_.Exception.Message)" -ForegroundColor Red
} finally {
    Stop-WorkProcesses
    if (-not $Installer) { Remove-Item -LiteralPath $testKey -Recurse -Force -ErrorAction SilentlyContinue }
    if (-not $Keep) { Remove-Item -LiteralPath $WorkDir -Recurse -Force -ErrorAction SilentlyContinue }
}
Write-Host ''
$results | ForEach-Object { Write-Host $_ }
if ($failures) { Write-Host "$failures scenario(s) failed" -ForegroundColor Red; exit 1 }
Write-Host 'All installer scenarios passed.'
exit 0
