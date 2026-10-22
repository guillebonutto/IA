<#
.SYNOPSIS
    Lanzador unificado en PowerShell para AURA CORE.
#>

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptDir

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "       AURA CORE - SISTEMA DE IA LOCAL ZERO-BLOAT         " -ForegroundColor Yellow
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host ""

$CustomModels = Get-ChildItem -Path (Join-Path $ScriptDir "models\*aura*.gguf") -ErrorAction SilentlyContinue
if ($CustomModels -and $CustomModels.Count -gt 0) {
    $ModelPath = $CustomModels[0].FullName
} else {
    $ModelPath = Join-Path $ScriptDir "models\qwen2.5-coder-1.5b-instruct-q4_k_m.gguf"
}
$BinPath = Join-Path $ScriptDir "bin\llama-server.exe"

if (-not (Test-Path $ModelPath)) {
    Write-Host "[ERROR] El modelo GGUF no se encuentra en $ModelPath" -ForegroundColor Red
    Write-Host "Espera a que finalice la descarga del modelo." -ForegroundColor Red
    pause
    exit
}

Write-Host "[1/3] Iniciando motor de inferencia nativo (llama.cpp AVX2/Vulkan)..." -ForegroundColor Green
Start-Process -FilePath $BinPath -ArgumentList "-m `"$ModelPath`" -c 8192 -t 4 -np 1 --port 8089 --host 127.0.0.1" -WindowStyle Minimized

Write-Host "[2/3] Iniciando servidor del Agente y UI Web..." -ForegroundColor Green
Start-Process -FilePath "python" -ArgumentList "`"$ScriptDir\agent\server.py`" 5000" -WindowStyle Minimized

Write-Host "[3/3] Abriendo navegador en http://127.0.0.1:5000..." -ForegroundColor Green
Start-Sleep -Seconds 3
Start-Process "http://127.0.0.1:5000"

Write-Host ""
Write-Host "[✓] AURA CORE esta activo y listo." -ForegroundColor Cyan
Write-Host "Para detenerlo ejecuta .\stop_ai.bat" -ForegroundColor Yellow
Write-Host "==========================================================" -ForegroundColor Cyan
