import sqlite3
import os

DB_PATH = "data/processos.db"

def init_db():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS processos (
            id TEXT PRIMARY KEY,
            autor TEXT,
            reu TEXT,
            status TEXT,
            atualizado_em TEXT
        )
    """)
    conn.commit()
    conn.close()

def inserir_processo(id, autor, reu, status, atualizado_em):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO processos (id, autor, reu, status, atualizado_em)
        VALUES (?, ?, ?, ?, ?)
    """, (id, autor, reu, status, atualizado_em))
    conn.commit()
    conn.close()

def listar_processos():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM processos")
    rows = cursor.fetchall()
    conn.close()
    return rows

def processo_existe(id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM processos WHERE id = ?", (id,))
    count = cursor.fetchone()[0]
    conn.close()
    return count > 0

def excluir_processo(id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM processos WHERE id = ?", (id,))
    conn.commit()
    conn.close()