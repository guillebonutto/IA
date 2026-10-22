@echo off
title AURA CORE - Consola Interactiva
cd /d "%~dp0"

echo [1/2] Verificando motor de inferencia (llama.cpp)...
tasklist /fi "imagename eq llama-server.exe" | findstr /i "llama-server.exe" >nul
if errorlevel 1 (
    echo Iniciando motor llama-server ultrarrapido en segundo plano...
    start "AURA - Motor Inferencia (llama.cpp)" /min "%~dp0bin\llama-server.exe" -m "%~dp0models\qwen2.5-coder-1.5b-instruct-q4_k_m.gguf" -c 8192 -t 4 -np 1 --port 8089 --host 127.0.0.1
    timeout /t 3 /nobreak >nul
)

echo [2/2] Iniciando consola de comandos interactiva del Agente...
python "%~dp0run_cli.py"
pause
