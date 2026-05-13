@echo off
setlocal

cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python nao encontrado.
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'Stop';" ^
  "$prod = Join-Path $env:USERPROFILE 'Bot BCP';" ^
  "$htmlDir = Join-Path $prod 'html';" ^
  "if (-not (Test-Path -LiteralPath $htmlDir)) { throw 'Nenhum HTML salvo encontrado. Rode o bot normal uma vez antes deste teste.' }" ^
  "$latest = Get-ChildItem -LiteralPath $htmlDir -Filter '*.html' | Sort-Object LastWriteTime -Descending | Select-Object -First 1;" ^
  "if (-not $latest) { throw 'Nenhum HTML salvo encontrado. Rode o bot normal uma vez antes deste teste.' }" ^
  "$testRoot = Join-Path $env:USERPROFILE 'Bot BCP Teste';" ^
  "$stamp = Get-Date -Format 'yyyyMMdd_HHmmss';" ^
  "$testBase = Join-Path $testRoot ('run_' + $stamp);" ^
  "$testInput = Join-Path $testBase 'inputs';" ^
  "New-Item -ItemType Directory -Force -Path $testInput | Out-Null;" ^
  "$original = Join-Path $testInput ('original_' + $stamp + '.html');" ^
  "$changed = Join-Path $testInput ('mudado_' + $stamp + '.html');" ^
  "Copy-Item -LiteralPath $latest.FullName -Destination $original -Force;" ^
  "$html = Get-Content -LiteralPath $original -Raw -Encoding UTF8;" ^
  "$q = [char]34;" ^
  "$fake = '<div class=' + $q + 'list__item search-item' + $q + ' data-value=2099 data-mes=teste data-categoria=Circulares><h3 class=item__title>CIRCULAR SV.SG. N 999/2099 TESTE AUTOMATICO DO BOT BCP</h3><p class=item__description>Esta circular fake foi criada apenas para testar a deteccao de mudanca.</p><div class=item__links><a href=' + $q + 'https://www.bcp.gov.py/documents/teste-bot-bcp.pdf' + $q + ' class=' + $q + 'link btn-gray btn-small' + $q + ' download>download Descargar</a></div></div>';" ^
  "$pattern = '<div class=' + $q + 'list__item search-item' + $q;" ^
  "$idx = $html.IndexOf($pattern);" ^
  "if ($idx -lt 0) { throw 'Nao encontrei a lista de circulares no HTML salvo.' }" ^
  "$html = $html.Insert($idx, $fake + [Environment]::NewLine);" ^
  "Set-Content -LiteralPath $changed -Value $html -Encoding UTF8;" ^
  "Write-Host 'HTML original:' $original;" ^
  "Write-Host 'HTML mudado:' $changed;" ^
  "Write-Host 'Base de teste:' $testBase;" ^
  "& python '.\extrair_html_bcp.py' --source-html $original --base-dir $testBase --no-open --no-pdf;" ^
  "if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }" ^
  "Start-Sleep -Seconds 1;" ^
  "& python '.\extrair_html_bcp.py' --source-html $changed --base-dir $testBase --no-pdf;" ^
  "exit $LASTEXITCODE"

if errorlevel 1 (
    echo.
    echo Teste falhou.
    pause
    exit /b 1
)

echo.
echo Teste concluido. O relatorio final deve apontar a circular fake como nova.
pause
