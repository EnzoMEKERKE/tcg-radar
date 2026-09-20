$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
try {
    $browserState = Invoke-RestMethod -Uri 'http://127.0.0.1:8766/status' -TimeoutSec 2
    if ($browserState.available) {
        Write-Host 'Le navigateur local est deja disponible dans TCG-RADAR.'
        exit 0
    }
} catch {}
$pythonExe = (Get-Command python -ErrorAction Stop).Source
$helperPath = Join-Path $projectRoot 'tools/local_deals_browser.py'
$logDir = Join-Path $projectRoot '.local-browser'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
Start-Process -FilePath $pythonExe -ArgumentList ('"' + $helperPath + '"') -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDir 'service.log') -RedirectStandardError (Join-Path $logDir 'service-error.log')
Write-Host 'Service lance. Ouvre http://localhost:8080/deals puis clique sur Ouvrir la session Chrome locale.'
