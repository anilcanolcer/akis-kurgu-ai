param([Parameter(Mandatory)][string]$Project)
$ErrorActionPreference = "Stop"
$repo = (Resolve-Path $Project).Path
$python = Join-Path $repo ".venv/Scripts/python.exe"
$outDir = Join-Path $env:TEMP ("akis-audit-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $outDir | Out-Null
Write-Host $outDir
Push-Location $repo
try {
    $env:QT_QPA_PLATFORM = "offscreen"
    $env:AKIS_REAL_SCREEN = "1"
    $env:PYTHONIOENCODING = "utf-8"
    & $python -B -m unittest discover -v
    if ($LASTEXITCODE) { throw "Test suite failed" }
    foreach ($name in "matrix","timing","deep","kurgu0610","multitrack0610") {
        & $python -X utf8 -B "$PSScriptRoot/$name.py" $repo | Out-File "$outDir/$name-final.json" -Encoding utf8
        if ($LASTEXITCODE) { throw "$name failed" }
    }
    & $python -B "$PSScriptRoot/verify.py" $outDir
    if ($LASTEXITCODE) { throw "Media verification failed" }
    $env:QT_QPA_PLATFORM = "windows"
    $env:AKIS_RUN_WINDOWS_GUI_SMOKE = "1"
    & $python -B -m unittest tests.test_shorts_windows_smoke -v
    if ($LASTEXITCODE) { throw "Windows GUI test failed" }
} finally {
    Pop-Location
}
