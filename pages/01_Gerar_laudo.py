# pages/01_Gerar_laudo.py (O MÓDULO INTEGRADO/CONTROLADOR DE FLUXO)

import streamlit as st
import os
import json
from datetime import date, datetime
from num2words import num2words
from typing import Dict, Any, Set, List
import pandas as pd
import matplotlib.pyplot as plt
import io
import base64

# Importações dos módulos de interface (AS SALAS DO EDIFÍCIO)
import app.module_01_apresentacao as m01
import app.module_04_documentos as m04 
import app.module_05_analise as m05 
import app.module_06_conclusao as m06
import app.module_07_quesitos as m07
import app.module_08_encerramento as m08 # NOVO MÓDULO (BLOCO 8 - Etapa 8)

# Importações dos módulos de backend
try:
    from data_handler import save_process_data, load_process_data
    from db_handler import atualizar_status
    # A função gerar_laudo será importada condicionalmente dentro do m08
except ImportError:
    # Implementação de placeholders para evitar crashs
    def save_process_data(*args, **kwargs): return True
    def load_process_data(*args, **kwargs): return {}
    def atualizar_status(*args, **kwargs): pass
    
# --- Configurações de Ambiente (Paths Absolutos) ---
st.set_page_config(page_title="Laudo Grafotécnico", layout="wide")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.join(SCRIPT_DIR, '..')
# Ajuste o caminho para o modelo DOCX
CAMINHO_MODELO = os.path.join(PROJECT_ROOT, "template", "LAUDO PERICIAL GRAFOTÉCNICO.docx") 
OUTPUT_FOLDER = os.path.join(PROJECT_ROOT, "output")
DATA_FOLDER = os.path.join(PROJECT_ROOT, "data")
os.makedirs(DATA_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# --- Funções de Controle de Estado ---

def init_session_state():
    """Inicializa chaves essenciais e corrige o tipo de dados após o carregamento."""
    
    # Garante que 'process_loaded' exista
    if 'process_loaded' not in st.session_state:
        st.session_state.process_loaded = False
        
    # CRÍTICO: 'etapas_concluidas' deve ser um SET
    if 'etapas_concluidas' not in st.session_state:
        st.session_state.etapas_concluidas = set()
    # Corrige o erro de serialização do JSON (AttributeError: 'list' object has no attribute 'add')
    elif isinstance(st.session_state.etapas_concluidas, list):
        st.session_state.etapas_concluidas = set(st.session_state.etapas_concluidas)

    # Variáveis Principais (M01)
    if 'numero_processo' not in st.session_state:
        st.session_state.numero_processo = ""
    if 'AUTOR' not in st.session_state:
        st.session_state.AUTOR = ""
    if 'REU' not in st.session_state:
        st.session_state.REU = ""
        
    # Listas de Conteúdo (Gerais)
    if 'anexos' not in st.session_state:
        st.session_state.anexos = []
    if 'adendos' not in st.session_state:
        st.session_state.adendos = []
        
    # Módulo 4
    if 'questionados_list' not in st.session_state:
        st.session_state.questionados_list = []
    if 'padroes_pce_list' not in st.session_state:
        st.session_state.padroes_pce_list = []
        
    # Módulo 5
    if 'analises_eog_list' not in st.session_state:
        st.session_state.analises_eog_list = []
        
    # Módulo 6
    if 'BLOCO_CONCLUSAO_DINAMICO' not in st.session_state:
        st.session_state.BLOCO_CONCLUSAO_DINAMICO = ""
        
    # Módulo 7
    if 'quesitos_autora_data' not in st.session_state:
        st.session_state.quesitos_autora_data = {"list": [], "nao_enviados": False}
    if 'quesitos_reu_data' not in st.session_state:
        st.session_state.quesitos_reu_data = {"list": [], "nao_enviados": False}
    if 'BLOCO_QUESITOS_AUTOR' not in st.session_state:
        st.session_state.BLOCO_QUESITOS_AUTOR = ""
    if 'BLOCO_QUESITOS_REU' not in st.session_state:
        st.session_state.BLOCO_QUESITOS_REU = ""
        
    # Módulo 8 
    if 'COMARCA' not in st.session_state:
        st.session_state.COMARCA = ""
    if 'DATA_LAUDO' not in st.session_state:
        st.session_state.DATA_LAUDO = datetime.now().date() # Inicializa com objeto date
    if 'anexos_manuais' not in st.session_state:
        st.session_state.anexos_manuais = []
        
    # Adiciona o caminho do modelo ao state para acesso no m08
    st.session_state.CAMINHO_MODELO = CAMINHO_MODELO 

# Chamada inicial
init_session_state()

# --- Funções de I/O ---

def load_process(process_id: str):
    """Tenta carregar os dados do JSON para o session_state."""
    try:
        dados_carregados = load_process_data(process_id)
        # Transfere os dados carregados para st.session_state
        for k, v in dados_carregados.items():
            st.session_state[k] = v
            
        st.session_state.process_loaded = True
        st.session_state.numero_processo = process_id
        
        # Chama init_session_state novamente para garantir que as correções de tipo (list->set) sejam aplicadas
        init_session_state() 
        
        st.success(f"Processo **{process_id}** carregado com sucesso! Etapas concluídas: {len(st.session_state.etapas_concluidas)}")
        st.rerun() # Recarrega para refletir o novo estado de carregamento

    except FileNotFoundError:
        st.error(f"❌ Não há dados salvos para o processo **{process_id}**.")
    except Exception as e:
        st.error(f"❌ Erro ao carregar dados: {e}")
        
def save_current_state():
    """Função wrapper para salvar o estado atual do Streamlit."""
    if not st.session_state.get('numero_processo'):
        st.error("Erro: Número do processo não definido para salvar.")
        return False
        
    try:
        # Tenta converter a data de volta para string antes de salvar no JSON
        if 'DATA_LAUDO' in st.session_state and isinstance(st.session_state.DATA_LAUDO, date):
            # Temporariamente converte para string para o JSON e salva
            original_data_laudo = st.session_state.DATA_LAUDO
            st.session_state.DATA_LAUDO = original_data_laudo.strftime("%Y-%m-%d") 

            # Chama a função de salvar
            save_process_data(st.session_state.numero_processo, st.session_state)
            
            # Restaura o objeto date para uso posterior no Streamlit
            st.session_state.DATA_LAUDO = original_data_laudo 
            
        else:
             save_process_data(st.session_state.numero_processo, st.session_state)
             
        return True
    except Exception as e:
        st.error(f"❌ Erro ao salvar o estado do processo: {e}")
        return False

# --- Dashboard (A Recepção) ---

st.title("Geração de Laudo Grafotécnico")
st.write("Selecione um processo ativo para continuar a geração do laudo, bloco a bloco.")

# 1. Seleção e Carregamento de Processo
with st.expander("📂 Carregar Processo Existente", expanded=not st.session_state.process_loaded):
    col1, col2 = st.columns([3, 1])
    process_id_to_load = col1.text_input("Número do Processo a Carregar", key="process_to_load_input")
    
    if col2.button("Carregar Dados", use_container_width=True, type="primary"):
        if process_id_to_load:
            load_process(process_id_to_load)
        else:
            st.warning("Insira um número de processo válido.")

st.markdown("---")

# 2. Área de Trabalho Modular (Fluxo)
if st.session_state.process_loaded:
    st.header(f"Processo Atual: `{st.session_state.numero_processo}`")
    st.caption(f"Autor: {st.session_state.get('AUTOR', 'N/A')} | Réu: {st.session_state.get('REU', 'N/A')}")
    st.markdown("---")
    
    # AQUI ENTRA A CHAMADA SEQUENCIAL DOS MÓDULOS (AS SALAS DO EDIFÍCIO)
    
    # MÓDULO 1: APRESENTAÇÃO, OBJETIVOS e INTRODUÇÃO (Blocos 1, 2 e 3) - Etapas 1, 2, 3
    m01.render_module(st.session_state, save_current_state) 
    
    # MÓDULO 4: DOCUMENTOS SUBMETIDOS (Bloco 4 - Etapa 4)
    if 3 in st.session_state.etapas_concluidas:
         m04.render_module(st.session_state, save_current_state)
    else:
         st.info("Complete as informações dos Blocos 1, 2 e 3 antes de prosseguir para a Etapa 4.")
         
    # MÓDULO 5: EXAMES PERICIAIS E METODOLOGIA (Bloco 5 - Etapa 5)
    if 4 in st.session_state.etapas_concluidas:
        m05.render_module(st.session_state, save_current_state)
    elif 3 in st.session_state.etapas_concluidas:
        st.info("Complete a Etapa 4 (Documentos Submetidos) antes de iniciar a Análise Pericial (Etapa 5).")

    # MÓDULO 6: CONCLUSÃO (Bloco 6 - Etapa 6)
    if 5 in st.session_state.etapas_concluidas:
        m06.render_module(st.session_state, save_current_state)
    elif 4 in st.session_state.etapas_concluidas:
         st.info("Complete a Etapa 5 (Exames Periciais) antes de gerar a Conclusão (Etapa 6).")
         
    # MÓDULO 7: RESPOSTA AOS QUESITOS (Bloco 7 - Etapa 7)
    if 6 in st.session_state.etapas_concluidas:
        m07.render_module(st.session_state, save_current_state)
    elif 5 in st.session_state.etapas_concluidas:
         st.info("Complete a Etapa 6 (Conclusão) antes de responder aos Quesitos (Etapa 7).")

    # MÓDULO 8: ENCERRAMENTO (Bloco 8 - Etapa 8)
    if 7 in st.session_state.etapas_concluidas:
        # Passa o caminho da raiz do projeto para o m08
        m08.render_module(st.session_state, save_current_state, PROJECT_ROOT) 
    elif 6 in st.session_state.etapas_concluidas:
         st.info("Complete a Etapa 7 (Respostas aos Quesitos) antes de finalizar e gerar o Laudo (Etapa 8).")
    
    st.markdown("---")
    
    # 3. Área de Geração Final (Mensagens de Status)
    if 8 in st.session_state.etapas_concluidas: 
        st.success("🎉 Geração do Laudo Final (Etapa 8) concluída. O laudo está pronto para download (veja no bloco 8).")
    elif 7 in st.session_state.etapas_concluidas:
        st.info("O Laudo está pronto para ser gerado. Preencha os detalhes finais na Etapa 8 (Encerramento) e clique em 'Gerar Laudo Final (.DOCX)'.")
        
else:
    st.info("Carregue um processo para iniciar a geração do laudo.")