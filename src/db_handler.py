import sqlite3
import os
from typing import List, Tuple
from datetime import datetime

# O caminho padrão do banco de dados (usado em produção)
# Ele cria o arquivo 'processos.db' na mesma pasta em que o script Streamlit está sendo executado.
DB_PATH = "processos.db" 

# --- Função de Conexão Centralizada (O Guardrail da Testabilidade) ---

def get_db_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    """
    Função auxiliar para estabelecer a conexão com o banco de dados.

    Se o 'db_path' for ':memory:', o Pytest usará um banco de dados temporário.
    Caso contrário, usará o 'processos.db' (produção).
    """
    return sqlite3.connect(db_path)

# --- Funções CRUD (Criação, Leitura, Atualização, Exclusão) ---

def init_db(db_path: str = DB_PATH):
    """
    Inicializa o banco de dados e cria a tabela 'processos' se ela não existir.
    """
    conn = get_db_connection(db_path)
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

def listar_processos(db_path: str = DB_PATH) -> List[Tuple]:
    """
    Retorna todos os processos cadastrados no banco de dados.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, autor, reu, status, atualizado_em FROM processos")
    processos = cursor.fetchall()
    conn.close()
    return processos

def inserir_processo(id: str, autor: str, reu: str, status: str, atualizado_em: str, db_path: str = DB_PATH):
    """
    Insere um novo processo no banco.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO processos (id, autor, reu, status, atualizado_em)
            VALUES (?, ?, ?, ?, ?)
        """, (id, autor, reu, status, atualizado_em))
        conn.commit()
    except sqlite3.IntegrityError:
        # Lidar com tentativa de inserir ID duplicado (embora 'home.py' já verifique)
        raise ValueError(f"O processo com ID {id} já existe no banco de dados.")
    finally:
        conn.close()

def processo_existe(id: str, db_path: str = DB_PATH) -> bool:
    """
    Verifica se um processo já existe no banco.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM processos WHERE id = ?", (id,))
    existe = cursor.fetchone()[0] > 0
    conn.close()
    return existe

def excluir_processo(id: str, db_path: str = DB_PATH):
    """
    Exclui um processo do banco de dados.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM processos WHERE id = ?", (id,))
    conn.commit()
    conn.close()

def atualizar_status(id: str, novo_status: str, db_path: str = DB_PATH):
    """
    Altera o status de um processo existente no banco, registrando a data/hora da mudança.
    Usado para Arquivar/Desarquivar/Concluir.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    # Adiciona a data/hora da atualização
    atualizado_em = datetime.now().strftime("%d/%m/%Y %H:%M:%S") 
    
    cursor.execute("""
        UPDATE processos SET status = ?, atualizado_em = ? WHERE id = ?
    """, (novo_status, atualizado_em, id))
    conn.commit()
    conn.close()