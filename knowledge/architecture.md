# Arquitectura y Convenciones de AURA Core 0.2

- **Origen:** Documentación oficial interna
- **Nivel de Confianza:** 1.0 (Máxima prioridad)
- **Fecha de Validación:** 2026-10-22

## Principios Fundamentales
1. **Inferencia Local First:** Priorizar modelos abiertos y ejecución local mediante `llama-server`.
2. **Cero Heurísticas Frágiles:** No utilizar condicionales de palabras clave ni expresiones regulares para determinar la intención del usuario. El modelo debe decidir autónomamente sus llamadas a herramientas mediante ChatML / OpenAI function calling.
3. **Guardarraíles de Seguridad:** Nunca ejecutar comandos destructivos de PowerShell (`rmdir /s`, `Remove-Item -Recurse -Force`, `format`, borrado masivo de bases de datos).
4. **Respeto a Procesos Críticos:** Los procesos de trading en segundo plano (bots de trading en `Bot-08-09`) NUNCA deben terminarse ni interrumpirse.
