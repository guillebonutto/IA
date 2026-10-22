"""
Sistema de Memoria y RAG Local Ultraligero.
Utiliza SQLite FTS5 (Full-Text Search) nativo de Python para búsquedas instantáneas
de código, notas y documentos sin dependencias pesadas de vectores ni PyTorch.
"""

import os
import sqlite3
import re
from typing import List, Dict

class LocalMemory:
    def __init__(self, db_path=None):
        if db_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_path = os.path.join(base_dir, "memory.db")
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        # Tabla estándar para metadatos
        cur.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT UNIQUE,
                title TEXT,
                category TEXT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Tabla virtual FTS5 para búsqueda de texto completo instantánea
        cur.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS doc_index USING fts5(
                source,
                title,
                content,
                tokenize='unicode61'
            )
        """)
        conn.commit()
        conn.close()

    def add_document(self, source: str, title: str, content: str, category: str = "general"):
        """Indexa o actualiza un documento o fragmento de código."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        
        # Eliminar versión previa si existe
        cur.execute("DELETE FROM documents WHERE source = ?", (source,))
        cur.execute("DELETE FROM doc_index WHERE source = ?", (source,))
        
        cur.execute(
            "INSERT INTO documents (source, title, category) VALUES (?, ?, ?)",
            (source, title, category)
        )
        cur.execute(
            "INSERT INTO doc_index (source, title, content) VALUES (?, ?, ?)",
            (source, title, content)
        )
        conn.commit()
        conn.close()

    def search(self, query: str, limit: int = 5) -> List[Dict]:
        """Busca documentos relevantes por palabras clave y similitud semántica de términos."""
        clean_query = re.sub(r'[^\w\s]', ' ', query).strip()
        if not clean_query:
            return []
        
        # Convertir palabras a consulta FTS5 OR/AND
        terms = [f'"{w}"' for w in clean_query.split() if len(w) > 2]
        if not terms:
            terms = [f'"{w}"' for w in clean_query.split()]
        fts_query = " OR ".join(terms)

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        try:
            cur.execute("""
                SELECT source, title, snippet(doc_index, 2, '<b>', '</b>', '...', 25), rank
                FROM doc_index
                WHERE doc_index MATCH ?
                ORDER BY rank
                LIMIT ?
            """, (fts_query, limit))
            
            rows = cur.fetchall()
            results = []
            for row in rows:
                results.append({
                    "source": row[0],
                    "title": row[1],
                    "snippet": row[2],
                    "score": round(row[3], 3)
                })
            conn.close()
            return results
        except Exception:
            conn.close()
            return []

    def get_stats(self) -> Dict:
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM documents")
        total_docs = cur.fetchone()[0]
        conn.close()
        return {"total_documents_indexed": total_docs}
