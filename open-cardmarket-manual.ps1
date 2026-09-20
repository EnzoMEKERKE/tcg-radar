# Reuse the dedicated marketplace profile, including the existing eBay session.
& (Join-Path $PSScriptRoot 'open-ebay-manual.ps1') -Marketplace cardmarket
exit $LASTEXITCODE
