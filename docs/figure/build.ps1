# Compile method.tex -> docs/method.pdf and docs/method.png (used by the README).
#   powershell -File docs\figure\build.ps1
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$bin = Get-ChildItem "$env:LOCALAPPDATA\Programs\MiKTeX" -Recurse -Filter pdflatex.exe | Select-Object -First 1 -ExpandProperty DirectoryName
& "$bin\pdflatex.exe" -interaction=nonstopmode -halt-on-error method.tex | Out-Null
if ($LASTEXITCODE -ne 0) { Select-String -Path method.log -Pattern '^!' -Context 0,4 | ForEach-Object { $_.ToString() }; exit 1 }
Copy-Item method.pdf ..\method.pdf -Force
& "$bin\pdftoppm.exe" -png -r 220 -singlefile method.pdf ..\method
Remove-Item method.aux, method.log -ErrorAction SilentlyContinue
Write-Host "ok: docs/method.pdf, docs/method.png"
