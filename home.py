import streamlit as st
import os
import json
import shutil
import pandas as pd
from datetime import datetime
# NOVO: Ajuste a importação para a nova estrutura de pastas 'src'
from src.db_handler import (
    init_db,
    listar_processos,
    inserir_processo,
    processo_existe,
    excluir_processo,
    atualizar_status
)

# --- Configuração Inicial ---
st.set_page_config(page_title="Início", layout="wide")

# CORREÇÃO CRÍTICA DO PATH: Garante o caminho absoluto para as pastas de dados
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = SCRIPT_DIR # home.py está na raiz, então o root é a própria pasta
DATA_FOLDER = os.path.join(PROJECT_ROOT, "data")
os.makedirs(DATA_FOLDER, exist_ok=True) 

init_db() # Garante que o banco de dados está inicializado

st.title("Bem-vindo ao Gerador de Laudos")
st.write("Selecione 'Gerar Laudo' no menu lateral ou use a tela abaixo para gerenciar processos.")

# --- Formulário para adicionar novo processo ---
with st.expander("➕ Adicionar Novo Processo"):
    with st.form("novo_processo_form"):
        novo_id = st.text_input("Número do Processo (Ex: 0001234-56.2023.8.26.0001)")
        novo_autor = st.text_input("Autor(a)")
        novo_reu = st.text_input("Réu")
        # Por padrão, novo processo começa 'Em andamento'
        novo_status = st.selectbox("Status Inicial", ["Em andamento", "Laudo Preliminar"]) 
        submitted = st.form_submit_button("Salvar Novo Processo")

        if submitted:
            if not novo_id or not novo_autor or not novo_reu:
                st.error("Preencha todos os campos obrigatórios.")
            elif processo_existe(novo_id):
                st.warning("Este número de processo já está cadastrado.")
            else:
                atualizado_em = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                try:
                    inserir_processo(novo_id, novo_autor, novo_reu, novo_status, atualizado_em)
                    st.success(f"✅ Processo **{novo_id}** cadastrado com sucesso!")
                    # Cria o arquivo JSON básico para evitar erro de arquivo não encontrado
                    json_path = os.path.join(DATA_FOLDER, f"{novo_id}.json")
                    with open(json_path, "w", encoding="utf-8") as f:
                        json.dump({
                            "NUMERO_PROCESSO": novo_id,
                            "AUTORES": novo_autor,
                            "REUS": novo_reu,
                            "status": novo_status,
                            "atualizado_em": atualizado_em,
                            "etapas_concluidas": list() # Inicializa como lista para salvar corretamente no JSON
                        }, f)
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Erro ao salvar no banco de dados: {e}")

st.markdown("---")

# --- Processos Ativos (Lidos do DB) ---
st.header("Processos Ativos")
# Filtrar apenas processos que não estão 'Arquivado' para mostrar aqui
processos_ativos_db = [
    p for p in listar_processos() 
    if p[3] != 'Arquivado' and p[3] != 'Concluído'
]

if processos_ativos_db:
    # Cria um DataFrame para facilitar a visualização
    df_processos = pd.DataFrame(processos_ativos_db, columns=["id", "autor", "reu", "status", "atualizado_em"])

    for index, row in df_processos.iterrows():
        processo_id = row['id']
        
        with st.container(border=True):
            col1, col2, col3, col4 = st.columns([4, 2, 2, 2])
            
            with col1:
                st.markdown(f"**Nº:** `{processo_id}`")
                st.markdown(f"**Partes:** {row['autor']} x {row['reu']}")
                st.caption(f"Status: **{row['status']}** | Última Atualização: {row['atualizado_em']}")
            
            with col2:
                # Botão para EDITAR/CARREGAR
                if st.button("▶️ Carregar para Edição", key=f"editar_{processo_id}", type="primary"):
                    # Define a variável de estado para a outra página carregar
                    st.session_state["process_to_load"] = processo_id
                    st.switch_page("pages/01_Gerar_laudo.py")
            
            with col3:
                # Botão para ARQUIVAR (muda o status no DB)
                if st.button("📁 Arquivar", key=f"arquivar_{processo_id}", type="secondary"):
                    atualizar_status(processo_id, 'Arquivado')
                    st.success(f"Processo {processo_id} arquivado. Consulte em 'Processos Finalizados'.")
                    st.rerun()

            with col4:
                # Botão para CONCLUIR (muda o status no DB, diferente de arquivar)
                if st.button("✔️ Concluído", key=f"concluir_{processo_id}"):
                    atualizar_status(processo_id, 'Concluído')
                    st.success(f"Processo {processo_id} marcado como Concluído.")
                    st.rerun()
else:
    st.info("Nenhum processo ativo encontrado. Adicione um novo processo acima.")

st.markdown("---")

# --- Processos Finalizados (Arquivados e Concluídos) ---
st.header("Processos Finalizados")

processos_finalizados_db = [
    p for p in listar_processos() 
    if p[3] == 'Arquivado' or p[3] == 'Concluído'
]

if processos_finalizados_db:
    df_finalizados = pd.DataFrame(processos_finalizados_db, columns=["id", "autor", "reu", "status", "atualizado_em"])
    
    with st.expander("Mostrar Processos Finalizados"):
        for index, row in df_finalizados.iterrows():
            processo_id = row['id']
            
            with st.container(border=True):
                col1, col2, col3 = st.columns([6, 2, 2])
                
                with col1:
                    st.markdown(f"**Nº:** `{processo_id}`")
                    st.markdown(f"**Partes:** {row['autor']} x {row['reu']}")
                    st.caption(f"Status: **{row['status']}** | Finalizado em: {row['atualizado_em']}")
                
                with col2:
                    if st.button("📂 Desarquivar", key=f"desarquivar_{processo_id}", type="secondary"):
                        # Atualiza o status no DB para 'Em andamento'
                        atualizar_status(processo_id, 'Em andamento')
                        st.success(f"Processo {processo_id} desarquivado e movido para Processos Ativos.")
                        st.rerun()
                
                with col3:
                    if st.button("🗑️ Excluir", key=f"excluir_{processo_id}"):
                        # Exclui do DB
                        excluir_processo(processo_id)
                        # Remove o arquivo JSON também
                        json_path = os.path.join(DATA_FOLDER, f"{processo_id}.json")
                        if os.path.exists(json_path):
                            os.remove(json_path)
                        st.success(f"Processo {processo_id} excluído permanentemente.")
                        st.rerun()
else:
    st.info("Nenhum processo finalizado ou arquivado encontrado.")