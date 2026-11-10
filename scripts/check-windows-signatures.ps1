param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string[]]$Path
)
$ErrorActionPreference = 'Stop'
$files = foreach ($itemPath in $Path) {
    $item = Get-Item -LiteralPath $itemPath
    if ($item.PSIsContainer) {
        Get-ChildItem -LiteralPath $item.FullName -File -Recurse | Where-Object { $_.Extension -in '.exe', '.dll', '.pyd' }
    } else {
        $item
    }
}
if (-not $files) { throw 'No executable files found.' }
$invalid = @()
foreach ($file in $files) {
    $signature = Get-AuthenticodeSignature -LiteralPath $file.FullName
    if ($signature.Status -ne 'Valid') {
        $invalid += [PSCustomObject]@{ File = $file.FullName; Status = $signature.Status }
    }
}
if ($invalid.Count) {
    $invalid | Format-Table -AutoSize | Out-String | Write-Host
    Write-Error "$($invalid.Count) file(s) do not have a valid, trusted Authenticode signature."
    exit 1
}
Write-Host "All $(@($files).Count) checked files have valid Authenticode signatures."
