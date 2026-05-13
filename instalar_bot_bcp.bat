@echo off
setlocal

cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python nao encontrado.
    echo Instale o Python 3 antes de continuar: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo Instalando dependencias do Bot BCP...
python -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo Falha ao instalar as dependencias Python.
    pause
    exit /b 1
)

echo Instalando Chromium do Playwright...
python -m playwright install chromium
if errorlevel 1 (
    echo Falha ao instalar o Chromium do Playwright.
    pause
    exit /b 1
)

echo Criando/atualizando tarefa agendada diaria as 10h...
powershell -ExecutionPolicy Bypass -File "%~dp0agendar_bot_bcp.ps1"
if errorlevel 1 (
    echo Falha ao criar a tarefa agendada.
    pause
    exit /b 1
)

echo.
echo Instalacao concluida.
echo Para fazer a primeira validacao do site, rode executar_bot_bcp.bat.
pause
