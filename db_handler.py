import sqlite3
import os

DB_PATH = "processos.db"

def init_db():
    """Inicializa o banco de dados e cria a tabela se necessário."""
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

def listar_processos():
    """Retorna todos os processos cadastrados."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, autor, reu, status, atualizado_em FROM processos")
    processos = cursor.fetchall()
    conn.close()
    return processos

def inserir_processo(id, autor, reu, status, atualizado_em):
    """Insere um novo processo no banco."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO processos (id, autor, reu, status, atualizado_em)
        VALUES (?, ?, ?, ?, ?)
    """, (id, autor, reu, status, atualizado_em))
    conn.commit()
    conn.close()

def processo_existe(id):
    """Verifica se um processo já existe no banco."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM processos WHERE id = ?", (id,))
    existe = cursor.fetchone()[0] > 0
    conn.close()
    return existe

def excluir_processo(id):
    """Exclui um processo do banco."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM processos WHERE id = ?", (id,))
    conn.commit()
    conn.close()