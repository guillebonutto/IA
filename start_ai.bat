@echo off
title AURA CORE - Iniciando IA Local Zero-Bloat
cd /d "%~dp0"

echo ==========================================================
echo    AURA CORE - SISTEMA DE IA LOCAL ULTRA-OPTIMIZADO
echo ==========================================================
echo.

set "MODEL_FILE=%~dp0models\Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"
if not exist "%MODEL_FILE%" (
    for %%F in ("%~dp0models\*.gguf") do (
        if exist "%%F" set "MODEL_FILE=%%F"
    )
)

if not exist "%MODEL_FILE%" (
    echo [ERROR] No se encuentra ningun archivo de modelo .gguf en models\
    pause
    exit /b
)

echo [1/3] Iniciando motor de inferencia nativo (Llama 3.1 8B Instruct)...
echo       Modelo: %MODEL_FILE%
start "AURA - Motor Inferencia (llama.cpp)" /min "%~dp0bin\llama-server.exe" -m "%MODEL_FILE%" -lm none -c 2048 -t 4 -np 1 --port 8089 --host 127.0.0.1

echo [2/3] Iniciando servidor del Agente y UI Web...
start "AURA - Servidor Web Agente" /min python "%~dp0agent\server.py" 5000

echo [3/3] Abriendo interfaz en el navegador...
timeout /t 3 /nobreak >nul
start http://127.0.0.1:5000

echo.
echo ==========================================================
echo  [LISTO] AURA CORE esta activo.
echo  Interfaz web abierta en: http://127.0.0.1:5000
echo  Para detener el sistema, ejecuta 'stop_ai.bat' o cierra las ventanas.
echo ==========================================================
echo.
pause
