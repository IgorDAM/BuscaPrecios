# Registra en el Programador de tareas de Windows la actualizacion semanal de
# Alcampo (scripts\actualizar_alcampo_completo.bat).
#
# Uso (una sola vez), desde la carpeta del proyecto:
#     powershell -ExecutionPolicy Bypass -File scripts\programar_alcampo.ps1
# Opcional: otro dia/hora ->  ... -File scripts\programar_alcampo.ps1 -Dia Saturday -Hora 10:30
#
# Para quitarla:  Unregister-ScheduledTask -TaskName "BuscaPrecios Alcampo" -Confirm:$false
#
# Se ejecuta CON TU SESION ABIERTA (hace falta: abre un Chrome fuera de pantalla)
# y el PC encendido. Si a esa hora estaba apagado, se lanza al encenderlo
# (StartWhenAvailable). Necesita que git ya tenga tus credenciales guardadas
# (las que usas en VS Code / "git push").
param(
    [string]$Dia = "Sunday",
    [string]$Hora = "16:00"
)

$bat = Join-Path $PSScriptRoot "actualizar_alcampo_completo.bat"
if (-not (Test-Path $bat)) { throw "No encuentro $bat" }

$accion = New-ScheduledTaskAction -Execute "cmd.exe" `
    -Argument "/c `"`"$bat`" nopause`"" `
    -WorkingDirectory (Split-Path $PSScriptRoot)
$disparador = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $Dia -At $Hora
$ajustes = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 4)

Register-ScheduledTask -TaskName "BuscaPrecios Alcampo" `
    -Description "Actualiza el catalogo de Alcampo (Gijon) para la web y el movil" `
    -Action $accion -Trigger $disparador -Settings $ajustes -Force | Out-Null

Write-Host "Tarea 'BuscaPrecios Alcampo' creada: cada $Dia a las $Hora."
Write-Host "Para probarla ya:  Start-ScheduledTask -TaskName 'BuscaPrecios Alcampo'"
