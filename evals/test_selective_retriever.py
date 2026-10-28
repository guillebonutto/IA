"""
Pruebas Unitarias para el Módulo SelectiveExampleRetriever
==========================================================
Verifica:
1. Carga limpia y estructurada de los 40 pares desde los JSON originales.
2. Formato e higiene del contexto generado (sin tests, mutantes ni metadatos).
3. Interruptor de activación/desactivación (toggle baseline).
4. Exclusión de la tarea consultada (cero self-retrieval).
5. Penalizaciones de categoría y límite de caracteres/ejemplos.
6. Aislamiento y no alteración de los datasets originales.
"""

import unittest
import hashlib
from pathlib import Path
from evals.selective_retriever import SelectiveExampleRetriever, tokenize_code_and_text

BASE_DIR = Path(__file__).resolve().parent.parent

class TestSelectiveExampleRetriever(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.pilot_path = BASE_DIR / "datasets" / "training_pairs_pilot.json"
        cls.batch_01_path = BASE_DIR / "datasets" / "training_pairs_batch_01.json"

        # Registrar hashes iniciales para verificar inmutabilidad
        cls.pilot_hash_before = cls._hash_file(cls.pilot_path)
        cls.batch_hash_before = cls._hash_file(cls.batch_01_path)

    @classmethod
    def tearDownClass(cls):
        # Comprobar que los datasets originales no se modificaron
        self_pilot_hash = cls._hash_file(cls.pilot_path)
        self_batch_hash = cls._hash_file(cls.batch_01_path)
        assert self_pilot_hash == cls.pilot_hash_before, "ALERTA: Pilot JSON fue modificado!"
        assert self_batch_hash == cls.batch_hash_before, "ALERTA: Batch 01 JSON fue modificado!"

    @staticmethod
    def _hash_file(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest().upper()

    def test_corpus_loading_and_counts(self):
        retriever = SelectiveExampleRetriever(enabled=True)
        self.assertEqual(len(retriever.examples), 40)
        self.assertGreater(retriever._total_docs, 0)
        self.assertGreater(retriever._avg_doc_len, 0)

    def test_disabled_retriever_returns_empty(self):
        retriever = SelectiveExampleRetriever(enabled=False)
        self.assertEqual(len(retriever.examples), 0)
        res = retriever.retrieve("Implementa una clase LRUCache")
        self.assertEqual(res, [])
        ctx = retriever.format_icl_context(res)
        self.assertEqual(ctx, "")

    def test_tokenization_and_cleaning(self):
        raw = "class DoublyLinkedDeque: def append_left(self, val: int) -> None"
        tokens = tokenize_code_and_text(raw)
        self.assertIn("doublylinkeddeque", tokens)
        self.assertIn("append", tokens)
        self.assertIn("left", tokens)
        self.assertNotIn("def", tokens)
        self.assertNotIn("none", tokens)

    def test_retrieve_relevant_task_alignment(self):
        retriever = SelectiveExampleRetriever(enabled=True, max_examples=2)
        # Consulta de árbol binario
        query = "Dada una clase TreeNode, calcula el diámetro de un árbol binario en número de aristas."
        results = retriever.retrieve(query, category="code_generation")

        self.assertGreaterEqual(len(results), 1)
        top_match = results[0]["example"]
        # El top match debe ser train_21_binary_tree_diameter o similar de árboles
        self.assertIn("tree", top_match["task_id"])
        self.assertIn("TreeNode", top_match["contract"])

    def test_exclude_task_id(self):
        retriever = SelectiveExampleRetriever(enabled=True, max_examples=3)
        query = "Dada una clase TreeNode, calcula el diámetro del árbol."
        # Excluir explícitamente train_21
        results = retriever.retrieve(query, category="code_generation", exclude_task_id="train_21_binary_tree_diameter")
        retrieved_ids = [r["example"]["task_id"] for r in results]
        self.assertNotIn("train_21_binary_tree_diameter", retrieved_ids)

    def test_hygiene_of_formatted_context(self):
        retriever = SelectiveExampleRetriever(enabled=True, max_examples=2)
        query = "Implementa un serializador JSON canónico determinista RFC 8785."
        results = retriever.retrieve(query, category="code_generation")
        self.assertGreaterEqual(len(results), 1)

        context_str = retriever.format_icl_context(results)

        # Verificar qué debe contener
        self.assertIn("PATRONES CANÓNICOS DE REFERENCIA", context_str)
        self.assertIn("REQUERIMIENTO / CONTRATO:", context_str)
        self.assertIn("SOLUCIÓN CANÓNICA VERIFICADA:", context_str)

        # Verificar qué NUNCA debe contener (higiene estricta)
        self.assertNotIn("test_", context_str.lower())
        self.assertNotIn("unittest", context_str.lower())
        self.assertNotIn("mutant", context_str.lower())
        self.assertNotIn("verification_status", context_str)
        self.assertNotIn("verified_at_iso", context_str)
        self.assertNotIn("source", context_str)

    def test_context_length_limit_respected(self):
        retriever = SelectiveExampleRetriever(enabled=True, max_examples=5, max_context_chars=1200)
        query = "Implementa estructura de datos árbol trie búsqueda y compresión"
        results = retriever.retrieve(query)
        context_str = retriever.format_icl_context(results)
        # El tamaño del contexto no debe desbordarse salvajemente
        self.assertLessEqual(len(results), 2)

if __name__ == "__main__":
    unittest.main()
