import streamlit as st
import os
import json
import shutil
import pandas as pd
from datetime import datetime
from db_handler import (
    init_db,
    listar_processos,
    inserir_processo,
    processo_existe,
    excluir_processo,
    atualizar_status # NOVO: Importa a função de atualização
)

# --- Configuração Inicial ---
st.set_page_config(page_title="Início", layout="wide")
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
                
                # 1. Insere o registro no Banco de Dados (SQLite)
                inserir_processo(novo_id, novo_autor, novo_reu, novo_status, atualizado_em)
                
                # 2. Cria o arquivo JSON inicial na pasta 'data'
                # NOTA: O arquivo JSON é apenas um cache de dados, a informação principal está no DB
                data_folder = "data"
                os.makedirs(data_folder, exist_ok=True)
                json_path = os.path.join(data_folder, f"{novo_id}.json")

                dados_iniciais = {
                    "numero_processo": novo_id,
                    "autor": novo_autor,
                    "reu": novo_reu,
                    "status_db": novo_status, # Armazena o status também no JSON (para referência)
                    "DATA_LAUDO": datetime.now().strftime("%d/%m/%Y")
                    # Outros campos iniciais podem ser adicionados aqui
                }
                
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(dados_iniciais, f, ensure_ascii=False, indent=4)
                
                st.success(f"Processo **{novo_id}** criado e salvo com sucesso!")
                st.rerun()

st.markdown("---")

# --- LISTAGEM DE PROCESSOS (Baseado no DB) ---

# 1. Busca todos os processos no banco de dados
try:
    todos_processos = listar_processos()
    # O resultado de listar_processos é uma lista de tuplas: (id, autor, reu, status, atualizado_em)
except Exception as e:
    st.error(f"Erro ao carregar processos do banco de dados: {e}")
    todos_processos = []

# 2. Filtragem de dados
PROCESSOS_ATIVOS = ['Em andamento', 'Laudo Preliminar']
PROCESSOS_ARQUIVADOS = ['Arquivado', 'Concluído']

# status está no índice [3]
processos_ativos = [p for p in todos_processos if p[3] in PROCESSOS_ATIVOS]
processos_arquivados = [p for p in todos_processos if p[3] in PROCESSOS_ARQUIVADOS]

# --- Processos Ativos ---
st.header("Processos Ativos")

if processos_ativos:
    # Cria um DataFrame para exibir a lista em formato de tabela
    df_ativos = pd.DataFrame(processos_ativos, columns=['id', 'autor', 'reu', 'status', 'atualizado_em'])

    # Exibe a tabela (opcional, pode ser substituído pela lista abaixo)
    st.dataframe(df_ativos, hide_index=True, use_container_width=True)

    # Lista detalhada para botões de ação
    for index, row in df_ativos.iterrows():
        processo_id = row['id']
        
        # Cria um container para cada item com botões
        with st.container(border=True):
            col1, col2, col3 = st.columns([5, 2, 2])
            
            with col1:
                st.markdown(f"**Nº:** `{processo_id}`")
                st.markdown(f"**Partes:** {row['autor']} x {row['reu']}")
                st.caption(f"Status: **{row['status']}** | Última atualização: {row['atualizado_em']}")

            with col2:
                # Botão para continuar a edição
                if st.button("✏️ Continuar Edição", key=f"continuar_{processo_id}", type="primary"):
                    st.session_state["process_to_load"] = processo_id
                    # Redireciona para a página de edição
                    st.switch_page("pages/01_Gerar_laudo.py")

            with col3:
                # Botão para arquivar
                if st.button("📁 Arquivar", key=f"arquivar_{processo_id}"):
                    # Atualiza o status no DB para 'Arquivado'
                    atualizar_status(processo_id, 'Arquivado')
                    st.success(f"Processo {processo_id} arquivado.")
                    st.rerun()
else:
    st.info("Nenhum processo ativo encontrado no momento.")

st.markdown("---")

# --- Processos Arquivados ---
st.header("Processos Arquivados")

if processos_arquivados:
    with st.expander(f"Mostrar {len(processos_arquivados)} Processos Arquivados"):
        # Cria um DataFrame para exibir a lista
        df_arquivados = pd.DataFrame(processos_arquivados, columns=['id', 'autor', 'reu', 'status', 'atualizado_em'])
        st.dataframe(df_arquivados, hide_index=True, use_container_width=True)
        
        for index, row in df_arquivados.iterrows():
            processo_id = row['id']
            
            with st.container(border=True):
                col1, col2, col3 = st.columns([5, 2, 2])
                
                with col1:
                    st.markdown(f"**Nº:** `{processo_id}`")
                    st.markdown(f"**Partes:** {row['autor']} x {row['reu']}")
                    st.caption(f"Status: **{row['status']}** | Arquivado em: {row['atualizado_em']}")
                
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
                        json_path = os.path.join("data", f"{processo_id}.json")
                        if os.path.exists(json_path):
                            os.remove(json_path)
                        st.success(f"Processo {processo_id} excluído permanentemente.")
                        st.rerun()

else:
    st.info("Nenhum processo arquivado encontrado.")