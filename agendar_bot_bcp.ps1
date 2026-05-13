$ErrorActionPreference = "Stop"

$TaskName = "Bot BCP - Circulares"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ScriptPath = Join-Path $ScriptDir "extrair_html_bcp.py"

$PythonCommand = Get-Command pythonw -ErrorAction SilentlyContinue
$Arguments = "`"$ScriptPath`" --headed --minimized"

if (-not $PythonCommand) {
    $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
}

if (-not $PythonCommand) {
    $PythonCommand = Get-Command pyw -ErrorAction SilentlyContinue
    $Arguments = "`"$ScriptPath`" --headed --minimized"
}

if (-not $PythonCommand) {
    $PythonCommand = Get-Command py -ErrorAction Stop
    $Arguments = "-3 `"$ScriptPath`" --headed --minimized"
}

$Action = New-ScheduledTaskAction `
    -Execute $PythonCommand.Source `
    -Argument $Arguments `
    -WorkingDirectory $ScriptDir

$Trigger = New-ScheduledTaskTrigger -Daily -At 10:00AM
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun
$Principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Principal $Principal `
    -Description "Monitora circulares e projetos normativos no site do Banco Central del Paraguay." `
    -Force

Write-Host "Tarefa agendada: $TaskName"
Write-Host "Horario: todos os dias as 10:00"
Write-Host "Script: $ScriptPath"
Write-Host "Executor: $($PythonCommand.Source)"
