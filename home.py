import streamlit as st
import os
import json
import shutil
from datetime import datetime
from word_handler import carregar_indice_processos

with st.expander("📄 Índice de Processos (Google Sheets)", expanded=False):
    indice = carregar_indice_processos()
    if indice:
        st.dataframe(indice, use_container_width=True)
    else:
        st.warning("Não foi possível carregar o índice de processos.")

# --- Configuração Inicial ---
st.set_page_config(page_title="Início", layout="wide")
st.title("Bem-vindo ao Gerador de Laudos")
st.write("Selecione 'Gerar Laudo' no menu lateral.")
with st.expander("📄 Índice de Processos (Google Sheets)", expanded=False):
    indice = carregar_indice_processos()
    if indice:
        st.dataframe(indice, use_container_width=True)
    else:
        st.warning("Não foi possível carregar o índice de processos.")

DATA_FOLDER = "data"
ARCHIVED_FOLDER = os.path.join(DATA_FOLDER, "arquivados")

# --- Funções de Gestão de Processos ---

def load_process_list(source_folder=DATA_FOLDER):
    """Carrega a lista de processos de uma pasta (principal ou arquivada)."""
    if not os.path.exists(source_folder):
        return []
    
    process_list = []
    
    # Busca por arquivos .json
    files_to_check = [f for f in os.listdir(source_folder) if f.endswith(".json")]
    
    for filename in files_to_check:
        filepath = os.path.join(source_folder, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                # --- Lógica de TAGS FALTANTES ---
                missing = []
                # Etapa 1 (Chaves essenciais)
                if not data.get("numero_processo"): missing.append("Nº Processo")
                if not data.get("autor_0"): missing.append("Autor")
                if not data.get("reu_0"): missing.append("Réu")
                if "Apresentação" not in data.get("etapas_concluidas", []): missing.append("Etapa 1")
                # Etapa 4
                if not data.get("doc_padrao"): missing.append("Docs. Padrão")
                if not data.get("documentos_questionados_list") or not all(d.get("TIPO_DOCUMENTO") for d in data.get("documentos_questionados_list", [])):
                    missing.append("Docs. Questionados")
                    
                
                process_list.append({
                    "id": filename.replace(".json", ""),
                    "nome": f"{data.get('autor_0', 'AUTOR')} x {data.get('reu_0', 'RÉU')}",
                    "tags": ", ".join(missing),
                    "status_etapa": f"{len(data.get('etapas_concluidas', []))}/10 concluídas",
                    "path": filepath,
                })
        except Exception:
            process_list.append({
                "id": filename.replace(".json", ""),
                "nome": "Erro ao carregar (JSON inválido)",
                "tags": "JSON INVÁLIDO",
                "status_etapa": "N/A",
                "path": filepath,
            })

    return process_list

def archive_process(process_id):
    """Move o arquivo JSON para a pasta de arquivados."""
    source_path = os.path.join(DATA_FOLDER, f"{process_id}.json")
    target_path = os.path.join(ARCHIVED_FOLDER, f"{process_id}.json")
    
    os.makedirs(ARCHIVED_FOLDER, exist_ok=True)
    
    try:
        shutil.move(source_path, target_path)
        st.toast(f"✅ Processo {process_id} arquivado com sucesso!")
    except FileNotFoundError:
        st.error(f"❌ Erro: Processo {process_id} não encontrado.")
    st.rerun()

def delete_process(process_id, is_archived=False):
    """Deleta o arquivo JSON permanentemente."""
    folder = ARCHIVED_FOLDER if is_archived else DATA_FOLDER
    file_path = os.path.join(folder, f"{process_id}.json")
    
    try:
        os.remove(file_path)
        st.toast(f"🗑️ Processo {process_id} excluído permanentemente!")
    except FileNotFoundError:
        st.error(f"❌ Erro: Processo {process_id} não encontrado.")
    st.rerun()
    
def load_and_redirect(process_id):
    """Carrega o processo e redireciona para a página de edição."""
    # Como não podemos alterar o st.session_state de um arquivo para outro, 
    # a maneira mais simples de "carregar" é passar o ID e deixar o 01_Gerar_laudo.py carregar.
    st.session_state["process_to_load"] = process_id
    # A forma nativa do Streamlit para redirecionar é usar um page_link que aponta para o arquivo.
    # Mas para garantir o carregamento, vamos apenas limpar a chave e confiar no link.
    # NOTA: O código de 01_Gerar_laudo.py precisa de uma forma de carregar este ID.
    # Como a navegação entre páginas Streamlit limpa o estado, você deve usar o JSON.
    pass # Deixa o page_link fazer o trabalho

# --- Interface do Usuário ---

st.title("🏠 Gerenciamento de Laudos Periciais")

# --- Processos em Andamento ---
st.header("Processos Ativos em Andamento")
active_processes = load_process_list(DATA_FOLDER)

if active_processes:
    for process in active_processes:
        with st.container(border=True):
            col_id, col_tags, col_actions = st.columns([1, 4, 2])
            
            # Coluna ID
            col_id.markdown(f"**Nº Processo:** `{process['id']}`")
            col_id.markdown(f"**{process['status_etapa']}**")
            
            # Coluna Tags
            col_tags.markdown(f"**Partes:** {process['nome']}")
            if process['tags'] and process['tags'] != "JSON INVÁLIDO":
                col_tags.markdown(f"**⚠️ Faltando:** ` {process['tags']} `")
            else:
                col_tags.markdown("✅ **Status:** Pronto para Emissão ou Dados Incompletos")

            # Coluna Ações
            col_actions.page_link(
                "pages/01_Gerar_laudo.py", 
                label="✏️ Continuar Edição", 
                icon="▶️", 
                help="Clique para ir à página e carregar os dados deste processo."
            )
            col_actions.button("📁 Arquivar", key=f"archive_{process['id']}", on_click=archive_process, args=(process['id'],), help="Move o processo para a lista de arquivados.")
            
else:
    st.info("Nenhum processo ativo encontrado. Crie um novo na página 'Gerar Laudo'.")

st.markdown("---")

# --- Processos Arquivados ---
st.header("Processos Arquivados")
archived_processes = load_process_list(ARCHIVED_FOLDER)

if archived_processes:
    with st.expander("Mostrar Processos Arquivados"):
        for process in archived_processes:
            with st.container(border=True):
                col_id, col_nome, col_actions = st.columns([1, 4, 2])
                
                col_id.markdown(f"**Nº Processo:** `{process['id']}`")
                col_nome.markdown(f"**Partes:** {process['nome']}")
                
                # Ações
                col_actions.button("🗑️ Apagar Permanentemente", key=f"delete_archived_{process['id']}", on_click=delete_process, args=(process['id'], True), help="APAGA O ARQUIVO JSON DO DISCO!")
else:
    st.caption("A pasta de processos arquivados está vazia.")