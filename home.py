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
    atualizar_status
) # Adicionando a função atualizar_status, se existir no db_handler. Se não existir, precisaremos dela.

# --- Configuração Inicial ---
st.set_page_config(page_title="Início", layout="wide")
init_db()

DATA_FOLDER = "data"
ARQUIVADOS_FOLDER = os.path.join(DATA_FOLDER, "arquivados")
os.makedirs(DATA_FOLDER, exist_ok=True)
os.makedirs(ARQUIVADOS_FOLDER, exist_ok=True)

st.title("🏠 Gerenciamento de Laudos Periciais")
st.write("Crie novos processos ou continue a edição dos processos existentes.")

# --- Formulário para adicionar novo processo ---
with st.expander("➕ Adicionar Novo Processo", expanded=True):
    with st.form("novo_processo_form"):
        col_id, col_partes = st.columns([1, 2])
        
        with col_id:
            novo_id = st.text_input("Número do Processo", key="novo_id_input")
            novo_status = st.selectbox("Status Inicial", ["Em andamento", "Laudo Preliminar", "Concluído"])
        
        with col_partes:
            novo_autor = st.text_area("Autor(a) (Um por linha, se múltiplos)", height=50)
            novo_reu = st.text_area("Réu (Um por linha, se múltiplos)", height=50)
        
        submitted = st.form_submit_button("Salvar e Iniciar Edição", type="primary")

        if submitted:
            # Normalização e validação
            novo_id_limpo = novo_id.strip()
            
            if not novo_id_limpo or not novo_autor.strip() or not novo_reu.strip():
                st.error("Preencha todos os campos obrigatórios (Número do Processo, Autor e Réu).")
            elif processo_existe(novo_id_limpo):
                st.warning("Este número de processo já está cadastrado.")
            else:
                try:
                    # 1. Salva no SQLite
                    atualizado_em = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    inserir_processo(novo_id_limpo, novo_autor.strip(), novo_reu.strip(), novo_status, atualizado_em)
                    
                    # 2. Inicializa o arquivo JSON (Base de Dados do Laudo)
                    dados_iniciais = {
                        "numero_processo": novo_id_limpo,
                        "autor": novo_autor.strip(),
                        "reu": novo_reu.strip(),
                        "status_db": novo_status,
                        "DATA_LAUDO": datetime.now().strftime("%d/%m/%Y"),
                        "atualizado_em": atualizado_em
                    }
                    json_path = os.path.join(DATA_FOLDER, f"{novo_id_limpo}.json")
                    with open(json_path, "w", encoding="utf-8") as f:
                        json.dump(dados_iniciais, f, ensure_ascii=False, indent=4)
                        
                    st.success(f"Processo **{novo_id_limpo}** cadastrado com sucesso! Redirecionando...")
                    
                    # 3. Redireciona para edição
                    st.session_state["process_to_load"] = novo_id_limpo
                    st.switch_page("pages/01_Gerar_laudo.py")
                
                except Exception as e:
                    st.error(f"Erro ao salvar o processo: {e}")

st.markdown("---")

# --- Processos Ativos ---
st.header("📋 Processos Ativos")

# Tabela de processos ativos do SQLite
processos_db = listar_processos()

# Filtra apenas os processos que não estão arquivados
processos_ativos_db = [p for p in processos_db if p[3] != 'Arquivado'] 

