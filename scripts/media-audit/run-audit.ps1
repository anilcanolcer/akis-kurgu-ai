param(
    [Parameter(Mandatory)][string]$Project,
    [string]$Python,
    [switch]$Headless,
    [switch]$LocalSpeech,
    [string]$ResultsRoot = $env:TEMP
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path -LiteralPath $Project).Path
if (-not $Python) { $Python = Join-Path $repo '.venv/Scripts/python.exe' }
$outDir = Join-Path $ResultsRoot ('akis-audit-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $outDir -Force | Out-Null
Write-Host "Audit results: $outDir"
$failed = @()
$variables = 'QT_QPA_PLATFORM', 'AKIS_REAL_SCREEN', 'AKIS_RUN_WINDOWS_GUI_SMOKE', 'PYTHONIOENCODING'
$previous = @{}
foreach ($name in $variables) { $previous[$name] = [Environment]::GetEnvironmentVariable($name) }
Push-Location $repo
try {
    $env:QT_QPA_PLATFORM = 'offscreen'
    $env:AKIS_REAL_SCREEN = if ($Headless) { '0' } else { '1' }
    $env:AKIS_RUN_WINDOWS_GUI_SMOKE = '0'
    $env:PYTHONIOENCODING = 'utf-8'
    & $Python -X utf8 -B -m unittest discover -v
    if ($LASTEXITCODE) { $failed += 'unittest' }

    foreach ($name in 'matrix', 'timing', 'deep', 'kurgu0610', 'multitrack0610', 'preview_export') {
        & $Python -X utf8 -B "$PSScriptRoot/$name.py" $repo | Out-File "$outDir/$name-final.json" -Encoding utf8
        if ($LASTEXITCODE) {
            $failed += $name
            continue
        }
        & $Python -X utf8 -B "$PSScriptRoot/verify.py" $outDir $name
        if ($LASTEXITCODE) { $failed += "$name verification" }
    }
    # Rule checkers on random input (scripts/media-audit): edit chains frame by frame against the model;
    # exports whose every frame and sound are read back; AI replies and transcripts; preview pieces and live
    # sound; editing sessions in the main window with undo and redo; stories (the guide on screen included),
    # templates and update versions; file names, overwrites, parallel downloads and update clean-up; the
    # recording window under random clicks.
    $checks = @(@('fuzz', '2000'), @('render_fuzz', '30'), @('audio_fuzz', '40'), @('ai_fuzz', '10000'),
                @('preview_fuzz', '1000'), @('window_fuzz', '100'), @('store_fuzz', '1500'),
                @('files_fuzz', '1200'), @('record_fuzz', '400'))
    foreach ($check in $checks) {
        & $Python -X utf8 -B "$PSScriptRoot/$($check[0]).py" $repo $check[1] | Out-File "$outDir/$($check[0])-final.json" -Encoding utf8
        if ($LASTEXITCODE) { $failed += $check[0] }
    }
    if ($LocalSpeech) {
        & $Python -X utf8 -B "$PSScriptRoot/speech_project.py" $repo | Out-File "$outDir/speech_project-final.json" -Encoding utf8
        if ($LASTEXITCODE) { $failed += 'Local speech project' }
    }
    if (-not $Headless) {
        $env:QT_QPA_PLATFORM = 'windows'
        $env:AKIS_RUN_WINDOWS_GUI_SMOKE = '1'
        & $Python -X utf8 -B -m unittest tests.test_shorts_windows_smoke tests.test_record.NativeRecordingTests -v
        if ($LASTEXITCODE) { $failed += 'Windows GUI' }
    }
    if ($failed) { throw ("Failed audit groups: " + ($failed -join ', ')) }
} finally {
    foreach ($name in $variables) { [Environment]::SetEnvironmentVariable($name, $previous[$name]) }
    Pop-Location
}
