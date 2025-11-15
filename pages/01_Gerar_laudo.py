import streamlit as st
from utils.word_handler import gerar_laudo
import os
from datetime import date, datetime 
from num2words import num2words
import json
import shutil 
from typing import List, Dict, Any, Union

# --- Configuração Inicial e Tema ---
st.set_page_config(page_title="Laudo Grafotécnico", layout="wide")

DATA_FOLDER = "data"

# --- Inicialização do Estado de Sessão ---
if "etapas_concluidas" not in st.session_state:
    st.session_state.etapas_concluidas = set()
if "theme" not in st.session_state:
    st.session_state.theme = "light" 
if "editing_etapa_1" not in st.session_state:
    # A variável 'editing_etapa_1' começa como True, a menos que estejamos carregando um processo.
    st.session_state.editing_etapa_1 = not st.session_state.get("process_to_load")
    
if "num_laudas" not in st.session_state:
    st.session_state.num_laudas = 10
if "num_docs_questionados" not in st.session_state:
    st.session_state.num_docs_questionados = 1
if "documentos_questionados_list" not in st.session_state:
    st.session_state.documentos_questionados_list = []
    
# Estruturas de dados para os quesitos individuais (com placeholders para imagem)
if "quesitos_autor" not in st.session_state:
    st.session_state.quesitos_autor = []
if "quesitos_reu" not in st.session_state:
    st.session_state.quesitos_reu = []

# --- Funções de Ajuda para Persistência e Quesitos ---

