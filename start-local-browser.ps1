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
& $pythonExe (Join-Path $projectRoot 'tools/start_local_browser.py')
exit $LASTEXITCODE
