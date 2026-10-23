"""
Sistema de Memoria y Base de Conocimiento de AURA Core 0.2.
Utiliza SQLite FTS5 (Full-Text Search) nativo de Python para búsquedas instantáneas
de documentación verificada, manuales y registro de correcciones (feedback).
Cero dependencias pesadas: funciona 100% offline con la biblioteca estándar.
"""

import os
import sqlite3
import re
import json
from typing import List, Dict, Optional
from datetime import datetime
from pathlib import Path

class LocalMemory:
    def __init__(self, db_path=None, base_dir=None):
        if base_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.base_dir = base_dir
        if db_path is None:
            db_path = os.path.join(base_dir, "memory.db")
        self.db_path = db_path
        self.knowledge_dir = os.path.join(base_dir, "knowledge")
        self.feedback_dir = os.path.join(base_dir, "feedback")
        self.feedback_file = os.path.join(self.feedback_dir, "feedback_log.jsonl")

        os.makedirs(self.knowledge_dir, exist_ok=True)
        os.makedirs(self.feedback_dir, exist_ok=True)

        self._init_db()
        self.sync_knowledge_directory()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        
        # Tabla de documentos verificados (Knowledge)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT UNIQUE,
                title TEXT,
                category TEXT,
                trust_level REAL DEFAULT 1.0,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        try:
            cur.execute("ALTER TABLE documents ADD COLUMN trust_level REAL DEFAULT 1.0")
        except Exception:
            pass

        # Tabla virtual FTS5 para búsqueda instantánea en base de conocimiento
        cur.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS doc_index USING fts5(
                source,
                title,
                content,
                tokenize='unicode61'
            )
        """)

        # Tabla de Feedback y correcciones del usuario (para revisión antes de pasar a datasets)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT,
                user_correction TEXT,
                agent_output TEXT,
                status TEXT DEFAULT 'pending_review',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        conn.close()

    def add_document(self, source: str, title: str, content: str, category: str = "general", trust_level: float = 1.0):
        """Indexa o actualiza un documento verificado en la base de conocimiento."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        
        cur.execute("DELETE FROM documents WHERE source = ?", (source,))
        cur.execute("DELETE FROM doc_index WHERE source = ?", (source,))
        
        cur.execute(
            "INSERT INTO documents (source, title, category, trust_level) VALUES (?, ?, ?, ?)",
            (source, title, category, trust_level)
        )
        cur.execute(
            "INSERT INTO doc_index (source, title, content) VALUES (?, ?, ?)",
            (source, title, content)
        )
        conn.commit()
        conn.close()

    def sync_knowledge_directory(self) -> int:
        """Lee todos los archivos markdown y de texto en knowledge/ y los indexa automáticamente."""
        indexed_count = 0
        if not os.path.exists(self.knowledge_dir):
            return 0

        for root, _, files in os.walk(self.knowledge_dir):
            for file in files:
                if file.lower().endswith(('.md', '.txt', '.py', '.json')):
                    full_path = os.path.join(root, file)
                    rel_source = os.path.relpath(full_path, self.base_dir)
                    try:
                        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                            content = f.read().strip()
                        if not content:
                            continue
                        
                        # Extraer título de la primera línea si es markdown
                        first_line = content.split("\n")[0].strip("# ").strip()
                        title = first_line if first_line else file
                        category = os.path.basename(root) if root != self.knowledge_dir else "general"

                        self.add_document(source=rel_source, title=title, content=content, category=category, trust_level=1.0)
                        indexed_count += 1
                    except Exception:
                        pass
        return indexed_count

    def search_knowledge(self, query: str, limit: int = 3) -> List[Dict]:
        """Busca fragmentos relevantes en la base de conocimiento verificada."""
        clean_query = re.sub(r'[^\w\s]', ' ', query).strip()
        if not clean_query:
            return []
        
        # Palabras clave de al menos 3 caracteres
        terms = [f'"{w}"' for w in clean_query.split() if len(w) > 2]
        if not terms:
            terms = [f'"{w}"' for w in clean_query.split() if len(w) > 1]
        if not terms:
            return []

        fts_query = " OR ".join(terms)

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        try:
            cur.execute("""
                SELECT d.source, d.title, d.category, d.trust_level,
                       snippet(doc_index, 2, '>>', '<<', '...', 35) as snippet,
                       doc_index.content,
                       doc_index.rank
                FROM doc_index
                JOIN documents d ON d.source = doc_index.source
                WHERE doc_index MATCH ? AND (d.trust_level >= 1.0 OR d.source LIKE '%knowledge%')
                ORDER BY d.trust_level DESC, doc_index.rank ASC
                LIMIT ?
            """, (fts_query, limit))
            
            rows = cur.fetchall()
            results = []
            for row in rows:
                results.append({
                    "source": row[0],
                    "title": row[1],
                    "category": row[2],
                    "trust_level": row[3],
                    "snippet": row[4],
                    "content": row[5][:1500], # Limitar tamaño para contexto
                    "score": round(row[6], 3)
                })
            conn.close()
            return results
        except Exception:
            conn.close()
            return []

    def record_feedback(self, query: str, user_correction: str, agent_output: str = ""):
        """Registra una corrección del usuario en SQLite y en feedback_log.jsonl para posterior revisión."""
        now_str = datetime.now().isoformat()
        entry = {
            "timestamp": now_str,
            "query": query,
            "user_correction": user_correction,
            "agent_output": agent_output,
            "status": "pending_review"
        }

        # Guardar en JSONL permanente
        try:
            with open(self.feedback_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

        # Guardar en SQLite
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO user_feedback (query, user_correction, agent_output, status)
                VALUES (?, ?, ?, 'pending_review')
            """, (query, user_correction, agent_output))
            conn.commit()
            conn.close()
        except Exception:
            pass

    def get_stats(self) -> Dict:
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM documents")
        total_docs = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM user_feedback")
        total_feedback = cur.fetchone()[0]
        conn.close()
        return {
            "total_documents_indexed": total_docs,
            "total_feedback_pending": total_feedback
        }