def save_process_data():
    """Salva os dados importantes para persistência e visualização na home."""
    
    # Se não houver número de processo, não salva
    if not st.session_state.get("numero_processo"):
        return
    
    processo_num = st.session_state.numero_processo
    
    # Prepara listas de quesitos para salvar no JSON, removendo objetos UploadedFile
    def clean_quesitos_for_json(quesitos_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        cleaned = []
        for q in quesitos_list:
            q_clean = q.copy()
            # O UploadedFile não é serializável, removemos e mantemos apenas o nome
            q_clean.pop("imagem_anexa", None) 
            cleaned.append(q_clean)
        return cleaned
    
    # Tenta obter as datas como string formatada para JSON
    data_laudo_obj = st.session_state.get("data_laudo", date.today())
    data_colheita_obj = st.session_state.get("data_colheita", date.today())

    data_laudo_str = data_laudo_obj.strftime("%d/%m/%Y") if isinstance(data_laudo_obj, date) else str(data_laudo_obj)
    data_colheita_str = data_colheita_obj.strftime("%d/%m/%Y") if isinstance(data_colheita_obj, date) else str(data_colheita_obj)
    
    data_to_save = {
        # --- CHAVES PADRONIZADAS: AGORA SOMENTE MINÚSCULAS PARA EVITAR CONFLITO ---
        "numero_processo": processo_num,
        "numero_vara": st.session_state.get("numero_vara", ""),
        "id_nomeacao": st.session_state.get("id_nomeacao", ""),
        "data_laudo": data_laudo_str, # Antes era DATA_LAUDO
        "data_colheita": data_colheita_str, # Antes era DATA_COLHEITA
        "comarca": st.session_state.get("comarca", "").upper(),
        # --------------------------------------------------------------------------
        
        "etapas_concluidas": list(st.session_state.etapas_concluidas),
        
        # Etapa 7 - Quesitos (limpos)
        "quesitos_autor": clean_quesitos_for_json(st.session_state.get("quesitos_autor", [])),
        "quesitos_reu": clean_quesitos_for_json(st.session_state.get("quesitos_reu", [])),
        
        # Outros dados importantes
        "doc_padrao": st.session_state.get("doc_padrao", ""),
        "documentos_questionados_list": st.session_state.get("documentos_questionados_list", []),
        "fls_quesitos_autor": st.session_state.get("fls_quesitos_autor", ""),
        "fls_quesitos_reu": st.session_state.get("fls_quesitos_reu", ""),
        
        # Correção: Estes são salvos automaticamente pela chave, mas para garantir
        # a persistência no JSON, lemos diretamente do session state.
        "nao_enviou_autor": st.session_state.get("nao_enviou_autor", False),
        "nao_enviou_reu": st.session_state.get("nao_enviou_reu", False),
        
        # Salva o número de autores/réus
        "num_autores": st.session_state.get("num_autores", 1),
        "num_reus": st.session_state.get("num_reus", 1),
        
        # Salva os autores e réus
        **{f"autor_{i}": st.session_state.get(f"autor_{i}", "") for i in range(st.session_state.get("num_autores", 1))},
        **{f"reu_{i}": st.session_state.get(f"reu_{i}", "") for i in range(st.session_state.get("num_reus", 1))}
    }
    
    os.makedirs(DATA_FOLDER, exist_ok=True)
    json_filename = os.path.join(DATA_FOLDER, f"{processo_num}.json")
    
    with open(json_filename, 'w', encoding='utf-8') as f:
        json.dump(data_to_save, f, indent=4, ensure_ascii=False)
        
    st.session_state["last_saved_process"] = processo_num
    

def load_process_data(processo_num: str, set_editing_false: bool = True):
    """
    Carrega os dados de um processo salvo no Streamlit Session State.
    set_editing_false: Se True (padrão), define editing_etapa_1 como False (bloqueado) após carregar.
    """
    json_filename = os.path.join(DATA_FOLDER, f"{processo_num}.json")
    if os.path.exists(json_filename):
        with open(json_filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
            # --- CARREGAMENTO SIMPLIFICADO E CONSISTENTE ---
            # Carrega dados principais (agora usando chaves minúsculas)
            st.session_state["numero_processo"] = data.get("numero_processo", "")
            st.session_state["numero_vara"] = data.get("numero_vara", "")
            st.session_state["comarca"] = data.get("comarca", "")
            st.session_state["id_nomeacao"] = data.get("id_nomeacao", "")
            # -----------------------------------------------
            
            # Conversão de Datas
            def parse_date(date_str: str) -> date:
                try:
                    # Tenta parsing DD/MM/YYYY
                    return datetime.strptime(date_str, "%d/%m/%Y").date()
                except (ValueError, TypeError):
                    return date.today()

            st.session_state["data_laudo"] = parse_date(data.get("data_laudo", date.today().strftime("%d/%m/%Y")))
            st.session_state["data_colheita"] = parse_date(data.get("data_colheita", date.today().strftime("%d/%m/%Y")))
            
            # Autores/Réus e números
            st.session_state["num_autores"] = data.get("num_autores", 1)
            st.session_state["num_reus"] = data.get("num_reus", 1)
            for i in range(st.session_state["num_autores"]):
                st.session_state[f"autor_{i}"] = data.get(f"autor_{i}", "")
            for i in range(st.session_state["num_reus"]):
                st.session_state[f"reu_{i}"] = data.get(f"reu_{i}", "")

            # Etapas e Quesitos
            st.session_state.etapas_concluidas = set(data.get("etapas_concluidas", []))
            st.session_state.quesitos_autor = data.get("quesitos_autor", [])
            st.session_state.quesitos_reu = data.get("quesitos_reu", [])
            
            # Etapa 7 Fls
            st.session_state["fls_quesitos_autor"] = data.get("fls_quesitos_autor", "")
            st.session_state["fls_quesitos_reu"] = data.get("fls_quesitos_reu", "")
            # Carrega o estado do checkbox
            st.session_state["nao_enviou_autor"] = data.get("nao_enviou_autor", False)
            st.session_state["nao_enviou_reu"] = data.get("nao_enviou_reu", False)
            
            # Doc Padrão
            st.session_state.doc_padrao = data.get("doc_padrao", "")
            st.session_state.documentos_questionados_list = data.get("documentos_questionados_list", [])
            
            # LÓGICA DE EDIÇÃO CORRIGIDA
            if set_editing_false:
                st.session_state.editing_etapa_1 = False 
                st.toast(f"✅ Processo {processo_num} carregado com sucesso!")
            else:
                # Se set_editing_false é False, estamos re-editando.
                st.session_state.editing_etapa_1 = True
                st.toast(f"✅ Dados de {processo_num} recarregados. Etapa 1 liberada para edição!")
                
            st.rerun() 

# Verifica se um processo foi selecionado na Home.py para ser carregado
if "process_to_load" in st.session_state and st.session_state["process_to_load"]:
    # Chama com o padrão set_editing_false=True para começar bloqueado
    load_process_data(st.session_state["process_to_load"])
    del st.session_state["process_to_load"]

def registrar_etapa(etapa: str):
    st.session_state.etapas_concluidas.add(etapa)
    save_process_data() 
    st.toast(f"✔️ Etapa '{etapa}' salva com sucesso!")

def toggle_editing():
    """Função que só deve ser usada para o evento de BLOQUEAR (True -> False)."""
    st.session_state.editing_etapa_1 = False
    registrar_etapa("Apresentação")

def formatar_data(data_obj: date) -> str:
    return data_obj.strftime("%d/%m/%Y")

def update_process_data_and_save():
    """Função de callback para salvar dados da Etapa 1 ao serem modificados."""
    # Salva todos os dados
    if st.session_state.get("numero_processo"):
        # Chama a função de salvamento real (não recursiva)
        save_process_data()
    
    # Tenta marcar a Etapa 1 como concluída se os dados principais estiverem preenchidos
    processo_num = st.session_state.get("numero_processo", "")
    primeiro_autor = st.session_state.get("autor_0", "") 
    primeiro_reu = st.session_state.get("reu_0", "")
    if processo_num and primeiro_autor and primeiro_reu and st.session_state.get("id_nomeacao"):
        if "Apresentação" not in st.session_state.etapas_concluidas and not st.session_state.editing_etapa_1:
             registrar_etapa("Apresentação")
             
# Função para adicionar um novo item de quesito à lista
def add_quesito(parte: str):
    """Adiciona um novo quesito vazio à lista do Autor ou Réu."""
    new_quesito = {"quesito": "", "resposta": "", "imagem_anexa": None, "imagem_name": ""}
    if parte == "autor":
        st.session_state.quesitos_autor.append(new_quesito)
    elif parte == "reu":
        st.session_state.quesitos_reu.append(new_quesito)
    save_process_data()

# Função para remover um quesito específico
def remove_quesito(parte: str, index: int):
    """Remove um quesito pelo índice."""
    if parte == "autor":
        st.session_state.quesitos_autor.pop(index)
    elif parte == "reu":
        st.session_state.quesitos_reu.pop(index)
    save_process_data()
    st.rerun()

# --- TÍTULO E LAYOUT PRINCIPAL ---
st.title("📄 Emissão de Laudo Pericial Grafotécnico")

# 1. Define variáveis para o card
processo_num = st.session_state.get("numero_processo", "N/A")
primeiro_autor = st.session_state.get("autor_0", "N/A").upper() 
primeiro_reu = st.session_state.get("reu_0", "N/A").upper()
is_saved = not st.session_state.editing_etapa_1

# 2. Cria layout de colunas para o card e o botão
col_main, col_sidebar_right = st.columns([4, 1])

# --- Coluna Direita (CARD e BOTÃO EXCEL) ---
with col_sidebar_right:
    # Card Permanente (após salvar a Etapa 1)
    if is_saved and processo_num != "N/A":
        st.markdown("##### Processo Atual")
        with st.container(border=True):
            st.markdown(f"**Nº:** `{processo_num}`")
            st.markdown(f"**A:** {primeiro_autor.split(',')[0]}") 
            st.markdown(f"**R:** {primeiro_reu.split(',')[0]}")
        st.markdown("---")
        
    # Acesso Rápido à Planilha Excel
    st.markdown("##### Ferramentas")
    excel_path = "utils/PLANILHA EOG - Elementos de Ordem Gráfica.xlsm"
    
    if os.path.exists(excel_path):
        absolute_path = os.path.abspath(excel_path)
        
        st.info("⚠️ **Atenção:** Para abrir a planilha, **copie o caminho abaixo** e cole-o no Explorador de Arquivos:")
        
        st.code(absolute_path)
        
        with open(excel_path, "rb") as file:
            st.download_button(
                label="⬇️ Baixar Planilha (Alternativa)",
                data=file.read(),
                file_name="PLANILHA EOG - Elementos de Ordem Gráfica.xlsm",
                mime="application/vnd.ms-excel.sheet.macroEnabled.12",
                key="download_excel_eog"
            )

    else:
        st.warning("Planilha EOG não encontrada em /utils.")


# --- Coluna Principal (TODAS AS ETAPAS) ---
with col_main:

    # Etapa 1: Apresentação
    etapa_1_expander = st.expander(
        f"📌 Etapa 1 de 10 — Apresentação e Endereçamento {'✔️' if 'Apresentação' in st.session_state.etapas_concluidas else ''}", 
        expanded=st.session_state.editing_etapa_1
    )
    with etapa_1_expander:
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Dados do Processo")
            # --- CORREÇÃO: REMOVENDO O ARGUMENTO VALUE PARA CONFIAR APENAS NO KEY ---
            numero_processo = st.text_input("Número do Processo", key="numero_processo", on_change=update_process_data_and_save)
            numero_vara = st.text_input("Número da Vara", key="numero_vara", on_change=update_process_data_and_save)
            comarca = st.text_input("Comarca / Cidade", key="comarca", on_change=update_process_data_and_save)
            id_nomeacao = st.text_input("Fls. Documento de Nomeação (ID_NOMEACAO)", key="id_nomeacao", help="Usado nas seções 1 e 2 do Laudo.", on_change=update_process_data_and_save) 
            # -----------------------------------------------------------------------

        with col2:
            st.subheader("Datas")
            
            # Tratamento de data
            data_laudo_default = st.session_state.get("data_laudo", date.today())
            if isinstance(data_laudo_default, str):
                try: data_laudo_default = datetime.strptime(data_laudo_default, "%d/%m/%Y").date()
                except: data_laudo_default = date.today()
                     
            data_colheita_default = st.session_state.get("data_colheita", date.today())
            if isinstance(data_colheita_default, str):
                try: data_colheita_default = datetime.strptime(data_colheita_default, "%d/%m/%Y").date()
                except: data_colheita_default = date.today()
                    
            # --- CORREÇÃO: USANDO data_laudo_default COMO VALOR INICIAL NO LUGAR DE data_laudo (string) ---
            data_laudo = st.date_input("Data do Laudo", format="DD/MM/YYYY", key="data_laudo", value=data_laudo_default, on_change=update_process_data_and_save)
            data_colheita = st.date_input("Data da Colheita dos Padrões (se aplicável)", format="DD/MM/YYYY", key="data_colheita", value=data_colheita_default, on_change=update_process_data_and_save)
            # ------------------------------------------------------------------------------------------------

        st.markdown("---")
        
        col3, col4 = st.columns(2)
        
        current_num_autores = st.session_state.get("num_autores", 1)
        current_num_reus = st.session_state.get("num_reus", 1)
        
        with col3:
            num_autores = st.number_input("Número de Autores (Máx. 5)", min_value=1, max_value=5, value=current_num_autores, key="num_autores", on_change=update_process_data_and_save)
            # --- CORREÇÃO: REMOVENDO O ARGUMENTO VALUE PARA CONFIAR APENAS NO KEY ---
            autores = [st.text_input(f"Autor {i+1}", key=f"autor_{i}", on_change=update_process_data_and_save) for i in range(num_autores)]
            # -----------------------------------------------------------------------
            
        with col4:
            num_reus = st.number_input("Número de Réus (Máx. 5)", min_value=1, max_value=5, value=current_num_reus, key="num_reus", on_change=update_process_data_and_save)
            # --- CORREÇÃO: REMOVENDO O ARGUMENTO VALUE PARA CONFIAR APENAS NO KEY ---
            reus = [st.text_input(f"Réu {i+1}", key=f"reu_{i}", on_change=update_process_data_and_save) for i in range(num_reus)]
            # -----------------------------------------------------------------------

        # Acessa os valores do session_state diretamente, que são atualizados pelo key
        preenchido = all([
            st.session_state.get("numero_processo"), 
            st.session_state.get("numero_vara"), 
            st.session_state.get("comarca"), 
            st.session_state.get("id_nomeacao"),
            st.session_state.get("data_laudo"), 
            st.session_state.get("data_colheita"),
            st.session_state.get("autor_0"), 
            st.session_state.get("reu_0")
        ])
        
        # --- LÓGICA DE BOTÕES JÁ CORRIGIDA ANTERIORMENTE ---
        if st.session_state.editing_etapa_1:
            if st.button("🔒 Bloquear Etapa 1 (Salvar)", disabled=not preenchido):
                # 1. Vai de EDITANDO (True) para BLOQUEADO (False) - SALVA DADOS
                toggle_editing() # Seta editing_etapa_1 = False e chama registrar_etapa (que salva)
                st.rerun()
                
        else: # Bloco atualmente bloqueado (st.session_state.editing_etapa_1 é False)
            if st.button("✏️ Retornar à Edição da Etapa 1"):
                # 2. Vai de BLOQUEADO (False) para EDITANDO (True) - RECARREGA DADOS E ABRE
                processo_num_load = st.session_state.get("numero_processo")
                if processo_num_load:
                    # Carrega os dados do JSON (garante integridade) e Seta editing_etapa_1 = True
                    # set_editing_false=False instrui load_process_data a manter o bloco aberto.
                    load_process_data(processo_num_load, set_editing_false=False)
                else:
                    st.error("Não há número de processo para recarregar. Preencha os campos.")
                    st.session_state.editing_etapa_1 = True # Abre vazio para ser preenchido
                    st.rerun()

    st.markdown("---")

    # [O restante do código (Etapas 2 a 10) continua inalterado, pois o problema estava na Etapa 1 e nas funções de persistência.]
    
    # Etapa 2: Objetivos da Perícia 
    with st.expander(f"🎯 Etapa 2 de 10 — Objetivos da Perícia (Padronizado) {'✔️' if 'Objetivos' in st.session_state.etapas_concluidas else ''}"):
        st.info(f"O texto é padronizado e usa o ID da Nomeação: **{st.session_state.get('id_nomeacao', '[ID DECISAO NOMEACAO NÃO PREENCHIDO]')}**.")
        if st.button("💾 Salvar etapa 2 (Pular)", key="salvar_2"):
            registrar_etapa("Objetivos")

    st.markdown("---")

    # Etapa 3: Introdução 
    with st.expander(f"📘 Etapa 3 de 10 — Introdução/Preâmbulo (Padronizado) {'✔️' if 'Introdução' in st.session_state.etapas_concluidas else ''}"):
        st.success("O texto é 100% padronizado no modelo Word.")
        if st.button("💾 Salvar etapa 3 (Pular)", key="salvar_3"):
            registrar_etapa("Introdução")

    st.markdown("---")

    # Etapa 4: Documentos Submetidos a Exame 
    with st.expander(f"📄 Etapa 4 de 10 — Documentos Submetidos a Exame {'✔️' if 'Documentos' in st.session_state.etapas_concluidas else ''}"):
        
        st.subheader("4.1 Documentos Questionados (PQ) e Resultado da Análise")
        
        num_docs_questionados = st.number_input("Número de Documentos Questionados", min_value=1, max_value=10, value=st.session_state.get("num_docs_questionados", 1), key="num_docs_questionados", on_change=save_process_data)
        
        documentos_questionados = []
        
        # Garante que a lista do session state tenha o tamanho mínimo
        if len(st.session_state.documentos_questionados_list) < num_docs_questionados:
            for _ in range(num_docs_questionados - len(st.session_state.documentos_questionados_list)):
                 st.session_state.documentos_questionados_list.append({
                    "TIPO_DOCUMENTO": "",
                    "NUMERO_CONTRATO": "",
                    "DATA_DOCUMENTO": date.today().strftime("%d/%m/%Y"),
                    "FLS_DOCUMENTOS": "",
                    "RESULTADO": "Não Avaliado"
                })

        # Remove o excesso
        st.session_state.documentos_questionados_list = st.session_state.documentos_questionados_list[:num_docs_questionados]
        
        for i in range(num_docs_questionados):
            doc = st.session_state.documentos_questionados_list[i]
            
            tipo_documento_default = doc.get("TIPO_DOCUMENTO", "")
            numero_contrato_default = doc.get("NUMERO_CONTRATO", "")
            fls_documentos_default = doc.get("FLS_DOCUMENTOS", "")
            resultado_default = doc.get("RESULTADO", "Não Avaliado") 
            
            data_documento_str = doc.get("DATA_DOCUMENTO", date.today().strftime("%d/%m/%Y"))
            try:
                data_documento_default = datetime.strptime(data_documento_str, "%d/%m/%Y").date()
            except ValueError:
                data_documento_default = date.today()
            
            with st.container(border=True):
                st.markdown(f"**Documento {i+1}**")
                colA, colB, colC = st.columns([1.5, 1.5, 1])
                with colA:
                    tipo_documento = st.text_input(f"Tipo (D{i+1})", key=f"tipo_documento_{i}", label_visibility="collapsed", placeholder="Tipo de Documento", value=tipo_documento_default, on_change=save_process_data)
                    numero_contrato = st.text_input(f"Nº (D{i+1})", key=f"numero_contrato_{i}", label_visibility="collapsed", placeholder="Número de Identificação", value=numero_contrato_default, on_change=save_process_data)
                    
                with colB:
                    data_documento = st.date_input(f"Data (D{i+1})", format="DD/MM/YYYY", key=f"data_documento_{i}", label_visibility="collapsed", value=data_documento_default, on_change=save_process_data)
                    fls_documentos = st.text_input(f"Fls. (D{i+1})", key=f"fls_documentos_{i}", placeholder="Fls. Questionado (Ex: 10-15)", value=fls_documentos_default, on_change=save_process_data)
                    
                with colC:
                    resultado = st.selectbox(
                        "Resultado", 
                        ["Não Avaliado", "Autêntico", "Falso", "Não Conclusivo"], 
                        index=["Não Avaliado", "Autêntico", "Falso", "Não Conclusivo"].index(resultado_default),
                        key=f"resultado_documento_{i}", 
                        label_visibility="collapsed",
                        on_change=save_process_data
                    )
                    
                # Atualiza a lista do session state (necessário se o valor for alterado por um widget sem on_change)
                st.session_state.documentos_questionados_list[i].update({
                    "TIPO_DOCUMENTO": tipo_documento,
                    "NUMERO_CONTRATO": numero_contrato,
                    "DATA_DOCUMENTO": formatar_data(data_documento),
                    "FLS_DOCUMENTOS": fls_documentos,
                    "RESULTADO": resultado
                })
                
        documentos_questionados = st.session_state.documentos_questionados_list
            
        st.markdown("---")
        
        st.subheader("4.2 Documentos Padrão (PC)")
        doc_padrao = st.text_area("Descrição dos Documentos Padrão (PCE - Encontrados nos Autos)", key="doc_padrao", height=100, on_change=save_process_data) 
        
        colC, colD = st.columns(2)
        with colC:
            num_espécimes = st.number_input("Número de Espécimes Colhidos (Padrões)", min_value=0, max_value=50, value=st.session_state.get("num_espécimes", 10), key="num_espécimes", on_change=save_process_data) 
        with colD:
            fls_colheita = st.text_input("Fls. do Termo de Colheita (PCA)", key="fls_colheita", on_change=save_process_data) 


        preenchido = all([doc['TIPO_DOCUMENTO'] and doc['FLS_DOCUMENTOS'] for doc in documentos_questionados]) and st.session_state.doc_padrao
        
        if st.button("💾 Salvar etapa 4", key="salvar_4"):
            if preenchido:
                registrar_etapa("Documentos")
            else:
                st.error("Preencha o tipo e as fls. para todos os documentos questionados e a descrição dos documentos padrão.")

    st.markdown("---")

    # Etapa 5: Exames Periciais e Metodologia 
    with st.expander(f"🔬 Etapa 5 de 10 — Exames Periciais e Metodologia (Padronizado) {'✔️' if 'Metodologia' in st.session_state.etapas_concluidas else ''}"):
        st.success("O texto é 100% padronizado no modelo Word.")
        if st.button("💾 Salvar etapa 5 (Pular)", key="salvar_5"):
            registrar_etapa("Metodologia")

    st.markdown("---")

    # Etapa 6: Conclusão 
    with st.expander(f"🧾 Etapa 6 de 10 — Conclusão (Gerada Automaticamente) {'✔️' if 'Conclusão' in st.session_state.etapas_concluidas else ''}"):
        st.info("A conclusão é gerada com base na classificação de cada documento na Etapa 4 (Documentos Questionados).")
        
        if st.session_state.documentos_questionados_list:
            autenticos = [d for d in st.session_state.documentos_questionados_list if d.get('RESULTADO') == 'Autêntico']
            falsos = [d for d in st.session_state.documentos_questionados_list if d.get('RESULTADO') == 'Falso']
            
            st.markdown(f"**Documentos Autênticos Encontrados:** {len(autenticos)}")
            st.markdown(f"**Documentos Falsos Encontrados:** {len(falsos)}")
        else:
            st.warning("Preencha e salve a Etapa 4 para ver o resumo da conclusão.")
            
        if st.button("💾 Salvar etapa 6 (Pular)", key="salvar_6"):
            registrar_etapa("Conclusão")

    st.markdown("---")

    # Etapa 7: Resposta aos Quesitos (INDIVIDUALIZADA com Imagem e Exclusão)
    with st.expander(f"🗣️ Etapa 7 de 10 — Resposta aos Quesitos {'✔️' if 'Quesitos' in st.session_state.etapas_concluidas else ''}"):
        
        # --- Quesitos da Parte Autora ---
        st.markdown("### 1. Quesitos da Parte Autora")
        col_autor_fls, col_autor_check = st.columns([3, 2])
        
        with col_autor_fls:
            fls_quesitos_autor = st.text_input("Fls. e Data dos Quesitos do Autor", key="fls_quesitos_autor", on_change=save_process_data)
            
        with col_autor_check:
            # O widget st.checkbox usa a chave para gerenciar o estado.
            st.checkbox(
                "Não enviou quesitos",
                key="nao_enviou_autor",
                value=st.session_state.get("nao_enviou_autor", False),
                on_change=save_process_data
            )
            
        # Acessa o valor diretamente pelo session state
        if not st.session_state.get("nao_enviou_autor", False):
            st.subheader("Cadastro de Quesitos do Autor")
            
            for i, item in enumerate(st.session_state.quesitos_autor):
                with st.container(border=True):
                    st.markdown(f"**Quesito Nº {i+1}**")
                    
                    quesito_key = f"quesito_autor_{i}"
                    resposta_key = f"resposta_autor_{i}"
                    imagem_key = f"imagem_autor_{i}"
                    
                    # Quesito Text Area
                    quesito_text = st.text_area(
                        "Texto do Quesito", 
                        key=quesito_key, 
                        value=item.get("quesito", ""), 
                        height=70
                    )
                    st.session_state.quesitos_autor[i]["quesito"] = quesito_text
                    
                    # Resposta Text Area
                    resposta_text = st.text_area(
                        "Resposta do Perito", 
                        key=resposta_key, 
                        value=item.get("resposta", ""),
                        height=100
                    )
                    st.session_state.quesitos_autor[i]["resposta"] = resposta_text
                    
                    st.markdown("---")
                    
                    # File Uploader para Imagem
                    uploaded_file = st.file_uploader(
                        "📷 Anexar Imagem na Resposta (Opcional)",
                        type=["png", "jpg", "jpeg"],
                        key=imagem_key
                    )
                    
                    if uploaded_file:
                        st.session_state.quesitos_autor[i]["imagem_anexa"] = uploaded_file
                        st.session_state.quesitos_autor[i]["imagem_name"] = uploaded_file.name
                        st.caption(f"Imagem anexada: **{uploaded_file.name}**")
                    elif item.get("imagem_name"):
                        st.caption(f"Imagem pré-selecionada: **{item['imagem_name']}**")
                    
                    # Remove Button
                    st.button(f"🗑️ Excluir Quesito {i+1}", key=f"remove_autor_{i}", on_click=remove_quesito, args=("autor", i))
            
            # Add Button
            st.button("➕ Adicionar Novo Quesito do Autor", key="add_autor", on_click=add_quesito, args=("autor",))
            
            # Salvar dados após interação em todos os quesitos
            if st.button("Salvar Conteúdo dos Quesitos do Autor", key="save_content_autor"):
                save_process_data()
                st.toast("Conteúdo dos quesitos do Autor salvo!")
            
        else:
            st.info("O bloco de quesitos do Autor será substituído pela mensagem de não envio no Word.")
            if st.session_state.quesitos_autor:
                st.session_state.quesitos_autor = []
                save_process_data()

        st.markdown("---")
        
        # --- Quesitos da Parte Ré ---
        st.markdown("### 2. Quesitos da Parte Ré")
        col_reu_fls, col_reu_check = st.columns([3, 2])
        
        with col_reu_fls:
            fls_quesitos_reu = st.text_input("Fls. e Data dos Quesitos do Réu", key="fls_quesitos_reu", on_change=save_process_data) 

        with col_reu_check:
            # O widget st.checkbox usa a chave para gerenciar o estado.
            st.checkbox(
                "Não enviou quesitos ",
                key="nao_enviou_reu",
                value=st.session_state.get("nao_enviou_reu", False),
                on_change=save_process_data
            )

        # Acessa o valor diretamente pelo session state
        if not st.session_state.get("nao_enviou_reu", False):
            st.subheader("Cadastro de Quesitos do Réu")
            
            for i, item in enumerate(st.session_state.quesitos_reu):
                with st.container(border=True):
                    st.markdown(f"**Quesito Nº {i+1}**")
                    
                    quesito_key = f"quesito_reu_{i}"
                    resposta_key = f"resposta_reu_{i}"
                    imagem_key = f"imagem_reu_{i}"

                    # Quesito Text Area
                    quesito_text = st.text_area(
                        "Texto do Quesito", 
                        key=quesito_key, 
                        value=item.get("quesito", ""), 
                        height=70
                    )
                    st.session_state.quesitos_reu[i]["quesito"] = quesito_text

                    # Resposta Text Area
                    resposta_text = st.text_area(
                        "Resposta do Perito", 
                        key=resposta_key, 
                        value=item.get("resposta", ""),
                        height=100
                    )
                    st.session_state.quesitos_reu[i]["resposta"] = resposta_text
                    
                    st.markdown("---")
                    
                    # File Uploader para Imagem
                    uploaded_file = st.file_uploader(
                        "📷 Anexar Imagem na Resposta (Opcional)",
                        type=["png", "jpg", "jpeg"],
                        key=imagem_key
                    )

                    if uploaded_file:
                        st.session_state.quesitos_reu[i]["imagem_anexa"] = uploaded_file
                        st.session_state.quesitos_reu[i]["imagem_name"] = uploaded_file.name
                        st.caption(f"Imagem anexada: **{uploaded_file.name}**")
                    elif item.get("imagem_name"):
                        st.caption(f"Imagem pré-selecionada: **{item['imagem_name']}**")
                    
                    # Remove Button
                    st.button(f"🗑️ Excluir Quesito {i+1}", key=f"remove_reu_{i}", on_click=remove_quesito, args=("reu", i))
            
            # Add Button
            st.button("➕ Adicionar Novo Quesito do Réu", key="add_reu", on_click=add_quesito, args=("reu",))
            
            # Salvar dados após interação em todos os quesitos
            if st.button("Salvar Conteúdo dos Quesitos do Réu", key="save_content_reu"):
                save_process_data()
                st.toast("Conteúdo dos quesitos do Réu salvo!")

        else:
            st.info("O bloco de quesitos do Réu será substituído pela mensagem de não envio no Word.")
            if st.session_state.quesitos_reu:
                st.session_state.quesitos_reu = []
                save_process_data()


        if st.button("💾 Salvar etapa 7", key="salvar_7"):
            registrar_etapa("Quesitos")
    
    st.markdown("---")

    # Etapa 8: Encerramento
    with st.expander(f"✅ Etapa 8 de 10 — Encerramento {'✔️' if 'Encerramento' in st.session_state.etapas_concluidas else ''}"):
        num_laudas = st.number_input("Número Final de Laudas do Laudo (Para fins de registro)", min_value=1, value=st.session_state.get("num_laudas", 10), key="num_laudas", on_change=save_process_data) 
        
        st.info("O restante do texto (cidade, data, etc.) é preenchido automaticamente pelos campos da Etapa 1.")
        if st.button("💾 Salvar etapa 8 (Pular)", key="salvar_8"):
            registrar_etapa("Encerramento")

    st.markdown("---")

    # Etapa 9: ANEXOS
    with st.expander(f"📎 Etapa 9 de 10 — ANEXOS (Pranchas Fotográficas) {'✔️' if 'Anexos' in st.session_state.etapas_concluidas else ''}"):
        st.warning("As imagens serão inseridas no Word na ordem em que foram carregadas.")
        anexos = st.file_uploader("Imagens para ANEXOS", accept_multiple_files=True, type=["png", "jpg", "jpeg"], key="anexos")
        if st.button("💾 Salvar etapa 9", key="salvar_9"):
            registrar_etapa("Anexos")

    st.markdown("---")

    # Etapa 10: ADENDOS
    with st.expander(f"📎 Etapa 10 de 10 — ADENDOS (Documentos/Fotos Adicionais) {'✔️' if 'Adendos' in st.session_state.etapas_concluidas else ''}"):
        adendos = st.file_uploader("Imagens/Documentos para ADENDOS", accept_multiple_files=True, type=["png", "jpg", "jpeg"], key="adendos")
        if st.button("💾 Salvar etapa 10 (Pular)", key="salvar_10"):
            registrar_etapa("Adendos")

    st.markdown("---")

    # --- Assinaturas Analisadas ---
    st.subheader("✍️ Assinaturas Analisadas (Exames de Confronto)")

    assinaturas = []
    num_assinaturas = st.number_input("Número de Assinaturas/Partes Questionadas", min_value=1, max_value=10, value=st.session_state.get("num_assinaturas", 1), key="num_assinaturas", on_change=save_process_data)

    for i in range(st.session_state.get("num_assinaturas", 1)):
        # Garante que os valores de assinatura estejam no session state
        if f"nome_assinatura_{i}" not in st.session_state: st.session_state[f"nome_assinatura_{i}"] = ""
        if f"obs_assinatura_{i}" not in st.session_state: st.session_state[f"obs_assinatura_{i}"] = ""
        
        with st.expander(f"Assinatura de Análise {i+1}"):
            nome = st.text_input(f"Nome da Pessoa ou Peça Analisada ({i+1})", key=f"nome_assinatura_{i}", on_change=save_process_data)
            observacoes = st.text_area(f"Observações Periciais detalhadas sobre a Peça ({i+1})", key=f"obs_assinatura_{i}", on_change=save_process_data)
            tabela_img = st.file_uploader(f"Tabela/Prancha de Detalhes da Assinatura ({i+1})", type=["png", "jpg", "jpeg"], key=f"tabela_{i}")
            assinaturas.append({
                "nome": nome,
                "observacoes": observacoes,
                "tabela": tabela_img
            })


    # --- Botão Final de Emissão ---
    st.markdown("---")
    st.header("🏁 Geração do Laudo")

    todas_etapas_salvas = len(st.session_state.etapas_concluidas) == 10
    if not todas_etapas_salvas:
        st.warning(f"Faltam {10 - len(st.session_state.etapas_concluidas)} etapas para salvar. Salve todas as etapas (1 a 10) para habilitar a emissão do relatório.")

    if st.button("📤 Emitir Relatório", disabled=not todas_etapas_salvas):
        
        # 1. Preparação dos dados
        caminho_modelo = "template/LAUDO PERICIAL GRAFOTÉCNICO.docx"
        
        primeiro_autor_singular = st.session_state.get("autor_0", "Autor").upper()
        primeiro_reu_singular = st.session_state.get("reu_0", "Réu").upper()

        nome_arquivo_saida = f"output/{st.session_state.numero_processo} - {primeiro_autor_singular} x {primeiro_reu_singular}.docx"
        
        autores_list = [st.session_state[f"autor_{i}"].upper() for i in range(st.session_state.num_autores) if st.session_state.get(f"autor_{i}")]
        reus_list = [st.session_state[f"reu_{i}"].upper() for i in range(st.session_state.num_reus) if st.session_state.get(f"reu_{i}")]

        dados: Dict[str, Union[str, List[Any]]] = {}
        
        # --- LÓGICA DINÂMICA DA CONCLUSÃO (Etapa 6) ---
        autenticos = [d for d in st.session_state.documentos_questionados_list if d.get('RESULTADO') == 'Autêntico']
        falsos = [d for d in st.session_state.documentos_questionados_list if d.get('RESULTADO') == 'Falso']
        
        def formatar_lista_docs(lista: List[Dict[str, str]]) -> str:
            if not lista: return ""
            return "; ".join([
                f"{doc['TIPO_DOCUMENTO']}, nº {doc['NUMERO_CONTRATO']} (fls. {doc['FLS_DOCUMENTOS']})"
                for doc in lista
            ])

        lista_autenticos_str = formatar_lista_docs(autenticos)
        lista_falsos_str = formatar_lista_docs(falsos)

        if len(autenticos) > 0 and len(falsos) > 0:
            conclusao_principal_bloco = (
                "☐ Há autenticidade em parte dos documentos e falsidade em outra parte.\n\n"
                f"As assinaturas nos documentos {lista_autenticos_str} são AUTÊNTICAS.\n\n"
                f"As assinaturas nos documentos {lista_falsos_str} são FALSAS."
            )
        elif len(autenticos) > 0 and len(falsos) == 0:
            conclusao_principal_bloco = (
                "☐ As assinaturas são AUTÊNTICAS.\n\n"
                f"A assinatura de {primeiro_autor_singular}, aposta nos documentos {lista_autenticos_str}, "
                "PROMANOU do punho escritor do(a) Autor(a), posto que reproduzem os caracteres gráficos personalíssimos "
                "e há convergências grafocinéticas suficientes para atestar a autenticidade."
            )
        elif len(falsos) > 0 and len(autenticos) == 0:
            conclusao_principal_bloco = (
                "☐ As assinaturas são FALSAS (Falsidade Gráfica/Falsificação).\n\n"
                f"A assinatura de {primeiro_autor_singular}, aposta nos documentos {lista_falsos_str}, "
                "NÃO PROMANOU do punho escritor do(a) Autor(a), sendo, portanto, FALSA. "
                "Foram constatadas divergências grafocinéticas significativas, indicando a introdução de marcas de esforço e simulação por terceiro."
            )
        else:
            conclusao_principal_bloco = (
                "NÃO CONCLUSIVO: Os exames grafoscópicos não permitiram a emissão de uma conclusão categórica "
                "devido a limitações no material questionado e/ou padrão de confronto."
            )
        
        # --- MONTAGEM FINAL DO DICIONÁRIO 'DADOS' ---
        
        # 1.1 Dados da Etapa 1
        dados.update({
            "NUMERO_PROCESSO": st.session_state.numero_processo,
            "NUMERO_VARA": st.session_state.numero_vara,
            "ID_NOMEACAO": st.session_state.id_nomeacao,
            "COMARCA": st.session_state.comarca.upper(),
            "DATA_LAUDO": formatar_data(st.session_state.data_laudo),
            "DATA_COLHEITA": formatar_data(st.session_state.data_colheita),
            "PRIMEIRO_AUTOR": primeiro_autor_singular,
            "PRIMEIRO_REU": primeiro_reu_singular,
            "AUTORES": ", ".join(autores_list),
            "REUS": ", ".join(reus_list),
        })

        # 1.2 Dados da Etapa 4 (Padrões)
        dados.update({
            "DOC_PADRAO": st.session_state.doc_padrao, 
            "NUM_ESPECIMES": str(st.session_state.num_espécimes),
            "FLS_COLHEITA": st.session_state.fls_colheita,
        })

        # 1.3 Dados da Etapa 4 (Documentos Questionados Dinâmicos)
        for i, doc in enumerate(st.session_state.documentos_questionados_list):
            for key, value in doc.items():
                dados[f"{key}_{i}"] = value 

        # 1.4 Dados da Etapa 6 e 8
        dados.update({
            "BLOCO_CONCLUSAO_DINAMICO": conclusao_principal_bloco,
            "NUM_LAUDAS": str(st.session_state.num_laudas),
            "NUM_LAUDAS_EXTENSO": num2words(st.session_state.num_laudas, lang='pt_BR').upper(),
            "ASSINATURAS": assinaturas
        })
        
        # 1.5 DADOS DINÂMICOS DA ETAPA 7 (QUESITOS)
        
        # Lista para coletar todas as imagens de quesitos
        quesito_images_list: List[Dict[str, Any]] = []

        def formatar_bloco_quesitos(lista_quesitos: List[Dict[str, Any]], parte_tag: str) -> str:
            bloco_texto = ""
            for i, item in enumerate(lista_quesitos):
                bloco_texto += f"**{i+1}. QUESITO:** {item.get('quesito', '')}\n\n"
                bloco_texto += f"**RESPOSTA DO PERITO:** {item.get('resposta', '')}\n\n"
                
                # Inclusão da Tag de Imagem
                if item.get("imagem_anexa"):
                    image_tag = f"[IMAGEM_Q_{parte_tag}_{i}]"
                    bloco_texto += image_tag + "\n\n"
                    # Adiciona o objeto UploadedFile à lista para o word_handler
                    quesito_images_list.append({
                        "tag": image_tag, 
                        "file": item["imagem_anexa"]
                    })
                    
            return bloco_texto.strip()

        # Bloco Autor
        if st.session_state.get("nao_enviou_autor", False):
            bloco_quesitos_autor_final = f"O {primeiro_autor_singular}, parte Autora, não encaminhou quesitos para serem respondidos, nos autos do presente processo."
            fls_quesitos_autor_final = "N/A"
        else:
            bloco_quesitos_autor_final = formatar_bloco_quesitos(st.session_state.quesitos_autor, "AUTOR")
            fls_quesitos_autor_final = st.session_state.fls_quesitos_autor

        # Bloco Réu
        if st.session_state.get("nao_enviou_reu", False):
            bloco_quesitos_reu_final = f"O {primeiro_reu_singular}, parte Ré, não encaminhou quesitos para serem respondidos, nos autos do presente processo."
            fls_quesitos_reu_final = "N/A"
        else:
            bloco_quesitos_reu_final = formatar_bloco_quesitos(st.session_state.quesitos_reu, "REU")
            fls_quesitos_reu_final = st.session_state.fls_quesitos_reu
        
        dados.update({
            "FLS_QUESITOS_AUTOR": fls_quesitos_autor_final,
            "FLS_QUESITOS_REU": fls_quesitos_reu_final,
            
            "BLOCO_QUESITOS_AUTOR": bloco_quesitos_autor_final,
            "BLOCO_QUESITOS_REU": bloco_quesitos_reu_final,
        })
        
        
        # 2. Geração do Laudo
        try:
            os.makedirs("output", exist_ok=True)
            
            # Garante que os dados mais recentes estejam no JSON
            save_process_data()
            
            # Adiciona o novo argumento para o word_handler (assume-se que ele foi atualizado)
            gerar_laudo(
                caminho_modelo, 
                nome_arquivo_saida, 
                dados, 
                st.session_state.anexos, 
                st.session_state.adendos,
                quesito_images_list 
            )
            st.success("✅ Laudo gerado com sucesso!")
            
            with open(nome_arquivo_saida, "rb") as file:
                st.download_button(
                    label="📥 Baixar Laudo",
                    data=file.read(),
                    file_name=os.path.basename(nome_arquivo_saida),
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )
                
        except Exception as e:
            st.error(f"❌ Erro ao gerar o laudo. Verifique se o arquivo modelo está no caminho correto (`{caminho_modelo}`) e se o seu `word_handler` suporta os novos argumentos.")
            st.exception(e)