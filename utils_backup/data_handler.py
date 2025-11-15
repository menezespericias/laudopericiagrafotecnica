import streamlit as st
import json
import os
import pandas as pd
from datetime import date

DATA_FOLDER = "data"
os.makedirs(DATA_FOLDER, exist_ok=True) # Garante que a pasta 'data' existe

def load_all_laudos_summary():
    """Carrega dados essenciais de todos os JSONs para exibição no Dashboard."""
    all_data = []
    for filename in os.listdir(DATA_FOLDER):
        if filename.endswith(".json"):
            filepath = os.path.join(DATA_FOLDER, filename)
            with open(filepath, 'r', encoding='utf-8') as f:
                try:
                    data = json.load(f)
                    
                    # Extrai dados essenciais para o resumo
                    all_data.append({
                        "id_arquivo": filename,
                        "Nº Processo": data.get("NUMERO_PROCESSO", "N/A"),
                        "Comarca": data.get("COMARCA", "N/A"),
                        "Autor": data.get("AUTORES", "N/A"),
                        "Réu": data.get("REUS", "N/A"),
                        "Data Laudo": data.get("DATA_LAUDO", "N/A"),
                    })
                except json.JSONDecodeError:
                    st.error(f"Erro ao ler o arquivo JSON: {filename}")
    return pd.DataFrame(all_data)

def load_laudo_for_edit(filename):
    """Carrega um único laudo JSON e popula o session_state para edição."""
    filepath = os.path.join(DATA_FOLDER, filename)
    with open(filepath, 'r', encoding='utf-8') as f:
        data_to_edit = json.load(f)
        
    # Limpa o session_state e carrega todos os campos do JSON
    st.session_state.clear()
    
    # Recarrega os dados do JSON para o session_state
    for key, value in data_to_edit.items():
        # Trata datas que são strings no JSON, convertendo de volta para objeto date
        if key.startswith('data_'):
            try:
                st.session_state[key] = datetime.strptime(value, "%d/%m/%Y").date()
            except:
                st.session_state[key] = value # Mantém como string se falhar
        else:
            st.session_state[key] = value

    # Garante que o modo de edição esteja ligado
    st.session_state.editing_etapa_1 = True
    st.session_state.etapas_concluidas = set() # Força a re-salvar as etapas
    
    # Usa a função de navegação do Streamlit (necessária versão > 1.13.0)
    # st.switch_page("pages/01_Gerar_laudo.py") 
    # Como não podemos rodar switch_page aqui, a Home.py vai apenas carregar
    # e avisar o usuário para navegar.
    
    return True # Retorna sucesso