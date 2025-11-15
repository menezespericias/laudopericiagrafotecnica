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

                dados_iniciais = {
                    "numero_processo": novo_id,
                    "autor": novo_autor,
                    "reu": novo_reu,
                    "status_processo": novo_status,
                    "etapas_concluidas": [],
                    "data_laudo": datetime.today().strftime("%Y-%m-%d")
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

# --- Processos Ativos em Andamento ---
st.header("Processos Ativos em Andamento")
arquivos = [f for f in os.listdir("data") if f.endswith(".json") and not f.startswith("arquivados")]
if arquivos:
    for arquivo in arquivos:
        caminho = os.path.join("data", arquivo)
        with open(caminho, "r", encoding="utf-8") as f:
            dados = json.load(f)
        processo_id = dados.get("numero_processo", arquivo.replace(".json", ""))
        partes = f"{dados.get('autor', 'Autor')} x {dados.get('reu', 'Réu')}"
        etapas = dados.get("etapas_concluidas", [])
        st.markdown(f"**Processo:** `{processo_id}`")
        st.markdown(f"**Partes:** {partes}")
        st.markdown(f"**Etapas concluídas:** {len(etapas)}")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✏️ Continuar Edição", key=f"editar_{processo_id}"):
                st.session_state["process_to_load"] = processo_id
                st.switch_page("pages/01_Gerar_laudo.py")
        with col2:
            if st.button("📁 Arquivar", key=f"arquivar_{processo_id}"):
                os.makedirs("data/arquivados", exist_ok=True)
                shutil.move(caminho, f"data/arquivados/{arquivo}")
                st.success(f"Processo {processo_id} arquivado.")
                st.rerun()
else:
    st.info("Nenhum processo ativo encontrado.")

# --- Processos Arquivados ---
st.header("Processos Arquivados")
arquivados = [f for f in os.listdir("data/arquivados") if f.endswith(".json")] if os.path.exists("data/arquivados") else []
if arquivados:
    with st.expander("Mostrar Processos Arquivados"):
        for arquivo in arquivados:
            caminho = os.path.join("data/arquivados", arquivo)
            with open(caminho, "r", encoding="utf-8") as f:
                dados = json.load(f)
            processo_id = dados.get("numero_processo", arquivo.replace(".json", ""))
            partes = f"{dados.get('autor', 'Autor')} x {dados.get('reu', 'Réu')}"
            st.markdown(f"**Processo Arquivado:** `{processo_id}` — {partes}")
            if st.button("🗑️ Apagar Permanentemente", key=f"delete_{processo_id}"):
                os.remove(caminho)
                st.success(f"Processo {processo_id} excluído permanentemente.")
                st.rerun()
else:
    st.caption("Nenhum processo arquivado encontrado.")