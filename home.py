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
    excluir_processo
)

# --- Configuração Inicial ---
st.set_page_config(page_title="Início", layout="wide")
init_db()

st.title("Bem-vindo ao Gerador de Laudos")
st.write("Selecione 'Gerar Laudo' no menu lateral.")

# --- Índice de Processos via SQLite ---
with st.expander("📄 Índice de Processos (SQLite)", expanded=False):
    processos = listar_processos()
    if processos:
        df = pd.DataFrame(processos, columns=["ID", "Autor", "Réu", "Status", "Atualizado em"])
        st.dataframe(df, use_container_width=True)
    else:
        st.warning("Nenhum processo encontrado no banco de dados.")

# --- Formulário para adicionar novo processo ---
with st.expander("➕ Adicionar Novo Processo"):
    with st.form("novo_processo_form"):
        novo_id = st.text_input("Número do Processo")
        novo_autor = st.text_input("Autor(a)")
        novo_reu = st.text_input("Réu")
        novo_status = st.selectbox("Status", ["Laudo Preliminar", "Em andamento", "Concluído"])
        submitted = st.form_submit_button("Salvar")

        if submitted:
            if not novo_id or not novo_autor or not novo_reu:
                st.error("Preencha todos os campos obrigatórios.")
            elif processo_existe(novo_id):
                st.warning("Este número de processo já está cadastrado.")
            else:
                atualizado_em = datetime.now().strftime("%d/%m/%Y %H:%M")
                inserir_processo(novo_id, novo_autor, novo_reu, novo_status, atualizado_em)

                # Salva como JSON para edição futura
                dados_iniciais = {
                    "numero_processo": novo_id,
                    "autor_0": novo_autor,
                    "reu_0": novo_reu,
                    "etapas_concluidas": [],
                    "doc_padrao": None,
                    "documentos_questionados_list": [],
                }
                os.makedirs("data", exist_ok=True)
                with open(f"data/{novo_id}.json", "w", encoding="utf-8") as f:
                    json.dump(dados_iniciais, f, ensure_ascii=False, indent=2)

                st.session_state["process_to_load"] = novo_id
                st.success(f"✅ Processo {novo_id} criado. Redirecionando para edição...")
                st.switch_page("pages/01_Gerar_laudo.py")

# --- Exclusão de processos do banco ---
with st.expander("🗑️ Excluir Processo do Banco de Dados"):
    processos = listar_processos()
    if processos:
        df = pd.DataFrame(processos, columns=["ID", "Autor", "Réu", "Status", "Atualizado em"])
        processo_ids = df["ID"].tolist()
        processo_selecionado = st.selectbox("Selecione o processo para excluir", processo_ids)
        if st.button("Excluir Processo"):
            excluir_processo(processo_selecionado)
            json_path = f"data/{processo_selecionado}.json"
            if os.path.exists(json_path):
                os.remove(json_path)
            st.success(f"✅ Processo {processo_selecionado} excluído com sucesso!")
            st.rerun()
    else:
        st.info("Nenhum processo disponível para exclusão.")

# --- Processos locais via JSON ---
DATA_FOLDER = "data"
ARCHIVED_FOLDER = os.path.join(DATA_FOLDER, "arquivados")

def load_process_list(source_folder=DATA_FOLDER):
    if not os.path.exists(source_folder):
        return []

    process_list = []
    files_to_check = [f for f in os.listdir(source_folder) if f.endswith(".json")]

    for filename in files_to_check:
        filepath = os.path.join(source_folder, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

                missing = []
                if not data.get("numero_processo"): missing.append("Nº Processo")
                if not data.get("autor_0"): missing.append("Autor")
                if not data.get("reu_0"): missing.append("Réu")
                if "Apresentação" not in data.get("etapas_concluidas", []): missing.append("Etapa 1")
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
    folder = ARCHIVED_FOLDER if is_archived else DATA_FOLDER
    file_path = os.path.join(folder, f"{process_id}.json")
    try:
        os.remove(file_path)
        st.toast(f"🗑️ Processo {process_id} excluído permanentemente!")
    except FileNotFoundError:
        st.error(f"❌ Erro: Processo {process_id} não encontrado.")
    st.rerun()

# --- Processos Ativos ---
st.header("Processos Ativos em Andamento")
active_processes = load_process_list(DATA_FOLDER)

if active_processes:
    for process in active_processes:
        with st.container(border=True):
            col_id, col_tags, col_actions = st.columns([1, 4, 2])

            col_id.markdown(f"**Nº Processo:** `{process['id']}`")
            col_id.markdown(f"**{process['status_etapa']}**")

            col_tags.markdown(f"**Partes:** {process['nome']}")
            if process['tags'] and process['tags'] != "JSON INVÁLIDO":
                col_tags.markdown(f"**⚠️ Faltando:** ` {process['tags']} `")
            else:
                col_tags.markdown("✅ **Status:** Pronto para Emissão ou Dados Incompletos")

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
                col_actions.button("🗑️ Apagar Permanentemente", key=f"delete_archived_{process['id']}", on_click=delete_process, args=(process['id'], True), help="APAGA O ARQUIVO JSON DO DISCO!")
else:
    st.caption("A pasta de processos arquivados está vazia.")