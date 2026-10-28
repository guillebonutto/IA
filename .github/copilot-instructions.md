# Instrucciones del proyecto AURA CORE

## Objetivo

Mejorar AURA CORE como asistente local, priorizando rendimiento medible, calidad funcional, estabilidad y bajo consumo de recursos.

## Entorno de referencia

- Referencia documentada: Windows 10 Pro x64, AMD Ryzen 5 2400G (4 núcleos/8 hilos, AVX2), 32 GB de RAM, `llama.cpp` y Qwen2.5-Coder-3B-Instruct Q4_K_M.
- Estos datos están respaldados por la auditoría en [`docs/benchmark-audit/README.md`](../docs/benchmark-audit/README.md). Verificá los archivos actuales cuando una decisión dependa de ellos; no asumas que una configuración documentada sigue activa ni extrapoles resultados fuera de las condiciones medidas.

## Límites de cambios

- No modificar `agent/`, `start_ai.bat` ni `start.ps1` sin autorización explícita del usuario.
- No detener procesos, cambiar configuraciones de producción ni modificar el puerto de producción sin autorización explícita.
- No hacer commits, pushes, resets destructivos ni eliminar o sobrescribir cambios del usuario sin autorización explícita.
- Antes de modificar código, inspeccionar `git status` y preservar todos los cambios existentes. No revertir ni sobrescribir trabajo ajeno al cambio solicitado.

## Implementación y validación

- Preferir cambios pequeños, reversibles y comprobables. Antes de implementar una mejora importante, explicar su objetivo, los archivos afectados, los riesgos y los criterios de aceptación.
- Medir el rendimiento con benchmarks reproducibles. Distinguir velocidad de generación, latencia total, uso de RAM y calidad funcional; no declarar una mejora basándose en una sola ejecución.
- Evitar ciclos autónomos indefinidos, exploraciones repetidas e interacciones innecesarias con Copilot. Preferir herramientas locales para pruebas, cálculos y análisis de datos.
- Al terminar, informar qué cambió, qué pruebas se ejecutaron y sus resultados, los riesgos pendientes y cualquier limitación.
