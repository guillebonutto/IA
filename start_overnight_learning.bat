@echo off
title AURA - Auto-Aprendizaje y Destilacion Nocturna
cd /d "%~dp0"

echo ==========================================================
echo    AURA - MODO DE AUTO-APRENDIZAJE NOCTURNO
echo ==========================================================
echo  Este proceso consultara a los modelos de 120B y Gemini
echo  mediante debate adversarial, destilando y guardando
echo  soluciones de elite en tu dataset local:
echo  data\distillation_dataset.jsonl
echo.
echo  - Puedes dejarlo corriendo toda la noche.
echo  - Puedes detenerlo en cualquier momento con Ctrl+C.
echo  - Respeta los limites de la capa gratuita (pausas de 12s).
echo ==========================================================
echo.

python -u "%~dp0agent\auto_distill.py" --target 400 --delay 18

echo.
echo Proceso finalizado. Presiona cualquier tecla para salir...
pause >nul
