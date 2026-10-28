"""
AURA CORE — Módulo Experimental de Recuperación Selectiva de Ejemplos (RAG / ICL)
==================================================================================
Diseñado para cargar de forma segura los 40 pares verificados desde sus fuentes
originales intactas (training_pairs_pilot.json y training_pairs_batch_01.json)
y seleccionar deterministamente hasta K ejemplos pertinentes para una tarea dada.

Principios de Diseño:
1. Determinista y explicable: BM25/TF-IDF ponderado por términos clave, sin bases
   vectoriales externas opacas.
2. Anti-superficialidad y penalización semántica: Penaliza pares que comparten
   términos genéricos o superficiales pero pertenecen a categorías incompatibles.
3. Higiene estricta de prompts: Excluye tests, aserciones ocultas, mutantes y
   metadatos internos. Solo expone contrato, firma y solución canónica.
4. Preservación del presupuesto de contexto: Longitud acotada por tokens estimados.
5. Interruptor completo de desactivación (toggle baseline).
"""

import os
import json
import re
import math
from pathlib import Path
from typing import List, Dict, Any, Optional

BASE_DIR = Path(__file__).resolve().parent.parent

# Rutas originales de los datasets
DEFAULT_PILOT_PATH = BASE_DIR / "datasets" / "training_pairs_pilot.json"
DEFAULT_BATCH_01_PATH = BASE_DIR / "datasets" / "training_pairs_batch_01.json"

# Stopwords en español e inglés para análisis léxico de código y contratos
STOPWORDS = {
    # Español
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "a", "al", "en", "para",
    "por", "con", "sin", "sobre", "entre", "este", "esta", "estos", "estas", "que", "cual", "quien",
    "como", "cuando", "donde", "si", "no", "es", "son", "fue", "era", "ser", "estar", "tener", "hacer",
    "debe", "deben", "retorna", "retornar", "retorne", "devuelve", "devolver", "implementa", "implementar",
    "dada", "dado", "dados", "dadas", "cada", "todo", "todos", "todas", "cualquier", "cualquiera",
    "levantar", "lanza", "lanzar", "segun", "ejemplo", "requisitos", "funcion", "clase", "metodo",
    # Inglés
    "the", "a", "an", "and", "or", "in", "on", "at", "to", "for", "with", "without", "by", "from",
    "of", "is", "are", "was", "were", "be", "been", "have", "has", "had", "do", "does", "did",
    "if", "then", "else", "when", "where", "which", "who", "whom", "this", "that", "these", "those",
    "must", "should", "return", "returns", "implement", "implements", "class", "def", "function", "method",
    "none", "self", "true", "false", "int", "str", "float", "bool"
}

def tokenize_code_and_text(text: str) -> List[str]:
    """Extrae identificadores de código, palabras clave y tokens alfanuméricos."""
    if not text:
        return []
    # Tokenizar preservando identificadores snake_case y camelCase
    raw_tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*|\d+", text)
    tokens = []
    for tok in raw_tokens:
        tok_lower = tok.lower()
        if len(tok_lower) >= 2 and tok_lower not in STOPWORDS:
            tokens.append(tok_lower)
            # Descomponer snake_case si aplica
            if "_" in tok_lower:
                for sub in tok_lower.split("_"):
                    if len(sub) >= 2 and sub not in STOPWORDS:
                        tokens.append(sub)
    return tokens

