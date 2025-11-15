import sqlite3
import os

# Caminho do banco de dados
DB_PATH = "data/processos.db"

def init_db():
    """Inicializa o banco de dados e cria a tabela se não existir."""
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
    """Insere ou atualiza um processo no banco."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO processos (id, autor, reu, status, atualizado_em)
        VALUES (?, ?, ?, ?, ?)
    """, (id, autor, reu, status, atualizado_em))
    conn.commit()
    conn.close()

def listar_processos():
    """Retorna todos os processos como lista de tuplas."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM processos")
    rows = cursor.fetchall()
    conn.close()
    return rows

def processo_existe(id):
    """Verifica se um processo com o ID informado já existe."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM processos WHERE id = ?", (id,))
    count = cursor.fetchone()[0]
    conn.close()
    return count > 0

def excluir_processo(id):
    """Exclui um processo do banco pelo ID."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM processos WHERE id = ?", (id,))
    conn.commit()
    conn.close()