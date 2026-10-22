@echo off
title AURA CORE - Detener Servicios
cd /d "%~dp0"

echo Deteniendo motor llama-server...
taskkill /f /im llama-server.exe >nul 2>&1

echo Deteniendo servidor web del Agente...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5000" ^| findstr "LISTENING"') do (
    taskkill /f /pid %%a >nul 2>&1
)

echo.
echo ==========================================================
echo  [✓] Todos los servicios de AURA CORE han sido detenidos.
echo  Cero consumo de memoria RAM o CPU en segundo plano.
echo ==========================================================
pause
