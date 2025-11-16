"""
data_handler.py
Backend responsável por salvar, carregar, apagar e listar processos.
Compatível com o fluxo do arquivo pages/01_Gerar_laudo.py.
"""

import os
import json
from typing import Any, Dict, List

# ============================================================
# CONFIGURAÇÃO DO DIRETÓRIO DE DADOS
# ============================================================

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROCESS_DATA_DIR = os.path.join(BASE_DIR, "data")

# Garante que a pasta /data exista
os.makedirs(PROCESS_DATA_DIR, exist_ok=True)


# ============================================================
# FUNÇÕES PRINCIPAIS DE BACKEND
# ============================================================

def get_process_file_path(process_id: str) -> str:
    """
    Retorna o caminho completo do arquivo JSON do processo.
    """
    return os.path.join(PROCESS_DATA_DIR, f"{process_id}.json")


def save_process_data(process_id: str, data: Dict[str, Any]) -> None:
    """
    Salva o dicionário de dados do processo em formato JSON.
    """
    file_path = get_process_file_path(process_id)

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def load_process_data(process_id: str) -> Dict[str, Any]:
    """
    Carrega os dados do arquivo JSON do processo.
    Se o arquivo não existir, retorna {}.
    """
    file_path = get_process_file_path(process_id)

    if not os.path.exists(file_path):
        return {}

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    except Exception:
        return {}


def delete_process(process_id: str) -> bool:
    """
    Remove o arquivo JSON do processo.
    Retorna True se removido.
    """
    file_path = get_process_file_path(process_id)

    if os.path.exists(file_path):
        os.remove(file_path)
        return True

    return False


# ============================================================
# FUNÇÕES DE LISTAGEM
# ============================================================

def list_process_files() -> List[str]:
    """
    Retorna lista de nomes dos arquivos JSON na pasta /data.
    """
    try:
        return [
            f for f in os.listdir(PROCESS_DATA_DIR)
            if f.lower().endswith(".json")
        ]
    except Exception:
        return []


def list_processes() -> List[str]:
    """
    Função esperada pelo frontend.
    Retorna *somente os IDs* dos processos.
    Exemplo: ['a1b2c3d4', 'x9y8z7w6']
    """
    files = list_process_files()
    ids = [os.path.splitext(f)[0] for f in files]
    return sorted(ids)


# ============================================================
# DEPURAÇÃO OPCIONAL
# ============================================================

if __name__ == "__main__":
    print("Diretório de processos:", PROCESS_DATA_DIR)
    print("Processos encontrados:", list_processes())
