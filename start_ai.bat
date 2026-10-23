@echo off
title AURA CORE - IA Local Zero-Bloat Ultra-Optimizada
cd /d "%~dp0"

echo ===================================================================
echo     AURA CORE - MOTOR DE INFERENCIA NATIVO ZERO-BLOAT (AVX2)
echo ===================================================================
echo.
echo Selecciona el modelo a cargar en memoria:
echo.
echo  [1] Qwen 2.5 Coder 3B (Q4_K_M)   ^| ~10.5 t/s ^| RECOMENDADO: Codigo limpio y veloz
echo  [2] Llama 3.1 8B (Q3_K_M)        ^| ~4.8 t/s  ^| 8B Optimizado localmente (3.7 GB)
echo  [3] Llama 3.1 8B (Q4_K_M)        ^| ~4.7 t/s  ^| 8B Original (4.6 GB)
echo  [4] AURA Coder 1.5B Fine-Tuned   ^| ~20+ t/s  ^| Ultra-liviano para background
echo.

set "OPCION=1"
choice /c 1234 /t 5 /d 1 /n /m "Elige una opcion [1-4] (por defecto 1 en 5 seg): "
set "OPCION=%ERRORLEVEL%"

if "%OPCION%"=="1" (
    set "MODEL_FILE=%~dp0models\qwen2.5-coder-3b-instruct-q4_k_m.gguf"
    set "MODEL_NAME=Qwen 2.5 Coder 3B Instruct"
    set "CTX=4096"
)
if "%OPCION%"=="2" (
    set "MODEL_FILE=%~dp0models\Meta-Llama-3.1-8B-Instruct-Q3_K_M.gguf"
    set "MODEL_NAME=Meta-Llama 3.1 8B Instruct (Q3_K_M Optimizado)"
    set "CTX=4096"
)
if "%OPCION%"=="3" (
    set "MODEL_FILE=%~dp0models\Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"
    set "MODEL_NAME=Meta-Llama 3.1 8B Instruct (Q4_K_M Original)"
    set "CTX=4096"
)
if "%OPCION%"=="4" (
    set "MODEL_FILE=%~dp0models\AURA-Qwen2.5-Coder-1.5B-FineTuned.Q4_K_M.gguf"
    set "MODEL_NAME=AURA Coder 1.5B Fine-Tuned"
    set "CTX=8192"
)

if not exist "%MODEL_FILE%" (
    echo [!] Archivo no encontrado: %MODEL_FILE%
    echo     Buscando alternativa en models\...
    for %%F in ("%~dp0models\*.gguf") do (
        if exist "%%F" set "MODEL_FILE=%%F"
    )
)

echo.
echo ===================================================================
echo [1/3] Limpiando procesos previos y liberando puertos...
taskkill /f /im llama-server.exe >nul 2>&1

echo [2/3] Iniciando motor C++ con flags ultra-optimizados:
echo       - Modelo: %MODEL_NAME%
echo       - Hilos: 6 generacion / 8 batch (Sin sobrecargar SMT)
echo       - Contexto: %CTX% tokens
echo       - Optimizaciones: KV-Cache Q8_0, Flash-Attention, Memory Mapped (mmap)
echo.

start "AURA - Motor Inferencia (llama.cpp)" /min "%~dp0bin\llama-server.exe" -m "%MODEL_FILE%" -c %CTX% -t 6 -tb 8 --cache-type-k q8_0 --cache-type-v q8_0 -lm mmap -fa on -np 1 --port 8089 --host 127.0.0.1

echo [3/3] Iniciando Agente AURA y Web UI...
netstat -aon | findstr ":5000" | findstr "LISTENING" >nul
if errorlevel 1 (
    start "AURA - Servidor Web Agente" /min python "%~dp0agent\server.py" 5000
)

echo Abriendo navegador...
timeout /t 3 /nobreak >nul
start http://127.0.0.1:5000

echo.
echo ===================================================================
echo  [LISTO] AURA CORE esta activo con %MODEL_NAME%.
echo  Interfaz web abierta en: http://127.0.0.1:5000
echo  Para apagar todo sin dejar residuos: ejecuta 'stop_ai.bat'
echo ===================================================================
echo.
pause
