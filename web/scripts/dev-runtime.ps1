# Print which Pixfabrica API / plugin code is on disk vs what port 8000 is serving.
# Usage: powershell -ExecutionPolicy Bypass -File web/scripts/dev-runtime.ps1

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $root

$apiPort = if ($env:PIXFABRICA_API_PORT) { [int]$env:PIXFABRICA_API_PORT } else { 8000 }

Write-Host "=== Workspace plugin (disk) ==="
uv run python -c @"
import pixfabrica_std.background.sun_gl as m
print('sun_gl path:', m.__file__)
print('SHADER_REVISION:', m._SHADER_REVISION)
"@

Write-Host ""
Write-Host "=== Port $apiPort listener ==="
$pids = @(Get-NetTCPConnection -LocalPort $apiPort -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique)
if (-not $pids.Count) {
    Write-Host "(nothing listening)"
} else {
    foreach ($procId in $pids) {
        try {
            $wmi = Get-CimInstance Win32_Process -Filter "ProcessId=$procId"
            Write-Host "PID $procId"
            Write-Host "  $($wmi.CommandLine)"
        } catch {
            Write-Host "PID $procId (could not read command line)"
        }
    }
}

Write-Host ""
Write-Host "=== API health ==="
try {
    $resp = Invoke-RestMethod -Uri "http://127.0.0.1:$apiPort/health" -TimeoutSec 2
    Write-Host "status: $($resp.status)  version: $($resp.version)  gl: $($resp.gl.available)"
} catch {
    Write-Host "API not reachable on port $apiPort"
}
