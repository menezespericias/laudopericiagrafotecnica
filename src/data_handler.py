import os
import json
from datetime import date, datetime
from typing import Dict, Any, Set, List

# --- Configuração de Pasta ---
DATA_FOLDER = "data"
# Garante que a pasta 'data' existe
os.makedirs(DATA_FOLDER, exist_ok=True) 

# --- Funções de Persistência JSON ---

def save_process_data(process_id: str, session_state_data: Dict[str, Any]) -> str:
    """
    Salva os dados do processo do Streamlit session_state em um arquivo JSON.
    Filtra chaves internas do Streamlit e serializa objetos complexos.
    """
    if not process_id:
        raise ValueError("ID do processo não pode ser vazio para salvar.")
        
    # 1. Filtra chaves internas e temporárias (Ex: process_to_load, editing_X)
    keys_to_exclude = ["process_to_load"] 
    keys_to_exclude.extend([k for k in session_state_data.keys() if k.startswith(("editing_", "form_"))])

    # Cria uma cópia dos dados filtrados para manipulação
    data_to_save = {k: v for k, v in session_state_data.items() 
                    if k not in keys_to_exclude}
    
    # 2. CORREÇÃO CRÍTICA (Set -> List): Trata o 'set' de etapas_concluidas
    # JSON não aceita 'set', converte para 'list' antes de salvar.
    if "etapas_concluidas" in data_to_save and isinstance(data_to_save["etapas_concluidas"], set):
        data_to_save["etapas_concluidas"] = list(data_to_save["etapas_concluidas"])
    
    # 3. Converte objetos 'date' para string no formato DD/MM/AAAA para salvar no JSON
    for k, v in data_to_save.items():
        if isinstance(v, date):
            data_to_save[k] = v.strftime("%d/%m/%Y")
        
        # 4. Trata objetos de arquivo (UploadedFile) em listas: remove o objeto binário 'imagem_obj'
        if isinstance(v, list):
            for item in v:
                if isinstance(item, dict) and "imagem_obj" in item:
                    # Remove o objeto binário da memória para não inchar o JSON
                    item.pop("imagem_obj", None)
    
    # 5. Salva o JSON
    json_path = os.path.join(DATA_FOLDER, f"{process_id}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data_to_save, f, ensure_ascii=False, indent=4)

    return json_path

def load_process_data(process_id: str) -> Dict[str, Any]:
    """
    Carrega os dados de um processo a partir do JSON.
    Retorna o dicionário de dados, convertendo listas de volta para 'set' e strings para 'date'.
    """
    json_path = os.path.join(DATA_FOLDER, f"{process_id}.json")
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"Arquivo JSON para o processo {process_id} não encontrado.")
    
    with open(json_path, "r", encoding="utf-8") as f:
        dados_carregados = json.load(f)
        
    # 1. CORREÇÃO CRÍTICA (List -> Set): Converte a lista de etapas_concluidas de volta para 'set'
    if "etapas_concluidas" in dados_carregados and isinstance(dados_carregados["etapas_concluidas"], list):
        dados_carregados["etapas_concluidas"] = set(dados_carregados["etapas_concluidas"])
        
    # 2. Converte strings de data de volta para objetos date, se for o caso
    for key, value in dados_carregados.items():
        if isinstance(value, str) and (key.startswith('data_') or key.endswith('_DATA')):
            try:
                # O formato esperado é DD/MM/AAAA
                dados_carregados[key] = datetime.strptime(value, "%d/%m/%Y").date()
            except ValueError:
                # Se falhar, mantém como string
                pass 
                
    return dados_carregados