@echo off
cd /d "%~dp0"
where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" /min pythonw "%~dp0extrair_html_bcp.py" --headed --minimized
) else (
    start "" /min python "%~dp0extrair_html_bcp.py" --headed --minimized
)
