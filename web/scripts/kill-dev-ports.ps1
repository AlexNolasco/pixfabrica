# Kill orphaned Pixfabrica dev servers (Vite + uvicorn) by port.
# Usage: powershell -ExecutionPolicy Bypass -File web/scripts/kill-dev-ports.ps1
# Env: PIXFABRICA_WEB_PORT (default 5173), PIXFABRICA_API_PORT (default 8000)

$webPort = if ($env:PIXFABRICA_WEB_PORT) { [int]$env:PIXFABRICA_WEB_PORT } else { 5173 }
$apiPort = if ($env:PIXFABRICA_API_PORT) { [int]$env:PIXFABRICA_API_PORT } else { 8000 }
$ports = @($webPort, $apiPort) | Sort-Object -Unique

function Stop-ListenerOnPort([int]$port) {
    $killed = @()
    $pids = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique)
    if (-not $pids.Count) {
        Write-Host "Port $port -> (nothing listening)"
        return $killed
    }
    foreach ($procId in $pids) {
        $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
        $name = if ($proc) { $proc.ProcessName } else { "?" }
        $cmd = ""
        try {
            $wmi = Get-CimInstance Win32_Process -Filter "ProcessId=$procId" -ErrorAction Stop
            $cmd = $wmi.CommandLine
        } catch {}
        Write-Host "Port $port -> PID $procId ($name)"
        if ($cmd) { Write-Host "  $cmd" }
        if ($proc) {
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        } else {
            # Zombie listener — try taskkill anyway.
            & taskkill.exe /F /PID $procId 2>$null | Out-Null
        }
        $killed += $procId
        Write-Host "  killed"
    }
    return $killed
}

$killed = @()
foreach ($port in $ports) {
    $killed += Stop-ListenerOnPort $port
}

# uvicorn --reload leaves a parent reloader + worker; kill any stragglers by command line.
$apiProcs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        $_.CommandLine -and (
            $_.CommandLine -match 'pixfabrica_api\.main:app' -or
            $_.CommandLine -match 'uvicorn.*--port\s+' + $apiPort
        )
    }
foreach ($p in $apiProcs) {
    if ($killed -contains $p.ProcessId) { continue }
    Write-Host "Extra API process PID $($p.ProcessId)"
    Write-Host "  $($p.CommandLine)"
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    $killed += $p.ProcessId
    Write-Host "  killed"
}

if (-not $killed.Count) {
    Write-Host "No dev servers were running."
} else {
    Write-Host "Done. Killed PIDs: $($killed -join ', ')"
}
