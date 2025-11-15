import os
import json
import pandas as pd
from datetime import date, datetime
from typing import Dict, Any

# --- Configuração de Pasta ---
DATA_FOLDER = "data"
os.makedirs(DATA_FOLDER, exist_ok=True) 

# --- Funções de Persistência JSON ---

def save_process_data(process_id: str, session_state_data: Dict[str, Any]):
    """
    Salva os dados do processo do Streamlit session_state em um arquivo JSON.
    Converte SETs para LISTAs e objetos DATE para STRING.
    """
    if not process_id:
        raise ValueError("ID do processo não pode ser vazio para salvar.")
        
    # Filtra chaves internas do Streamlit e chaves temporárias
    keys_to_exclude = ["process_to_load"] 
    # Exclui chaves internas do streamlit ('st.') e as de edição ('editing_')
    keys_to_exclude.extend([k for k in session_state_data.keys() if k.startswith(("editing_", "st."))] or [])
    # Exclui objetos de arquivo binário UploadedFile, que não podem ser serializados
    keys_to_exclude.extend([k for k in session_state_data.keys() if k.endswith("_obj")] or [])

    data_to_save = {k: v for k, v in session_state_data.items() 
                    if k not in keys_to_exclude}
    
    # 1. Trata objetos de arquivo em listas: remove o objeto binário 'imagem_obj' antes de salvar
    for lista_key in ['anexos', 'adendos', 'quesitos_autor', 'quesitos_reu']:
        if lista_key in data_to_save and isinstance(data_to_save[lista_key], list):
            for item in data_to_save[lista_key]:
                if isinstance(item, dict) and 'file_obj' in item:
                    item['file_obj'] = None # Remove o objeto UploadedFile
    
    # CORREÇÃO CRÍTICA 1: Converte o SET de 'etapas_concluidas' para LISTA antes de salvar no JSON
    if 'etapas_concluidas' in data_to_save and isinstance(data_to_save['etapas_concluidas'], set):
        data_to_save['etapas_concluidas'] = list(data_to_save['etapas_concluidas'])

    # 2. Converte objetos 'date' para string no formato DD/MM/AAAA para salvar no JSON
    for k, v in data_to_save.items():
        if isinstance(v, date):
            data_to_save[k] = v.strftime("%d/%m/%Y")
    
    # 3. Salva o JSON
    json_path = os.path.join(DATA_FOLDER, f"{process_id}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data_to_save, f, ensure_ascii=False, indent=4)

    return json_path

def load_process_data(process_id: str) -> Dict[str, Any]:
    """
    Carrega os dados de um processo a partir do JSON.
    Converte datas de string para objetos date e LISTA de etapas para SET.
    """
    json_path = os.path.join(DATA_FOLDER, f"{process_id}.json")
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"Arquivo JSON para o processo {process_id} não encontrado.")
    
    with open(json_path, "r", encoding="utf-8") as f:
        dados_carregados = json.load(f)
        
    # 1. Converte strings de data de volta para objetos date, se for o caso
    for key, value in dados_carregados.items():
        if key.startswith('data_') and isinstance(value, str):
            try:
                # Tenta formatar a data
                dados_carregados[key] = datetime.strptime(value, "%d/%m/%Y").date()
            except ValueError:
                pass 
        
    # CORREÇÃO CRÍTICA 2: Converte a LISTA de 'etapas_concluidas' de volta para um SET
    if 'etapas_concluidas' in dados_carregados and isinstance(dados_carregados['etapas_concluidas'], list):
        dados_carregados['etapas_concluidas'] = set(dados_carregados['etapas_concluidas'])
        
    return dados_carregados

# As demais funções que carregam e resumem dados (não vistas no log de erro) foram mantidas
# ou adicionadas para integridade, mas o foco das correções está em save_process_data e load_process_data.
def load_all_laudos_summary():
    """Carrega dados essenciais de todos os JSONs para exibição no Dashboard."""
    all_data = []
    # ... (implementação omitida para concisão, mas deve existir no seu arquivo original)
    return pd.DataFrame(all_data) if all_data else pd.DataFrame()