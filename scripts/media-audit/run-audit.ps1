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
    if ($LocalSpeech) {
        & $Python -X utf8 -B "$PSScriptRoot/speech_project.py" $repo | Out-File "$outDir/speech_project-final.json" -Encoding utf8
        if ($LASTEXITCODE) { $failed += 'Local speech project' }
    }
    if (-not $Headless) {
        $env:QT_QPA_PLATFORM = 'windows'
        $env:AKIS_RUN_WINDOWS_GUI_SMOKE = '1'
        & $Python -X utf8 -B -m unittest tests.test_shorts_windows_smoke -v
        if ($LASTEXITCODE) { $failed += 'Windows GUI' }
    }
    if ($failed) { throw ("Failed audit groups: " + ($failed -join ', ')) }
} finally {
    foreach ($name in $variables) { [Environment]::SetEnvironmentVariable($name, $previous[$name]) }
    Pop-Location
}
