<#
.SYNOPSIS
    Lanzador unificado ultra-optimizado en PowerShell para AURA CORE.
#>

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptDir

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "       AURA CORE - SISTEMA DE IA LOCAL ZERO-BLOAT         " -ForegroundColor Yellow
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Modelos disponibles:"
Write-Host " [1] Qwen 2.5 Coder 3B (Q4_K_M) - 10.5 t/s [RECOMENDADO CODIGO]" -ForegroundColor Green
Write-Host " [2] Llama 3.1 8B (Q3_K_M)      - 4.8 t/s  [OPTIMIZADO 8B]" -ForegroundColor White
Write-Host " [3] Llama 3.1 8B (Q4_K_M)      - 4.7 t/s  [ORIGINAL 8B]" -ForegroundColor White
Write-Host " [4] AURA Coder 1.5B Fine-Tuned - 20+ t/s  [ULTRA-LIVIANO]" -ForegroundColor White
Write-Host ""

$choice = Read-Host "Elige una opcion [1-4] (default: 1)"
if (-not $choice) { $choice = "1" }

switch ($choice) {
    "1" {
        $ModelPath = Join-Path $ScriptDir "models\qwen2.5-coder-3b-instruct-q4_k_m.gguf"
        $Ctx = 4096
        $ModelName = "Qwen 2.5 Coder 3B Instruct"
    }
    "2" {
        $ModelPath = Join-Path $ScriptDir "models\Meta-Llama-3.1-8B-Instruct-Q3_K_M.gguf"
        $Ctx = 4096
        $ModelName = "Meta-Llama 3.1 8B Instruct (Q3_K_M)"
    }
    "3" {
        $ModelPath = Join-Path $ScriptDir "models\Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"
        $Ctx = 4096
        $ModelName = "Meta-Llama 3.1 8B Instruct (Q4_K_M)"
    }
    "4" {
        $ModelPath = Join-Path $ScriptDir "models\AURA-Qwen2.5-Coder-1.5B-FineTuned.Q4_K_M.gguf"
        $Ctx = 8192
        $ModelName = "AURA Coder 1.5B Fine-Tuned"
    }
    Default {
        $ModelPath = Join-Path $ScriptDir "models\qwen2.5-coder-3b-instruct-q4_k_m.gguf"
        $Ctx = 4096
        $ModelName = "Qwen 2.5 Coder 3B Instruct"
    }
}

$BinPath = Join-Path $ScriptDir "bin\llama-server.exe"

if (-not (Test-Path $ModelPath)) {
    Write-Host "[ERROR] El modelo GGUF no se encuentra en $ModelPath" -ForegroundColor Red
    pause
    exit
}

Write-Host "[1/3] Limpiando procesos previos..." -ForegroundColor Yellow
Stop-Process -Name "llama-server" -Force -ErrorAction SilentlyContinue

Write-Host "[2/3] Iniciando motor C++ ($ModelName) con flags optimizados..." -ForegroundColor Green
$ArgsList = "-m `"$ModelPath`" -c $Ctx -t 6 -tb 8 --cache-type-k q8_0 --cache-type-v q8_0 -lm mmap -fa on -np 1 --port 8089 --host 127.0.0.1"
Start-Process -FilePath $BinPath -ArgumentList $ArgsList -WindowStyle Minimized

Write-Host "[3/3] Iniciando servidor del Agente y UI Web..." -ForegroundColor Green
$AgentRunning = Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue
if (-not $AgentRunning) {
    Start-Process -FilePath "python" -ArgumentList "`"$ScriptDir\agent\server.py`" 5000" -WindowStyle Minimized
}

Start-Sleep -Seconds 3
Start-Process "http://127.0.0.1:5000"

Write-Host ""
Write-Host "[✓] AURA CORE esta activo con $ModelName." -ForegroundColor Cyan
Write-Host "Interfaz web: http://127.0.0.1:5000" -ForegroundColor Green
Write-Host "Para detenerlo ejecuta .\stop_ai.bat" -ForegroundColor Yellow
Write-Host "==========================================================" -ForegroundColor Cyan

