<#
.SYNOPSIS
    Puxa os .fit novos exportados do iGPSPORT no celular (via adb) para a pasta
    data/ do Bike Tracker e dispara o POST /api/sync.

.DESCRIPTION
    Fluxo pensado para dar o minimo de trabalho:
      1. No app iGPSPORT: abrir o treino -> Compartilhar/Exportar arquivo.
         O .fit cai na pasta Download (ou Documents) do celular.
      2. Este script, rodando no PC, percebe o arquivo novo, puxa para
         data/from-phone/ e chama o sync. O resto do pipeline (dedup por
         SHA-256, calculo de metricas) acontece sozinho.

    So pega arquivos .fit em armazenamento ACESSIVEL (Download/Documents).
    A memoria privada do app nao e lida - o aparelho nao e root e o app
    tem allowBackup="false". Por isso o passo de exportar no app e manual.

.PARAMETER Once
    Roda uma unica varredura e sai (ideal para Agendador de Tarefas).
    Sem este switch, fica em loop vigiando.

.PARAMETER IntervalSeconds
    Intervalo entre varreduras no modo loop. Padrao: 120.

.PARAMETER Serial
    Serial do aparelho adb. Se vazio, usa o unico conectado.

.PARAMETER ApiUrl
    Base da API. Padrao: http://localhost:8000

.EXAMPLE
    # loop, vigiando o celular a cada 2 min
    powershell -ExecutionPolicy Bypass -File scripts\sync_from_phone.ps1

.EXAMPLE
    # uma varredura so (para agendar)
    powershell -ExecutionPolicy Bypass -File scripts\sync_from_phone.ps1 -Once
#>

[CmdletBinding()]
param(
    [switch] $Once,
    [int]    $IntervalSeconds = 120,
    [string] $Serial = "",
    [string] $ApiUrl = "http://127.0.0.1:8000"
)

$ErrorActionPreference = "Stop"

# --- Onde ficam as coisas -------------------------------------------------
$Root     = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$DataDir  = Join-Path $Root "data"
$DestDir  = Join-Path $DataDir "from-phone"
# Pastas do celular onde o .fit exportado costuma cair:
$DeviceDirs = @("/sdcard/Download", "/sdcard/Documents")

# --- adb ------------------------------------------------------------------
$Adb = if ($env:REA_ADB_PATH) { $env:REA_ADB_PATH } else { "adb" }

function Resolve-Serial {
    if ($Serial) { return $Serial }
    $lines = @(& $Adb devices | Select-Object -Skip 1 |
               Where-Object { $_ -match "\sdevice\s*$" })
    if ($lines.Count -eq 0) { throw "Nenhum aparelho adb conectado (verifique o cabo e a depuracao USB)." }
    if ($lines.Count -gt 1) { throw "Mais de um aparelho conectado. Passe -Serial <serial>." }
    return ($lines[0] -split "\s+")[0]
}

function Get-DeviceFitFiles([string] $dev) {
    # Lista caminhos absolutos dos .fit nas pastas acessiveis do celular.
    $args = $DeviceDirs | ForEach-Object { "'$_'" }
    $cmd  = "find $($args -join ' ') -maxdepth 1 -type f -iname '*.fit' 2>/dev/null"
    $out  = & $Adb -s $dev shell $cmd 2>$null
    return $out | Where-Object { $_ -and $_.Trim() } | ForEach-Object { $_.Trim() }
}

function Invoke-Sync {
    try {
        $r = Invoke-RestMethod -Method Post -Uri "$ApiUrl/api/sync" -TimeoutSec 120
        $n = if ($null -ne $r.imported) { $r.imported } else { $r }
        Write-Host ("  sync ok -> {0}" -f ($n | ConvertTo-Json -Compress)) -ForegroundColor Green
    } catch {
        Write-Host "  AVISO: nao consegui chamar o sync em $ApiUrl." -ForegroundColor Yellow
        Write-Host "         Os arquivos ja estao em data/; suba o backend e o boot faz o sync." -ForegroundColor Yellow
    }
}

function Scan-Once {
    $dev = Resolve-Serial
    New-Item -ItemType Directory -Force -Path $DestDir | Out-Null

    # Nomes de .fit que o projeto ja conhece (data/ inteiro, recursivo).
    $known = @{}
    Get-ChildItem -Path $DataDir -Recurse -Filter *.fit -ErrorAction SilentlyContinue |
        ForEach-Object { $known[$_.Name] = $true }

    $deviceFiles = Get-DeviceFitFiles $dev
    if (-not $deviceFiles) {
        Write-Host ("[{0}] nenhum .fit no celular." -f (Get-Date -Format HH:mm:ss))
        return
    }

    $pulled = 0
    foreach ($path in $deviceFiles) {
        $name = Split-Path $path -Leaf
        if ($known.ContainsKey($name)) { continue }   # ja temos esse
        $dest = Join-Path $DestDir $name
        Write-Host ("[{0}] puxando {1}" -f (Get-Date -Format HH:mm:ss), $name) -ForegroundColor Cyan
        & $Adb -s $dev pull "$path" "$dest" | Out-Null
        if (Test-Path $dest) { $pulled++ ; $known[$name] = $true }
    }

    if ($pulled -gt 0) {
        Write-Host ("  {0} arquivo(s) novo(s). Rodando sync..." -f $pulled)
        Invoke-Sync
    } else {
        Write-Host ("[{0}] nada novo ({1} .fit no celular, todos ja importados)." -f (Get-Date -Format HH:mm:ss), $deviceFiles.Count)
    }
}

Write-Host "Bike Tracker - sync do celular" -ForegroundColor Magenta
Write-Host ("  projeto : {0}" -f $Root)
Write-Host ("  destino : {0}" -f $DestDir)
Write-Host ("  api     : {0}" -f $ApiUrl)
Write-Host ""

if ($Once) {
    Scan-Once
} else {
    Write-Host ("Modo loop (a cada {0}s). Ctrl+C para parar." -f $IntervalSeconds)
    while ($true) {
        try { Scan-Once } catch { Write-Host ("  erro: {0}" -f $_.Exception.Message) -ForegroundColor Red }
        Start-Sleep -Seconds $IntervalSeconds
    }
}