if processos_ativos_db:
    # Formata os dados para exibição e ações
    data_for_display = []
    
    # Mapeia os dados (id, autor, reu, status, atualizado_em)
    for processo in processos_ativos_db:
        processo_id = processo[0]
        
        # Cria um link direto para o JSON
        json_path = os.path.join(DATA_FOLDER, f"{processo_id}.json")
        
        if os.path.exists(json_path):
            
            # Carrega o JSON para pegar as informações mais detalhadas ou status
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    dados_json = json.load(f)
            except json.JSONDecodeError:
                dados_json = {} # Em caso de erro, usa dados básicos
            
            # Ação de Editar (coloca na primeira coluna para visibilidade)
            editar_button = f'<button onClick="window.location.href=\'{st.get_page_link("pages/01_Gerar_laudo.py")}?load={processo_id}\'">✏️ Editar</button>'
            
            # Note: St.switch_page não funciona dentro de st.dataframe com HTML/CSS puro,
            # então usaremos botões fora do dataframe ou uma abordagem diferente.

            data_for_display.append({
                "ID": processo_id,
                "Autor": processo[1].split('\n')[0] + ('...' if '\n' in processo[1] else ''),
                "Réu": processo[2].split('\n')[0] + ('...' if '\n' in processo[2] else ''),
                "Status": processo[3],
                "Última Atualização": datetime.strptime(processo[4], "%Y-%m-%d %H:%M:%S").strftime("%d/%m/%Y %H:%M"),
                "Ações": processo_id # Usaremos a coluna ID para criar os botões
            })

    # Cria o DataFrame para exibição (sem a coluna de Ações)
    df_display = pd.DataFrame(data_for_display).drop(columns=['Ações'])
    
    st.dataframe(df_display, use_container_width=True, hide_index=True)
    
    st.markdown("### Ações Rápidas")
    
    # Cria os botões de ação para cada processo (melhor abordagem no Streamlit)
    for processo in data_for_display:
        processo_id = processo["ID"]
        
        col1, col2, col3, col4 = st.columns([1, 1, 1, 10])
        
        json_path = os.path.join(DATA_FOLDER, f"{processo_id}.json")

        with col1:
            if st.button("✏️ Continuar Edição", key=f"editar_{processo_id}"):
                st.session_state["process_to_load"] = processo_id
                st.switch_page("pages/01_Gerar_laudo.py")
        
        with col2:
            if st.button("📁 Arquivar", key=f"arquivar_{processo_id}"):
                
                # 1. Move o arquivo JSON
                if os.path.exists(json_path):
                    shutil.move(json_path, os.path.join(ARQUIVADOS_FOLDER, f"{processo_id}.json"))
                
                # 2. Atualiza o status no SQLite (usando a função de db_handler)
                atualizar_status(processo_id, "Arquivado") # É necessário implementar esta função em db_handler.py
                
                st.success(f"Processo **{processo_id}** arquivado.")
                st.rerun()
                
        with col3:
            if st.button("🗑️ Excluir", key=f"excluir_{processo_id}"):
                # 1. Exclui do SQLite
                excluir_processo(processo_id)
                
                # 2. Exclui o arquivo JSON
                if os.path.exists(json_path):
                    os.remove(json_path)
                
                st.error(f"Processo **{processo_id}** permanentemente excluído.")
                st.rerun()

else:
    st.info("Nenhum processo ativo encontrado. Use o formulário acima para adicionar um novo.")

st.markdown("---")

# --- Processos Arquivados ---
st.header("📦 Processos Arquivados")

arquivados = [f for f in os.listdir(ARQUIVADOS_FOLDER) if f.endswith(".json")]

if arquivados:
    with st.expander("Mostrar Processos Arquivados"):
        for arquivo in sorted(arquivados, reverse=True): # Mostra os mais recentes primeiro
            processo_id = arquivo.replace(".json", "")
            caminho = os.path.join(ARQUIVADOS_FOLDER, arquivo)
            
            try:
                with open(caminho, "r", encoding="utf-8") as f:
                    dados = json.load(f)
            except json.JSONDecodeError:
                dados = {"autor": "N/A", "reu": "N/A"}
            
            partes = f"**Autor:** {dados.get('autor', 'N/A').split('\n')[0]} | **Réu:** {dados.get('reu', 'N/A').split('\n')[0]}"
            
            st.markdown(f"**Processo Arquivado:** {processo_id} ({partes})")
            
            col_a1, col_a2, col_a3 = st.columns([1, 1, 10])
            
            with col_a1:
                # 1. Botão Desarquivar
                if st.button("↩️ Desarquivar", key=f"desarquivar_{processo_id}"):
                    # Move o arquivo JSON de volta
                    shutil.move(caminho, os.path.join(DATA_FOLDER, arquivo))
                    
                    # Atualiza o status no SQLite
                    atualizar_status(processo_id, "Em andamento") # Assume 'Em andamento'
                    
                    st.success(f"Processo **{processo_id}** desarquivado e movido para Ativos.")
                    st.rerun()
            
            with col_a2:
                # 2. Botão Excluir (permanente)
                if st.button("🗑️ Excluir (Permanente)", key=f"excluir_arq_{processo_id}"):
                    # Exclui o registro do DB
                    excluir_processo(processo_id) 
                    
                    # Exclui o arquivo JSON
                    os.remove(caminho) 
                    
                    st.error(f"Processo **{processo_id}** excluído permanentemente.")
                    st.rerun()
                    
            st.markdown("---")
else:
    st.info("Nenhum processo foi arquivado ainda.")