import os
import json
from datetime import date, datetime
from typing import Dict, Any

# --- Configuração de Pasta ---
DATA_FOLDER = "data"
# Garante que a pasta 'data' existe (necessário se este arquivo for importado antes de home.py)
os.makedirs(DATA_FOLDER, exist_ok=True) 

# --- Funções de Persistência JSON ---

def save_process_data(process_id: str, session_state_data: Dict[str, Any]):
    """
    Salva os dados do processo do Streamlit session_state em um arquivo JSON.
    Recebe o dicionário st.session_state, filtra chaves internas e serializa objetos.
    """
    if not process_id:
        raise ValueError("ID do processo não pode ser vazio para salvar.")
        
    # Filtra chaves internas do Streamlit e chaves temporárias
    # O set() é necessário para evitar salvar o session_state inteiro (incluindo objetos complexos)
    keys_to_exclude = ["process_to_load", "etapas_concluidas"] 
    keys_to_exclude.extend([k for k in session_state_data.keys() if k.startswith("editing_")])

    data_to_save = {k: v for k, v in session_state_data.items() 
                    if k not in keys_to_exclude}
    
    # 1. Trata objetos de arquivo (UploadedFile) em listas: remove o objeto binário 'imagem_obj' antes de salvar
    for lista_key in ["anexos", "adendos", "quesitos_autor", "quesitos_reu"]:
        if lista_key in data_to_save and isinstance(data_to_save[lista_key], list):
            # Cria uma cópia da lista com o campo 'imagem_obj' removido
            data_to_save[lista_key] = [{k: v for k, v in item.items() if k != 'imagem_obj'} 
                                       for item in data_to_save[lista_key]]

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
    Retorna o dicionário de dados, convertendo datas de string para objetos date.
    """
    json_path = os.path.join(DATA_FOLDER, f"{process_id}.json")
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"Arquivo JSON para o processo {process_id} não encontrado.")
    
    with open(json_path, "r", encoding="utf-8") as f:
        dados_carregados = json.load(f)
        
    # 1. Converte strings de data de volta para objetos date, se for o caso
    for key, value in dados_carregados.items():
        if key.startswith('DATA_') and isinstance(value, str):
            try:
                # O formato esperado é DD/MM/AAAA (como foi salvo)
                dados_carregados[key] = datetime.strptime(value, "%d/%m/%Y").date()
            except ValueError:
                pass # Mantém como string se a conversão falhar
                
    return dados_carregados