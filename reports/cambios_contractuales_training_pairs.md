# AURA CORE — Registro de Cambios Contractuales del Dataset Piloto

**Fecha:** 2026-10-26  
**Documento Fuente:** [`reports/auditoria_calidad_training_pairs.md`](file:///c:/Users/Guille/Downloads/IA/reports/auditoria_calidad_training_pairs.md)  
**Dataset Modificado:** [`datasets/training_pairs_pilot.json`](file:///c:/Users/Guille/Downloads/IA/datasets/training_pairs_pilot.json)  
**Copia de Respaldo Previa a Modificaciones:** [`datasets/training_pairs_pilot.pre_correction.json`](file:///c:/Users/Guille/Downloads/IA/datasets/training_pairs_pilot.pre_correction.json)  
**Respaldo Histórico Original Intacto:** [`datasets/training_pairs_pilot.original.json`](file:///c:/Users/Guille/Downloads/IA/datasets/training_pairs_pilot.original.json)  
**Entorno de Revalidación:** Debian 13 WSL2 (`aura_sandbox`, aislamiento con `unshare -r -n`)  
**Estado Final del Dataset:** **APTO** (100% de ambigüedades resueltas)

---

## 1. Justificación y Alcance de las Correcciones

Durante la auditoría de calidad previa se observó que en 4 tareas existía una discordancia terminológica en la redacción del contrato textual: los contratos agrupaban genéricamente bajo `ValueError` tanto los fallos de tipo de datos (que idiomáticamente en Python arrojan `TypeError`) como los fallos de valor, dominio o sintaxis (que arrojan `ValueError`).

La directiva técnica instruyó:
1. Comparar `contract`, `input_signature`, `reference_solution`, `edge_cases` y `tests`.
2. Determinar el comportamiento esperado a partir del problema completo y de los requisitos existentes.
3. Aclarar el contrato para distinguir inequívocamente `TypeError` (tipo de argumento incorrecto) de `ValueError` (valor o dominio inválido).
4. No alterar innecesariamente las soluciones de referencia ni las suites de pruebas existentes.
5. Preservar la trazabilidad completa mediante copias de seguridad.

---

## 2. Detalle de Cambios por `task_id`

### 2.1. `train_05_interval_disjoint_intersection`

- **Categoría:** `code_generation`
- **Contrato Anterior:**
```text
Implementa intersect_interval_lists(first_list: list[list[int]], second_list: list[list[int]]) -> list[list[int]].
Dadas dos listas de intervalos cerrados [start, end] ordenadas y disjuntas cada una, retorna su intersección por pares.
Validaciones:
- Si cualquier lista no es list o contiene intervalos no válidos (start > end o no enteros), levantar ValueError.
- Si una de las listas es vacía, retornar [].
- Retornar una nueva lista con los intervalos de intersección resultantes.
```

- **Contrato Corregido:**
```text
Implementa intersect_interval_lists(first_list: list[list[int]], second_list: list[list[int]]) -> list[list[int]].
Dadas dos listas de intervalos cerrados [start, end] ordenadas y disjuntas cada una, retorna su intersección por pares.
Validaciones:
- Si first_list o second_list no son listas, o algún límite de intervalo no es entero, levantar TypeError.
- Si algún intervalo no es una secuencia de 2 elementos o start > end, levantar ValueError.
- Si una de las listas es vacía, retornar [].
- Retornar una nueva lista con los intervalos de intersección resultantes.
```

- **Justificación:** La solución canónica implementa validación estricta de tipos (`if not isinstance(first_list, list) ... raise TypeError` y `if not isinstance(s, int) ... raise TypeError`), reservando `ValueError` para inconsistencias de tamaño (`len(item) != 2`) y de orden numérico (`start > end`). El contrato anterior provocaba una contradicción al exigir `ValueError` para entradas no listas. Se alineó la redacción para distinguir nítidamente tipo (`TypeError`) de dominio del intervalo (`ValueError`).

---

### 2.2. `train_14_roman_numeral_strict_parser`

- **Categoría:** `edge_cases`
- **Contrato Anterior:**
```text
Implementa roman_to_int(roman: str) -> int con validación estricta de la notación romana estándar.
Valores: I=1, V=5, X=10, L=50, C=100, D=500, M=1000.
Reglas sustractivas válidas exclusivas: IV(4), IX(9), XL(40), XC(90), CD(400), CM(900).
Validaciones:
- No se permiten más de 3 repeticiones consecutivas de I, X, C, M (ej. 'IIII' es inválido).
- V, L, D no pueden repetirse ni restarse jamás (ej. 'VV' o 'VX' es inválido).
- Substracciones no estándar (ej. 'IL', 'IC', 'XD') levantan ValueError.
- Si no es str o está vacía, levantar ValueError.
```

- **Contrato Corregido:**
```text
Implementa roman_to_int(roman: str) -> int con validación estricta de la notación romana estándar.
Valores: I=1, V=5, X=10, L=50, C=100, D=500, M=1000.
Reglas sustractivas válidas exclusivas: IV(4), IX(9), XL(40), XC(90), CD(400), CM(900).
Validaciones:
- Si roman no es str, levantar TypeError.
- Si roman es cadena vacía, levantar ValueError('roman string cannot be empty').
- No se permiten más de 3 repeticiones consecutivas de I, X, C, M (ej. 'IIII' es inválido).
- V, L, D no pueden repetirse ni restarse jamás (ej. 'VV' o 'VX' es inválido).
- Substracciones no estándar (ej. 'IL', 'IC', 'XD') o sintaxis no canónica levantan ValueError.
```

- **Justificación:** En la solución canónica, `if not isinstance(roman, str)` levanta `TypeError`, mientras que `if not roman` y los fallos de regex levantan `ValueError`. Agrupar tipos incorrectos bajo `ValueError` en el contrato violaba el principio de tipado idiomático de Python y confundía la especificación para el entrenamiento del modelo.

---

### 2.3. `train_15_ip_network_cidr_validator`

- **Categoría:** `edge_cases`
- **Contrato Anterior:**
```text
Implementa is_ip_in_cidr(ip: str, cidr: str) -> bool que determine si una dirección IPv4 pertenece a una red CIDR.
Validaciones obligatorias:
- IPv4 válida: exactamente 4 octetos enteros entre 0 y 255 separados por punto, sin ceros a la izquierda (ej. '01' es inválido) excepto '0' solo.
- CIDR válido: 'ip_base/prefix' donde prefix es entero entre 0 y 32, y la ip_base cumple el formato IPv4.
- Si ip o cidr tienen formato inválido, levantar ValueError.
- Retornar True si ip pertenece al rango de red, False en caso contrario.
```

- **Contrato Corregido:**
```text
Implementa is_ip_in_cidr(ip: str, cidr: str) -> bool que determine si una dirección IPv4 pertenece a una red CIDR.
Validaciones obligatorias:
- Si ip o cidr no son cadenas de texto (str), levantar TypeError.
- IPv4 válida: exactamente 4 octetos enteros entre 0 y 255 separados por punto, sin ceros a la izquierda (ej. '01' es inválido) excepto '0' solo.
- CIDR válido: 'ip_base/prefix' donde prefix es entero entre 0 y 32, y la ip_base cumple el formato IPv4.
- Si ip o cidr tienen formato inválido (octetos fuera de rango, ceros iniciales, prefijo inválido o sin separador '/'), levantar ValueError.
- Retornar True si ip pertenece al rango de red, False en caso contrario.
```

- **Justificación:** La solución realiza explícitamente `if not isinstance(ip, str) or not isinstance(cidr, str): raise TypeError(...)` antes de proceder al parsing numérico y bitwise de los octetos (`ValueError`). La aclaración explícita de `TypeError` en el contrato formaliza este comportamiento defensivo sin dejarlo implícito.

---

### 2.4. `train_20_refactor_polymorphic_discount_engine`

- **Categoría:** `refactoring`
- **Contrato Anterior:**
```text
Refactoriza un motor de cálculo de precios en una función pura apply_discount_rules(order: dict) -> dict.
Reglas de contrato estricto:
- order es un dict con claves obligatorias: 'items_subtotal' (float >= 0), 'user_tier' ('standard', 'gold', 'vip'), 'coupon_code' (str opcional).
- Descuentos por tier: 'standard': 0%, 'gold': 10%, 'vip': 20%.
- Cupones: 'SAVE10': $10 fijos; 'SAVE20': $20 fijos. Un cupón no puede descontar más del 50% del subtotal tras el tier discount.
- Inmutabilidad: Retorna un NUEVO diccionario {'final_price': float, 'discount_applied': float} sin mutar order.
- Si items_subtotal < 0 o user_tier desconocido, levantar ValueError.
- El precio final nunca puede ser negativo (mínimo 0.0).
```

- **Contrato Corregido:**
```text
Refactoriza un motor de cálculo de precios en una función pura apply_discount_rules(order: dict) -> dict.
Reglas de contrato estricto:
- Si order no es un diccionario (dict), levantar TypeError.
- order contiene claves: 'items_subtotal' (float o int >= 0), 'user_tier' ('standard', 'gold', 'vip'), 'coupon_code' (str opcional).
- Descuentos por tier: 'standard': 0%, 'gold': 10%, 'vip': 20%.
- Cupones: 'SAVE10': $10 fijos; 'SAVE20': $20 fijos. Un cupón no puede descontar más del 50% del subtotal tras el tier discount.
- Inmutabilidad: Retorna un NUEVO diccionario {'final_price': float, 'discount_applied': float} sin mutar order.
- Si items_subtotal < 0, falta items_subtotal o no es numérico, o user_tier es desconocido, levantar ValueError.
- El precio final nunca puede ser negativo (mínimo 0.0).
```

- **Justificación:** La solución verifica `if not isinstance(order, dict): raise TypeError("order must be a dictionary")` y `if subtotal is None or not isinstance(subtotal, (int, float)) or subtotal < 0: raise ValueError(...)`. Se formalizó en el contrato la regla explícita de `TypeError` para el argumento de la función y de `ValueError` para subtotales faltantes, no numéricos o negativos.

---

## 3. Resultados Comparativos: Antes vs Después de la Revalidación

| Dimensión de Control | Antes de la Corrección | Después de la Corrección | Estado Comparativo |
|---|---|---|---|
| **Soluciones de Referencia en Sandbox** | 20 / 20 PASS (100.0%) | 20 / 20 PASS (100.0%) | **Sin regresiones** |
| **Mutation Testing (Sensibilidad de Tests)** | 20 / 20 KILLED (100.0%) | 20 / 20 KILLED (100.0%) | **Máxima sensibilidad mantenida** |
| **Pruebas Unitarias Evaluador (`evals`)** | 23 / 23 PASS (100.0%) | 23 / 23 PASS (100.0%) | **Filtro AST y runner estables** |
| **Esquema JSON y Campos Obligatorios** | 20 / 20 conformes | 20 / 20 conformes | **100% íntegro** |
| **Discordancias Tipo vs Valor en Contrato** | 4 observaciones abiertas | **0 observaciones abiertas** | **100% subsanado** |
| **Ambigüedades Pendientes de Decisión** | 4 registros bajo revisión | **0 registros ambiguos** | **Resuelto inequívocamente** |

---

## 4. Incidencias y Decisiones Pendientes

- **Ambigüedades Contractuales:** **Ninguna**. Las especificaciones de los 20 problemas son completas, inequívocas y coherentes con los principios idiomáticos de Python.
- **Acciones Pendientes para el Fine-Tuning:**
  - El dataset piloto queda en estado óptimo para servir como núcleo y plantilla de generación masiva (hacia 100-200 pares).
  - No se requiere ninguna modificación de código ni de pruebas adicionales sobre el lote piloto.

---

## 5. Estado Final del Dataset

### Veredicto: **APTO**
El dataset `datasets/training_pairs_pilot.json` ha superado todas las pruebas estáticas, dinámicas, de mutación y de consistencia conceptual. Queda validado y listo para ser utilizado en las fases posteriores de ampliación y preparación para fine-tuning.
