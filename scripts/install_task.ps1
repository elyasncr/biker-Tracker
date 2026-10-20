<#
.SYNOPSIS
    Registra (ou remove) uma Tarefa Agendada do Windows que roda o
    sync_from_phone.ps1 sozinho: no logon e a cada 5 minutos, sem janela.

.PARAMETER Uninstall
    Remove a tarefa.

.PARAMETER IntervalMinutes
    De quanto em quanto tempo repetir. Padrao: 5.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\install_task.ps1
    powershell -ExecutionPolicy Bypass -File scripts\install_task.ps1 -Uninstall
#>

[CmdletBinding()]
param(
    [switch] $Uninstall,
    [int]    $IntervalMinutes = 5
)

$ErrorActionPreference = "Stop"
$TaskName = "BikeTracker-SyncFromPhone"
$Script   = Join-Path $PSScriptRoot "sync_from_phone.ps1"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Tarefa '$TaskName' removida." -ForegroundColor Green
    } else {
        Write-Host "Tarefa '$TaskName' nao existe." -ForegroundColor Yellow
    }
    return
}

if (-not (Test-Path $Script)) { throw "Nao achei $Script" }

$psArgs  = "-WindowStyle Hidden -ExecutionPolicy Bypass -NoProfile -File `"$Script`" -Once"
$action  = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $psArgs

# Dispara no logon e repete a cada N minutos, indefinidamente.
$trigger = New-ScheduledTaskTrigger -AtLogOn
$rep = (New-ScheduledTaskTrigger -Once -At (Get-Date) `
          -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)).Repetition
$trigger.Repetition = $rep

$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
              -DontStopIfGoingOnBatteries -StartWhenAvailable `
              -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Description "Puxa .fit novos do celular para o Bike Tracker" `
    -Force | Out-Null

Write-Host "Tarefa '$TaskName' registrada: roda no logon e a cada $IntervalMinutes min." -ForegroundColor Green
Write-Host "Ver:    Get-ScheduledTask -TaskName $TaskName"
Write-Host "Rodar:  Start-ScheduledTask -TaskName $TaskName"
Write-Host "Tirar:  powershell -ExecutionPolicy Bypass -File scripts\install_task.ps1 -Uninstall"
