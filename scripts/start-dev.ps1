$ErrorActionPreference = "Stop"

$workspace = Split-Path -Parent $PSScriptRoot
$webapp = Join-Path $workspace "webapp"
$backendProcess = $null

try {
    $listener = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1

    if (-not $listener) {
        $backendProcess = Start-Process `
            -FilePath "C:\Python312\python.exe" `
            -ArgumentList "-m", "uvicorn", "app:api", "--host", "127.0.0.1", "--port", "8000" `
            -WorkingDirectory $workspace `
            -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $workspace "uvicorn.out.log") `
            -RedirectStandardError (Join-Path $workspace "uvicorn.err.log") `
            -PassThru

        $ready = $false
        for ($attempt = 0; $attempt -lt 30; $attempt++) {
            Start-Sleep -Milliseconds 500
            try {
                $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health" -TimeoutSec 2
                if ($health.status -eq "ok") {
                    $ready = $true
                    break
                }
            } catch {
                if ($backendProcess.HasExited) {
                    break
                }
            }
        }

        if (-not $ready) {
            throw "FastAPI did not become ready. Check uvicorn.err.log."
        }
        Write-Host "FastAPI is ready at http://127.0.0.1:8000" -ForegroundColor Green
    } else {
        Write-Host "Using the backend already listening at http://127.0.0.1:8000" -ForegroundColor Green
    }

    Push-Location $webapp
    try {
        & npm.cmd run dev
    } finally {
        Pop-Location
    }
} finally {
    if ($backendProcess -and -not $backendProcess.HasExited) {
        Stop-Process -Id $backendProcess.Id -Force
        Write-Host "Stopped the FastAPI development process." -ForegroundColor Yellow
    }
}
