param([ValidateSet('ebay','cardmarket')][string]$Marketplace = 'ebay')
$ErrorActionPreference = 'Stop'
$profilePath = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '.local-browser/profile'))
# Never use the user's personal Chrome profile or stop their browser processes.
$profileSlash = $profilePath.Replace('\', '/')
$running = Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" | Where-Object {
    $_.CommandLine -and ($_.CommandLine.Contains($profilePath) -or $_.CommandLine.Contains($profileSlash))
}
if ($running) {
    Write-Host 'Ferme d''abord la fenetre Chrome dediee ouverte par TCG-RADAR, puis relance ce script.'
    Write-Host 'Tes onglets Chrome personnels peuvent rester ouverts.'
    exit 1
}
$candidates = @(
    (Join-Path $env:ProgramFiles 'Google/Chrome/Application/chrome.exe'),
    (Join-Path ${env:ProgramFiles(x86)} 'Google/Chrome/Application/chrome.exe'),
    (Join-Path $env:LOCALAPPDATA 'Google/Chrome/Application/chrome.exe')
)
$chromePath = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $chromePath) { throw 'Google Chrome est introuvable sur ce PC.' }
New-Item -ItemType Directory -Path $profilePath -Force | Out-Null
# This is an interactive browser explicitly intended for the user's sign-in.
$startUrl = if ($Marketplace -eq 'cardmarket') { 'https://www.cardmarket.com/fr/Pokemon' } else { 'https://signup.ebay.fr/pa/crte' }
Start-Process -FilePath $chromePath -ArgumentList @(
    ('--user-data-dir="' + $profilePath + '"'),
    '--no-first-run',
    $startUrl
)
Write-Host 'Chrome manuel ouvert : aucun pilotage automatique dans cette fenetre.'
Write-Host ('Termine toi-meme la connexion sur ' + $Marketplace + '.')
Write-Host 'Ferme ensuite cette fenetre AVANT de rouvrir la session locale dans TCG-RADAR.'
Write-Host 'Ne lance pas d''analyse pendant cette etape. Le profil dedie est conserve.'
