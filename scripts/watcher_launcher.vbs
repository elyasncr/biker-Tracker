' Sobe o robo de sync do Bike Tracker em modo loop, sem janela nenhuma.
' Usado pela pasta de Inicializacao do Windows (autostart no logon).
Dim shell, script
Set shell = CreateObject("WScript.Shell")
script = "D:\AI Solution\Bike_Graph\scripts\sync_from_phone.ps1"
shell.Run "powershell.exe -WindowStyle Hidden -ExecutionPolicy Bypass -NoProfile -File """ & script & """", 0, False
