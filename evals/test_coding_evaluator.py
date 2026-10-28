"""
Tests unitarios y estáticos del Evaluador de Calidad de Programación de AURA CORE.
Verifica:
1. Extracción robusta de bloques simples, múltiples y detección de formato ambiguo/truncado.
2. Clasificación precisa entre SyntaxError (fallo de solución) y SecurityViolation.
3. Bloqueo de ejecución en host no aislado (defensa activa de seguridad).
4. Manejo de sinónimos en español y negaciones/desmentidos en rúbricas léxicas.
5. Detección y bloqueo de redefinición de clases objetivo en mutation testing.

RESTRICCIÓN: Ningún test en esta suite ejecuta código peligroso ni realiza inferencia o red.
"""

import unittest
from unittest.mock import patch
from pathlib import Path

from evals.coding_evaluator import (
    extract_python_code,
    static_safety_check,
    execute_code_test,
    execute_in_sandbox,
    check_for_target_redefinition,
    check_fallacy_with_negation,
    evaluate_semantic_rubric,
    evaluate_mutation_testing,
    is_isolated_environment_available,
    validate_extra_files_paths
)

class TestCodingEvaluator(unittest.TestCase):

    # -------------------------------------------------------------------------
    # 1. Extracción de código Markdown (bloques simples, múltiples y ambiguos)
    # -------------------------------------------------------------------------
    def test_extract_python_code_single_block(self):
        text = "Aquí está la función:\n```python\ndef solve(x):\n    return x * 2\n```\nExplicación adicional."
        code, err = extract_python_code(text)
        self.assertIsNone(err)
        self.assertEqual(code, "def solve(x):\n    return x * 2")

    def test_extract_python_code_multiple_blocks(self):
        text = (
            "Primero definimos el helper:\n"
            "```python\n"
            "class Node:\n"
            "    def __init__(self, val):\n"
            "        self.val = val\n"
            "```\n"
            "Y ahora la clase principal:\n"
            "```python\n"
            "class Tree:\n"
            "    def __init__(self):\n"
            "        self.root = None\n"
            "```\n"
        )
        code, err = extract_python_code(text)
        self.assertIsNone(err)
        self.assertIn("class Node:", code)
        self.assertIn("class Tree:", code)
        # Ambos bloques deben estar presentes y concatenados
        self.assertTrue(code.startswith("class Node:"))
        self.assertTrue(code.endswith("self.root = None"))

    def test_extract_python_code_unclosed_block_fails(self):
        # Respuesta truncada por max_tokens con fence de apertura pero sin cierre
        text_truncated = "```python\ndef calculate_something():\n    val = 10"
        code, err = extract_python_code(text_truncated)
        self.assertEqual(code, "")
        self.assertIsNotNone(err)
        self.assertIn("bloque de código Markdown sin cerrar", err)

    def test_extract_python_code_generic_blocks(self):
        text = "```\ndef helper():\n    return 42\n```"
        code, err = extract_python_code(text)
        self.assertIsNone(err)
        self.assertEqual(code, "def helper():\n    return 42")

    def test_extract_python_code_raw_valid_python(self):
        text = "def raw_func(a, b):\n    return a + b\n"
        code, err = extract_python_code(text)
        self.assertIsNone(err)
        self.assertEqual(code, "def raw_func(a, b):\n    return a + b")

    def test_extract_python_code_invalid_conversational_text_fails(self):
        text = "No estoy seguro de cómo resolver este problema, te sugiero buscar en internet."
        code, err = extract_python_code(text)
        self.assertEqual(code, "")
        self.assertIsNotNone(err)
        self.assertIn("Formato ambiguo", err)

    # -------------------------------------------------------------------------
    # 2. Clasificación: distincion entre SyntaxError y Violaciones de Seguridad
    # -------------------------------------------------------------------------
    def test_static_safety_distinguishes_syntax_error(self):
        # Código sintácticamente incompleto/inválido
        broken_syntax = "def broken_fn(x:\n    return x +"
        safe, category, msg = static_safety_check(broken_syntax)
        self.assertFalse(safe)
        self.assertEqual(category, "SYNTAX_ERROR")
        self.assertIn("Error de sintaxis", msg)

    def test_static_safety_identifies_security_violation(self):
        # Intento de uso de subprocess
        dangerous_subprocess = "import subprocess\nsubprocess.run(['dir'])"
        safe, category, msg = static_safety_check(dangerous_subprocess)
        self.assertFalse(safe)
        self.assertEqual(category, "SECURITY_VIOLATION")
        self.assertIn("Módulo no autorizado", msg)

        # Intento de os.system
        dangerous_os_system = "import os\nos.system('echo hi')"
        safe, category, msg = static_safety_check(dangerous_os_system)
        self.assertFalse(safe)
        self.assertEqual(category, "SECURITY_VIOLATION")
        self.assertIn("Llamada a función restringida", msg)

    def test_static_safety_accepts_clean_standard_code(self):
        clean_code = "from collections import OrderedDict, defaultdict\nimport math\ndef calc(): return math.sqrt(16)"
        safe, category, msg = static_safety_check(clean_code)
        self.assertTrue(safe)
        self.assertEqual(category, "OK")
        self.assertEqual(msg, "")

    def test_static_safety_allows_collection_remove_methods(self):
        # set.remove y list.remove son métodos legítimos en memoria
        set_code = "seen = set()\nseen.add(1)\nseen.remove(1)"
        safe, category, msg = static_safety_check(set_code)
        self.assertTrue(safe)
        self.assertEqual(category, "OK")

        list_code = "items = [1, 2, 3]\nitems.remove(2)"
        safe, category, msg = static_safety_check(list_code)
        self.assertTrue(safe)
        self.assertEqual(category, "OK")

        # Caso específico de gen_08 con stack.remove(node) en conjunto
        graph_code = "stack = set(['a'])\nstack.remove('a')"
        safe, category, msg = static_safety_check(graph_code)
        self.assertTrue(safe)
        self.assertEqual(category, "OK")

    def test_static_safety_blocks_file_and_os_removal(self):
        # os.remove debe ser bloqueado estrictamente
        os_remove_code = "import os\nos.remove('/tmp/target.txt')"
        safe, category, msg = static_safety_check(os_remove_code)
        self.assertFalse(safe)
        self.assertEqual(category, "SECURITY_VIOLATION")
        self.assertIn("Llamada a función de sistema restringida", msg)

        # from os import remove debe ser bloqueado estrictamente
        import_from_os = "from os import remove\nremove('/tmp/target.txt')"
        safe, category, msg = static_safety_check(import_from_os)
        self.assertFalse(safe)
        self.assertEqual(category, "SECURITY_VIOLATION")
        self.assertIn("Función de sistema no autorizada importada", msg)

        # pathlib.Path.unlink debe ser bloqueado
        pathlib_unlink = "from pathlib import Path\nPath('/tmp/test').unlink()"
        safe, category, msg = static_safety_check(pathlib_unlink)
        self.assertFalse(safe)
        self.assertEqual(category, "SECURITY_VIOLATION")
        self.assertIn("Llamada a función restringida: 'unlink'", msg)

    # -------------------------------------------------------------------------
    # 3. Seguridad: Bloqueo de ejecución en host no aislado
    # -------------------------------------------------------------------------
    @patch("evals.coding_evaluator.is_isolated_environment_available")
    def test_untrusted_host_execution_blocked_when_isolation_unavailable(self, mock_iso):
        mock_iso.return_value = (False, "No existe un entorno de aislamiento real verificado")
        code = "def add(a, b): return a + b"
        test = "import unittest\nclass T(unittest.TestCase): pass"
        # Si el entorno aislado no está disponible, la ejecución queda estrictamente bloqueada
        res = execute_code_test(code, test)
        self.assertFalse(res["passed"])
        self.assertEqual(res["status"], "EXECUTION_BLOCKED_UNSAFE_ENVIRONMENT")
        self.assertIn("No existe un entorno de aislamiento real", res["error"])

    @patch("evals.coding_evaluator.subprocess.run")
    @patch("evals.coding_evaluator.is_isolated_environment_available")
    def test_execution_blocked_without_invoking_subprocess_when_isolation_unavailable(
        self, mock_iso, mock_subprocess_run
    ):
        mock_iso.return_value = (False, "No existe un entorno de aislamiento real verificado")
        code = "def add(a, b): return a + b"
        test = "import unittest\nclass T(unittest.TestCase): pass"

        res = execute_code_test(code, test)

        self.assertEqual(res["status"], "EXECUTION_BLOCKED_UNSAFE_ENVIRONMENT")
        mock_subprocess_run.assert_not_called()

    def test_isolated_environment_detection_status(self):
        # Verifica la función de diagnóstico de entorno aislado
        available, msg = is_isolated_environment_available()
        self.assertIsInstance(available, bool)
        self.assertIsInstance(msg, str)
        self.assertTrue(len(msg) > 0)
        # En este entorno con Debian WSL2 configurado, debe ser True
        self.assertTrue(available, f"El entorno aislado debería estar disponible: {msg}")

    def test_syntax_error_reported_without_host_execution(self):
        # Si el código tiene un SyntaxError, debe reportarse inmediatamente como SYNTAX_ERROR
        broken_code = "def broken_code(:"
        res = execute_code_test(broken_code, "")
        self.assertFalse(res["passed"])
        self.assertEqual(res["status"], "SYNTAX_ERROR")
        self.assertIn("Error de sintaxis", res["error"])

    # -------------------------------------------------------------------------
    # 4. Rúbricas Léxicas: Sinónimos en español y manejo de negaciones
    # -------------------------------------------------------------------------
    def test_semantic_rubric_accepts_spanish_synonyms(self):
        rubric = {
          "required_concepts": [
            ["gil", "global interpreter lock"],
            ["reference counting", "conteo de referencias", "cuenta de referencias"],
            ["cpu-bound", "intensivo en cpu", "cálculo intensivo"],
            ["ipc", "comunicación entre procesos", "tuberías"]
          ],
          "prohibited_fallacies": [
            "multiprocessing siempre es mejor"
          ],
          "minimum_word_count": 10
        }
        spanish_response = (
            "En Python, el GIL protege el conteo de referencias interno para evitar "
            "condiciones de carrera. Las cargas de cálculo intensivo no escalan en hilos, "
            "y usar procesos requiere comunicación entre procesos."
        )
        res = evaluate_semantic_rubric(spanish_response, rubric)
        self.assertTrue(res["passed"], f"Falló con error: {res['error']}")
        self.assertEqual(len(res["missing_concepts"]), 0)

    def test_semantic_rubric_negation_prevents_false_positive_fallacy(self):
        rubric = {
          "required_concepts": ["gil"],
          "prohibited_fallacies": [
            "multiprocessing siempre es mejor",
            "los threads son inútiles en python"
          ],
          "minimum_word_count": 10
        }
        # El modelo desmiente explícitamente ambas falacias usando negaciones
        refuting_response = (
            "El GIL es clave en CPython. No es cierto que multiprocessing siempre es mejor "
            "debido al costo de IPC. Es falso que los threads son inútiles en python, ya que "
            "en tareas de red funcionan de manera óptima."
        )
        res = evaluate_semantic_rubric(refuting_response, rubric)
        self.assertTrue(res["passed"], f"No debió penalizar falacias desmentidas: {res['error']}")
        self.assertEqual(len(res["detected_fallacies"]), 0)

    def test_semantic_rubric_detects_unnegated_fallacy(self):
        rubric = {
          "required_concepts": ["gil"],
          "prohibited_fallacies": [
            "multiprocessing siempre es mejor"
          ],
          "minimum_word_count": 10
        }
        fallacy_response = (
            "El GIL limita la ejecución de hilos. Por lo tanto, multiprocessing siempre es mejor "
            "en todos los casos posibles sin excepción alguna."
        )
        res = evaluate_semantic_rubric(fallacy_response, rubric)
        self.assertFalse(res["passed"])
        self.assertIn("multiprocessing siempre es mejor", res["detected_fallacies"])

    # -------------------------------------------------------------------------
    # 5. Mutation Testing: Detección y prevención de sobreescritura de mutantes
    # -------------------------------------------------------------------------
    def test_mutation_testing_blocks_redefinition_of_target_class(self):
        candidate_with_override = (
            "import unittest\n"
            "class BankAccount:\n"  # Redefinición prohibida
            "    def __init__(self, *args): pass\n\n"
            "class TestBankAccount(unittest.TestCase):\n"
            "    def test_dummy(self): pass\n"
        )
        mutation_spec = {
            "canonical_implementation": "class BankAccount: pass",
            "mutants": [{"id": "m1", "description": "dummy", "code_diff": "class BankAccount: pass"}]
        }
        res = evaluate_mutation_testing(candidate_with_override, mutation_spec)
        self.assertFalse(res["passed"])
        self.assertIn("redefine la clase 'BankAccount'", res["error"])

    @patch("evals.coding_evaluator.is_isolated_environment_available")
    def test_mutation_testing_blocks_when_isolation_unavailable(self, mock_iso):
        mock_iso.return_value = (False, "No existe un entorno de aislamiento real verificado")
        clean_candidate_test = (
            "import unittest\n"
            "from bank_account import BankAccount\n"
            "class TestBankAccount(unittest.TestCase):\n"
            "    def test_ok(self): pass\n"
        )
        mutation_spec = {
            "canonical_implementation": "class BankAccount: pass",
            "mutants": [{"id": "m1", "description": "dummy", "code_diff": "class BankAccount: pass"}]
        }
        res = evaluate_mutation_testing(clean_candidate_test, mutation_spec)
        self.assertFalse(res["passed"])
        self.assertEqual(res["status"], "EXECUTION_BLOCKED_UNSAFE_ENVIRONMENT")

    @patch("evals.coding_evaluator.is_isolated_environment_available")
    @patch("evals.coding_evaluator.execute_code_test")
    def test_mutation_testing_preserves_canonical_failure_diagnostic(
        self, mock_execute, mock_iso
    ):
        mock_iso.return_value = (True, "WSL2 disponible")
        diagnostic = ("traceback detail " * 40) + "AttributeError: initial_balance is unavailable"
        mock_execute.return_value = {
            "status": "FAIL",
            "passed": False,
            "error": diagnostic,
            "elapsed_s": 0.1,
        }
        candidate = (
            "import unittest\n"
            "class TestBankAccount(unittest.TestCase):\n"
            "    def test_balance(self): pass\n"
        )
        mutation_spec = {
            "canonical_implementation": "class BankAccount: pass",
            "mutants": [{"id": "m1", "description": "dummy", "code_diff": "class BankAccount: pass"}]
        }

        result = evaluate_mutation_testing(candidate, mutation_spec)

        self.assertFalse(result["passed"])
        self.assertIn("AttributeError: initial_balance is unavailable", result["error"])
        self.assertGreater(len(result["error"]), 300)
        mock_execute.assert_called_once()

    # -------------------------------------------------------------------------
    # 6. Validación de Rutas: Protección contra escapes en extra_files
    # -------------------------------------------------------------------------
    def test_validate_extra_files_accepts_clean_relative_paths(self):
        clean_files = {
            "bank_account.py": "class BankAccount: pass",
            "utils/helper.py": "def f(): pass",
            "data_v1.json": "{}"
        }
        ok, err = validate_extra_files_paths(clean_files)
        self.assertTrue(ok)
        self.assertEqual(err, "")

    def test_validate_extra_files_rejects_path_traversal(self):
        traversal_cases = [
            {"../escape.py": "code"},
            {"a/../../escape.py": "code"},
            {"sub/../..": "code"},
            {"..": "code"}
        ]
        for bad in traversal_cases:
            ok, err = validate_extra_files_paths(bad)
            self.assertFalse(ok, f"Debió rechazar path traversal: {bad}")
            self.assertIn("..", err)

    def test_validate_extra_files_rejects_absolute_paths(self):
        abs_cases = [
            {"/etc/passwd": "code"},
            {"/tmp/malicious.py": "code"},
            {"C:/Windows/System32/evil.dll": "code"},
            {"D:\\data.txt": "code"}
        ]
        for bad in abs_cases:
            ok, err = validate_extra_files_paths(bad)
            self.assertFalse(ok, f"Debió rechazar ruta absoluta: {bad}")
            self.assertIn("Ruta absoluta", err)

    def test_validate_extra_files_rejects_empty_and_invalid_chars(self):
        invalid_cases = [
            {"": "code"},
            {"   ": "code"},
            {"foo//bar.py": "code"},
            {"invalid*name?.py": "code"},
            {"bad|pipe.py": "code"}
        ]
        for bad in invalid_cases:
            ok, err = validate_extra_files_paths(bad)
            self.assertFalse(ok, f"Debió rechazar nombre inválido: {bad}")

if __name__ == "__main__":
    unittest.main()