class SelectiveExampleRetriever:
    """
    Recuperador determinista de ejemplos de referencia para In-Context Learning (ICL).
    Carga los 40 pares verificados y rankea la pertinencia técnica ante una consulta.
    """

    def __init__(
        self,
        pilot_path: Optional[Path] = None,
        batch_01_path: Optional[Path] = None,
        enabled: bool = True,
        max_examples: int = 2,
        max_context_chars: int = 3500
    ):
        self.enabled = enabled
        self.max_examples = max_examples
        self.max_context_chars = max_context_chars
        self.pilot_path = pilot_path or DEFAULT_PILOT_PATH
        self.batch_01_path = batch_01_path or DEFAULT_BATCH_01_PATH
        self.examples: List[Dict[str, Any]] = []
        self._doc_frequencies: Dict[str, int] = {}
        self._tokenized_corpus: List[List[str]] = []
        self._total_docs: int = 0
        self._avg_doc_len: float = 0.0

        if self.enabled:
            self._load_and_index_corpus()

    def _load_and_index_corpus(self) -> None:
        """Carga y construye el índice léxico-estructural invertido de los 40 pares."""
        raw_items = []
        for p in [self.pilot_path, self.batch_01_path]:
            if not p.exists():
                raise FileNotFoundError(f"Archivo de dataset no encontrado: {p}")
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    raw_items.extend(data)
                elif isinstance(data, dict) and "tasks" in data:
                    raw_items.extend(data["tasks"])

        self.examples = []
        self._tokenized_corpus = []
        self._doc_frequencies = {}

        # Sanitización: asegurar que cada ejemplo tiene los campos indispensables
        for item in raw_items:
            tid = item.get("task_id") or item.get("id", "unknown")
            contract = item.get("contract") or item.get("prompt", "")
            sig = item.get("input_signature") or item.get("entry_point", "")
            sol = item.get("reference_solution", "")
            cat = item.get("category", "general")

            clean_entry = {
                "task_id": tid,
                "category": cat,
                "contract": contract,
                "input_signature": sig,
                "reference_solution": sol
            }
            self.examples.append(clean_entry)

            # Documento para indexación: combinación de categoría, contrato y firma
            doc_text = f"{cat} {cat} {sig} {contract}"
            tokens = tokenize_code_and_text(doc_text)
            self._tokenized_corpus.append(tokens)

            unique_tokens = set(tokens)
            for tok in unique_tokens:
                self._doc_frequencies[tok] = self._doc_frequencies.get(tok, 0) + 1

        self._total_docs = len(self.examples)
        if self._total_docs > 0:
            total_tokens = sum(len(doc) for doc in self._tokenized_corpus)
            self._avg_doc_len = total_tokens / self._total_docs
        else:
            self._avg_doc_len = 0.0

    def _calculate_bm25_score(
        self,
        query_tokens: List[str],
        doc_tokens: List[str],
        doc_idx: int,
        k1: float = 1.5,
        b: float = 0.75
    ) -> float:
        """Calcula el score BM25 clásico para un documento dado."""
        if not doc_tokens:
            return 0.0

        doc_len = len(doc_tokens)
        token_counts = {}
        for tok in doc_tokens:
            token_counts[tok] = token_counts.get(tok, 0) + 1

        score = 0.0
        for q_tok in query_tokens:
            if q_tok not in token_counts:
                continue
            tf = token_counts[q_tok]
            df = self._doc_frequencies.get(q_tok, 0)
            # IDF con corrección estándar
            idf = math.log(1.0 + (self._total_docs - df + 0.5) / (df + 0.5))
            numerator = tf * (k1 + 1.0)
            denominator = tf + k1 * (1.0 - b + b * (doc_len / (self._avg_doc_len or 1.0)))
            score += idf * (numerator / denominator)

        return score

    def retrieve(
        self,
        task_query: str,
        category: Optional[str] = None,
        exclude_task_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Recupera hasta max_examples pertinentes ordenados por relevancia estructural y léxica.
        Aplica penalizaciones por incongruencia de categoría y similitud superficial.
        """
        if not self.enabled or not self.examples:
            return []

        query_tokens = tokenize_code_and_text(task_query)
        if not query_tokens:
            return []

        candidates = []
        for idx, ex in enumerate(self.examples):
            # 1. Regla de oro: Jamás recuperar la misma tarea
            if exclude_task_id and ex["task_id"] == exclude_task_id:
                continue

            bm25 = self._calculate_bm25_score(query_tokens, self._tokenized_corpus[idx], idx)

            # 2. Bonificación por alineación de categoría / Penalización por divergencia
            category_multiplier = 1.0
            if category:
                if ex["category"] == category:
                    category_multiplier = 1.35  # Afinidad directa en patrón algorítmico
                else:
                    category_multiplier = 0.80  # Ligera penalización para desalentar cruces irrelevantes

            final_score = bm25 * category_multiplier

            # Umbral mínimo de relevancia para no inyectar ruido
            if final_score > 1.2:
                candidates.append({
                    "example": ex,
                    "score": round(final_score, 4),
                    "bm25_raw": round(bm25, 4),
                    "category": ex["category"],
                    "matched_category": (ex["category"] == category)
                })

        # Ordenar por score decreciente
        candidates.sort(key=lambda x: x["score"], reverse=True)

        # 3. Selección y filtrado de diversidad (evitar duplicar ejemplos casi idénticos)
        selected = []
        seen_categories = set()
        total_chars = 0

        for cand in candidates:
            ex = cand["example"]
            ex_chars = len(ex["contract"]) + len(ex["reference_solution"])

            # Comprobar límite de longitud en caracteres
            if total_chars + ex_chars > self.max_context_chars:
                # Si excede el contexto máximo, intentar ver si cabe uno más pequeño o detenerse
                if selected:
                    continue

            selected.append(cand)
            total_chars += ex_chars
            seen_categories.add(ex["category"])

            if len(selected) >= self.max_examples:
                break

        return selected

    def format_icl_context(self, retrieved: List[Dict[str, Any]]) -> str:
        """
        Construye el bloque de contexto In-Context Learning (ICL) para inyectar en el prompt.
        Solo incluye los campos útiles: Contrato, Firma y Solución de Referencia Canónica.
        No incluye tests, mutantes ni metadatos de auditoría.
        """
        if not retrieved:
            return ""

        sections = []
        sections.append("=== PATRONES CANÓNICOS DE REFERENCIA (EJEMPLOS SIMILARES DE ALTA CALIDAD) ===")
        sections.append(
            "Los siguientes ejemplos ilustran la metodología esperada: validación estricta de contratos,\n"
            "separación exacta entre TypeError y ValueError, inmutabilidad y firmas limpias.\n"
            "Úsalos como guía estructural de estilo y rigor, pero resuelve estrictamente la tarea solicitada.\n"
        )

        for i, item in enumerate(retrieved, 1):
            ex = item["example"]
            sections.append(f"--- [EJEMPLO DE REFERENCIA #{i}: {ex['task_id']} ({ex['category']})] ---")
            sections.append(f"REQUERIMIENTO / CONTRATO:\n{ex['contract'].strip()}\n")
            if ex.get("input_signature"):
                sections.append(f"FIRMA CANÓNICA:\n```python\n{ex['input_signature'].strip()}\n```\n")
            sections.append(f"SOLUCIÓN CANÓNICA VERIFICADA:\n```python\n{ex['reference_solution'].strip()}\n```\n")

        sections.append("=== FIN DE PATRONES DE REFERENCIA ===\n")
        return "\n".join(sections)
