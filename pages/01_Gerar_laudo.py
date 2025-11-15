import streamlit as st
from utils.word_handler import gerar_laudo
import os
from datetime import date, datetime 
from num2words import num2words
import json
import shutil 
from typing import List, Dict, Any, Union
import io # Para manipulação de bytes de imagens

# --- NOVO: IMPORTS PARA GOOGLE SHEETS ---
import gspread 
from gspread_dataframe import set_with_dataframe, get_dataframe
import pandas as pd
# ----------------------------------------

# --- Configuração Inicial e Tema ---
st.set_page_config(page_title="Gerador de Laudo Grafotécnico", layout="wide")

# Caminho para o modelo Word (DEVE EXISTIR na pasta 'template/')
caminho_modelo = "template/LAUDO PERICIAL GRAFOTÉCNICO.docx"
DATA_FOLDER = "data" # Mantido para fins de estrutura, mas não será usado para persistência

# --- Funções de Ajuda e Lógica de Componentes ---

def _reset_processo_completo():
    """Reinicia o estado de sessão para um novo processo."""
    st.session_state.etapas_concluidas = set()
    st.session_state.editing_etapa_1 = True
    
    # Lista de chaves a serem reiniciadas (incluindo todas as variáveis usadas nos formulários)
    chaves_para_reset = [
        "numero_processo", "data_laudo", "data_colheita", "autor_0", "reu_0", 
        "tipo_justica", "vara", "comarca", "obj_pericia", 
        "num_docs_questionados", "documentos_questionados_list",
        "num_docs_paradigmas_pca", "num_docs_paradigmas_pce", 
        "documentos_paradigmas_pca_list", "documentos_paradigmas_pce_list",
        "doc_questionado_final", "doc_padrao_final", 
        "descricao_analise_padrao", "descricao_confronto", 
        "conclusao_final", "conclusao_tipo", "docs_autenticos_conc", "docs_falsos_conc", 
        "fls_quesitos_autor", "fls_quesitos_reu", 
        "quesitos_autor", "quesitos_reu", "num_laudas", "assinaturas",
        "anexos", "adendos", "process_to_load", "quesito_counter_autor", "quesito_counter_reu"
    ]
    
    for key in chaves_para_reset:
        if key in st.session_state:
            # Reseta listas para vazio, sets para vazio, strings para vazio, e None para outros
            if isinstance(st.session_state[key], list):
                st.session_state[key] = []
            elif isinstance(st.session_state[key], set):
                st.session_state[key] = set()
            elif isinstance(st.session_state[key], str):
                st.session_state[key] = ""
            else:
                st.session_state[key] = None

    # Inicializações específicas para valores padrão
    st.session_state.num_laudas = 10
    st.session_state.num_docs_questionados = 1
    st.session_state.documentos_questionados_list = []
    st.session_state.quesitos_autor = []
    st.session_state.quesitos_reu = []
    st.session_state.anexos = []
    st.session_state.adendos = []
    
    st.toast("Novo processo iniciado. Todos os campos foram limpos.")
    st.rerun()

def _add_quesito(tipo: str):
    """Adiciona um novo quesito ao estado de sessão."""
    
    # Garante que o contador exista
    if f"quesito_counter_{tipo}" not in st.session_state:
        st.session_state[f"quesito_counter_{tipo}"] = 1
        
    # Inicializa a lista se não existir
    if f"quesitos_{tipo}" not in st.session_state:
        st.session_state[f"quesitos_{tipo}"] = []
        
    st.session_state[f"quesitos_{tipo}"].append({
        "N": st.session_state[f"quesito_counter_{tipo}"],
        "Quesito": f"[Quesito {st.session_state[f'quesito_counter_{tipo}']}]",
        "Resposta": "[Resposta do Perito]",
        "anexar_imagem": False,
        "imagem_anexa": None, # Streamlit UploadedFile object
        "descricao_imagem": ""
    })
    st.session_state[f"quesito_counter_{tipo}"] += 1

def _display_dados_processo():
    """Exibe um resumo dos dados do processo na barra lateral."""
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📋 Processo Atual")
    
    processo_num = st.session_state.get("numero_processo")
    if processo_num:
        st.sidebar.metric("Nº do Processo", processo_num)
        st.sidebar.metric("Autor", st.session_state.get("autor_0", "N/A"))
        st.sidebar.metric("Réu", st.session_state.get("reu_0", "N/A"))
        st.sidebar.metric("Status", f"{len(st.session_state.etapas_concluidas)}/8 Concluídas")
        
        if st.sidebar.button("Limpar Processo Atual", type="primary"):
            _reset_processo_completo()
    else:
        st.sidebar.info("Nenhum processo em edição.")

# --- NOVO: FUNÇÕES DE PERSISTÊNCIA VIA GOOGLE SHEETS ---

@st.cache_resource(ttl="1h")
def get_gspread_client():
    """Conecta ao Google Sheets usando as credenciais do Streamlit Secrets."""
    try:
        # Tenta conectar usando as credenciais do secrets.toml
        credentials = st.secrets["gcp_service_account"]
        gc = gspread.service_account_from_dict(credentials)
        return gc
    except Exception as e:
        # Se falhar, é porque a chave secrets["gcp_service_account"] não foi configurada
        # Isso é esperado em desenvolvimento local ou se a configuração do Cloud estiver errada
        st.warning("⚠️ Não foi possível conectar ao Google Sheets (Verifique `secrets.toml`). O salvamento persistente está DESATIVADO.")
        return None

gc = get_gspread_client()

def clean_quesitos_for_json(quesitos_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove objetos não serializáveis (UploadedFile) dos quesitos antes de salvar."""
    cleaned = []
    for q in quesitos_list:
        q_clean = q.copy()
        # Remove UploadedFile (não é serializável)
        q_clean.pop("imagem_anexa", None) 
        # Tenta converter o objeto UploadedFile em bytes (opcional, mas mais seguro é remover)
        # q_clean["imagem_anexa_bytes"] = q.get("imagem_anexa").read() if q.get("imagem_anexa") else None
        cleaned.append(q_clean)
    return cleaned

def clean_anexos_for_json(anexos_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove objetos não serializáveis (UploadedFile) dos anexos antes de salvar."""
    cleaned = []
    for a in anexos_list:
        a_clean = a.copy()
        # Remove UploadedFile (não é serializável)
        a_clean.pop("arquivo_anexo", None) 
        cleaned.append(a_clean)
    return cleaned

def save_process_data():
    """Salva o processo no Google Sheets (Index) e armazena todos os dados em JSON string."""
    
    if not st.session_state.get("numero_processo") or not gc:
        # Não salva se não houver número de processo ou se a conexão falhou
        return
    
    processo_num = st.session_state.numero_processo
    
    # 1. Preparar o objeto COMPLETO (Será serializado e salvo na coluna 'dados_completos_json')
    data_laudo_obj = st.session_state.get("data_laudo", date.today())
    data_laudo_str = data_laudo_obj.strftime("%d/%m/%Y") if isinstance(data_laudo_obj, date) else str(data_laudo_obj)
    
    full_data = {
        # Dados de INDEX (para busca rápida)
        "numero_processo": processo_num,
        "data_laudo": data_laudo_str,
        "autor_0": st.session_state.get("autor_0", "").upper(),
        "reu_0": st.session_state.get("reu_0", "").upper(),
        
        # O resto dos dados do session_state (limpando objetos não serializáveis)
        "etapas_concluidas": list(st.session_state.etapas_concluidas),
        
        # Estruturas complexas (limpas)
        "quesitos_autor": clean_quesitos_for_json(st.session_state.get("quesitos_autor", [])),
        "quesitos_reu": clean_quesitos_for_json(st.session_state.get("quesitos_reu", [])),
        "anexos": clean_anexos_for_json(st.session_state.get("anexos", [])),
        "adendos": clean_anexos_for_json(st.session_state.get("adendos", [])),
        
        "documentos_questionados_list": st.session_state.get("documentos_questionados_list", []),
        "documentos_paradigmas_pca_list": st.session_state.get("documentos_paradigmas_pca_list", []),
        "documentos_paradigmas_pce_list": st.session_state.get("documentos_paradigmas_pce_list", []),
        
        # Salva todos os valores simples (strings, números, booleanos)
        **{k: v for k, v in st.session_state.items() if isinstance(v, (str, int, float, bool))}
    }
    
    # 2. Conectar à Planilha e Salvar
    try:
        sh = gc.open_by_url(st.secrets["spreadsheet_url"])
        worksheet = sh.worksheet("Página1") # Assume o nome padrão da aba
        
        # Ler todos os dados existentes
        # Esta função lê apenas as colunas com dados, se o DF estiver vazio, cria-se um novo
        df_existing = get_dataframe(worksheet)
        if df_existing.empty:
            df_existing = pd.DataFrame(columns=["numero_processo", "data_laudo", "autor_0", "reu_0", "dados_completos_json"])
            
        # Criar o novo registro para o INDEX
        new_record = {
            "numero_processo": processo_num,
            "data_laudo": full_data["data_laudo"],
            "autor_0": full_data["autor_0"],
            "reu_0": full_data["reu_0"],
            "dados_completos_json": json.dumps(full_data, ensure_ascii=False)
        }
        
        df_new = pd.DataFrame([new_record])
        
        # Atualizar ou Adicionar
        if processo_num in df_existing['numero_processo'].values:
            idx = df_existing[df_existing['numero_processo'] == processo_num].index[0]
            df_existing.loc[idx] = new_record
            df_final = df_existing
        else:
            df_final = pd.concat([df_existing, df_new], ignore_index=True)

        # Escrever de volta para a planilha
        set_with_dataframe(worksheet, df_final, include_index=False)
        
        st.session_state["last_saved_process"] = processo_num
        st.toast("💾 Dados salvos na Planilha Google (Cloud)!")

    except Exception as e:
        st.error("❌ Erro ao salvar dados no Google Sheets. Verifique o compartilhamento e a URL.")
        st.exception(e)
    

def load_process_data(processo_num: str, set_editing_false: bool = True):
    """
    Carrega os dados de um processo salvo no Google Sheets para o Session State.
    """
    if not gc:
        st.error("Conexão com Google Sheets não estabelecida. Não foi possível carregar o processo.")
        return

    try:
        sh = gc.open_by_url(st.secrets["spreadsheet_url"])
        worksheet = sh.worksheet("Página1") 
        df = get_dataframe(worksheet)
        
        # Limpar NaN gerados por linhas vazias
        df = df.dropna(subset=['numero_processo']).reset_index(drop=True)
        
        record = df[df['numero_processo'] == processo_num]
        
        if record.empty:
            st.error(f"Processo {processo_num} não encontrado na Planilha.")
            return

        json_data_str = record['dados_completos_json'].iloc[0]
        data = json.loads(json_data_str)
            
        # Limpa o estado atual antes de carregar
        _reset_processo_completo() 
        
        # Carrega todos os dados do JSON para o session state
        for key, value in data.items():
            if key in ["data_laudo", "data_colheita"] and isinstance(value, str):
                # Converte strings de data de volta para objetos date
                try: 
                    st.session_state[key] = datetime.strptime(value, "%d/%m/%Y").date()
                except: 
                    st.session_state[key] = date.today()
            elif key == "etapas_concluidas":
                st.session_state.etapas_concluidas = set(value)
            # Os campos 'imagem_anexa' e 'arquivo_anexo' (UploadedFile) são ignorados,
            # pois não é possível armazenar arquivos binários grandes no Sheets de forma prática.
            # O usuário precisará anexar as imagens e arquivos novamente ao carregar.
            else:
                st.session_state[key] = value

        # Lógica de edição
        if set_editing_false:
            st.session_state.editing_etapa_1 = False 
            st.toast(f"✅ Processo {processo_num} carregado com sucesso! (Imagens e arquivos devem ser anexados novamente)")
        else:
            st.session_state.editing_etapa_1 = True
            st.toast(f"✅ Dados de {processo_num} recarregados. Etapa 1 liberada para edição!")
            
        st.rerun() 

    except Exception as e:
        st.error("❌ Erro ao carregar dados do Google Sheets.")
        st.exception(e)
        
def _get_process_list() -> List[str]:
    """Retorna a lista de números de processo disponíveis na Planilha."""
    if not gc:
        return []
    try:
        sh = gc.open_by_url(st.secrets["spreadsheet_url"])
        worksheet = sh.worksheet("Página1") 
        df = get_dataframe(worksheet)
        
        # Filtra valores vazios e retorna como lista
        process_list = df['numero_processo'].dropna().tolist()
        return process_list
    except Exception:
        # Erro de URL, planilha, ou credenciais
        return []
# ---------------------------------------------


# --- Inicialização do Estado de Sessão (continuação) ---
if "etapas_concluidas" not in st.session_state:
    st.session_state.etapas_concluidas = set()
if "theme" not in st.session_state:
    st.session_state.theme = "light" 
if "editing_etapa_1" not in st.session_state:
    st.session_state.editing_etapa_1 = True
    
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
if "quesito_counter_autor" not in st.session_state:
    st.session_state.quesito_counter_autor = 1
if "quesito_counter_reu" not in st.session_state:
    st.session_state.quesito_counter_reu = 1

# Estruturas para anexos e adendos (arquivos binários devem ser anexados a cada sessão)
if "anexos" not in st.session_state:
    st.session_state.anexos = []
if "adendos" not in st.session_state:
    st.session_state.adendos = []


# --- SIDEBAR (CARREGAMENTO/SALVAMENTO) ---
with st.sidebar:
    st.header("📂 Gerenciamento de Processos")
    
    # NOVO: Carregar Processo Salvo
    processos_disponiveis = _get_process_list()
    if processos_disponiveis:
        st.markdown("##### Carregar Processo Salvo (Cloud)")
        process_to_load = st.selectbox(
            "Selecione o N° do Processo:",
            options=[""] + processos_disponiveis,
            key="process_to_load"
        )
        if st.button("Carregar Processo", use_container_width=True, disabled=(process_to_load == "")):
            load_process_data(process_to_load)
    else:
        st.info("Nenhum processo salvo na nuvem.")
    
    _display_dados_processo()


# --- CORPO PRINCIPAL DO APLICATIVO ---
st.title("✍️ Laudo Pericial Grafotécnico")

# --------------------------
# ETAPA 1: Dados do Processo (Sempre visível, mas editável ou bloqueada)
# --------------------------
if st.session_state.editing_etapa_1:
    with st.expander("ETAPA 1: Dados do Processo e Objeto da Perícia", expanded=True):
        st.markdown("Preencha os dados básicos do processo judicial.")
        
        with st.form(key="form_etapa_1"):
            col1, col2 = st.columns(2)
            
            with col1:
                st.session_state.numero_processo = st.text_input(
                    "Número do Processo (Usado para Salvar)",
                    value=st.session_state.get("numero_processo", ""),
                    key="numero_processo_input"
                ).strip().upper()
                
                st.session_state.autor_0 = st.text_input(
                    "Nome do Autor(a)",
                    value=st.session_state.get("autor_0", ""),
                    key="autor_0_input"
                ).strip().upper()
                
                st.session_state.reu_0 = st.text_input(
                    "Nome do Réu (Ré)",
                    value=st.session_state.get("reu_0", ""),
                    key="reu_0_input"
                ).strip().upper()
            
            with col2:
                st.session_state.tipo_justica = st.selectbox(
                    "Tipo de Justiça",
                    options=["Estadual", "Federal", "Trabalhista"],
                    index=["Estadual", "Federal", "Trabalhista"].index(st.session_state.get("tipo_justica", "Estadual"))
                )
                st.session_state.data_laudo = st.date_input(
                    "Data do Laudo",
                    value=st.session_state.get("data_laudo", date.today())
                )
                
                # Campos adicionais
                st.session_state.vara = st.text_input(
                    "Vara",
                    value=st.session_state.get("vara", "Vara Cível")
                )
                st.session_state.comarca = st.text_input(
                    "Comarca",
                    value=st.session_state.get("comarca", "Rio de Janeiro/RJ")
                )
            
            st.session_state.obj_pericia = st.text_area(
                "Objeto da Perícia (Resumo da Introdução)",
                value=st.session_state.get("obj_pericia", "Verificação da autenticidade ou falsidade de assinaturas apostas em [DESCREVER DOCUMENTO] questionadas pelo(a) [AUTOR/RÉU]."),
                height=100
            )

            # Botão de conclusão da Etapa 1
            if st.form_submit_button("Concluir Etapa 1 e Salvar"):
                if not st.session_state.numero_processo or not st.session_state.autor_0 or not st.session_state.reu_0:
                    st.error("Preencha o Número do Processo, Autor e Réu para prosseguir.")
                else:
                    st.session_state.etapas_concluidas.add(1)
                    st.session_state.editing_etapa_1 = False
                    save_process_data() # NOVO: Salva no Sheets
                    st.success("Etapa 1 concluída e bloqueada.")
                    st.rerun()

else:
    # Mostra os dados básicos salvos e botão de edição
    st.markdown(f"**Processo:** `{st.session_state.numero_processo}` | **Autor:** `{st.session_state.autor_0}` | **Réu:** `{st.session_state.reu_0}`")
    if st.button("✏️ Editar Etapa 1 (Desbloquear)", key="edit_etapa_1"):
        st.session_state.editing_etapa_1 = True
        st.toast("Etapa 1 liberada para edição.")
        st.rerun()
    st.markdown("---")


# --------------------------
# ETAPA 2: Documentos Questionados (Condicional)
# --------------------------
if 1 in st.session_state.etapas_concluidas:
    with st.expander(f"ETAPA 2: Documentos Questionados (Status: {'✅' if 2 in st.session_state.etapas_concluidas else '⏳'})", expanded=(2 not in st.session_state.etapas_concluidas)):
        st.markdown("Liste os documentos que contêm as assinaturas cuja autoria é questionada.")
        
        # Campo para o usuário definir quantos documentos ele quer listar
        st.session_state.num_docs_questionados = st.number_input(
            "Quantos documentos questionados serão listados?",
            min_value=1, 
            value=st.session_state.get("num_docs_questionados", 1), 
            step=1, 
            key="num_docs_questionados_input"
        )
        
        # Garante que a lista tenha o tamanho correto
        while len(st.session_state.documentos_questionados_list) < st.session_state.num_docs_questionados:
            st.session_state.documentos_questionados_list.append({
                "TIPO_DOCUMENTO": "", 
                "FLS_DOCUMENTOS": "", 
                "RESULTADO": "Não Informado"
            })
        st.session_state.documentos_questionados_list = st.session_state.documentos_questionados_list[:st.session_state.num_docs_questionados]

        with st.form(key="form_etapa_2"):
            docs_q_temp = st.session_state.documentos_questionados_list.copy()
            
            for i in range(st.session_state.num_docs_questionados):
                st.subheader(f"Documento Questionado #{i+1}")
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    docs_q_temp[i]["TIPO_DOCUMENTO"] = st.text_input(
                        "Tipo do Documento",
                        value=docs_q_temp[i].get("TIPO_DOCUMENTO", ""),
                        key=f"doc_q_{i}_tipo"
                    ).strip()
                with col2:
                    docs_q_temp[i]["FLS_DOCUMENTOS"] = st.text_input(
                        "Fls. (Números das Folhas/Páginas)",
                        value=docs_q_temp[i].get("FLS_DOCUMENTOS", ""),
                        key=f"doc_q_{i}_fls"
                    ).strip()
                with col3:
                    docs_q_temp[i]["RESULTADO"] = st.selectbox(
                        "Resultado Previsto (Para auxiliar o texto da Conclusão)",
                        options=["Não Informado", "Autêntico", "Falso"],
                        index=["Não Informado", "Autêntico", "Falso"].index(docs_q_temp[i].get("RESULTADO", "Não Informado")),
                        key=f"doc_q_{i}_resultado"
                    )
                st.markdown("---")
            
            # Campo final da etapa 2 (resumo)
            st.session_state.doc_questionado_final = st.text_area(
                "Descrição Final dos Documentos Questionados (Para o Laudo)",
                value=st.session_state.get("doc_questionado_final", "Os documentos submetidos ao exame pericial (Padrão Questionado - PQ) são os seguintes, a saber: [LISTA DE DOCUMENTOS ACIMA]."),
                height=100
            )

            if st.form_submit_button("Concluir Etapa 2"):
                st.session_state.documentos_questionados_list = docs_q_temp
                st.session_state.etapas_concluidas.add(2)
                save_process_data()
                st.success("Etapa 2 concluída e salva.")
                st.rerun()

# --------------------------
# ETAPA 3: Documentos Padrão (Paradigmas)
# --------------------------
if 2 in st.session_state.etapas_concluidas:
    with st.expander(f"ETAPA 3: Documentos Padrão (Status: {'✅' if 3 in st.session_state.etapas_concluidas else '⏳'})", expanded=(3 not in st.session_state.etapas_concluidas)):
        st.markdown("Liste os documentos usados para confronto (Padrões de Confronto - PC).")
        
        # Lógica de input para documentos Padrão Colhido (PCA) e Padrão Encontrado (PCE)
        st.session_state.num_docs_paradigmas_pca = st.number_input("Nº de Documentos Padrão COLHIDOS (PCA)", min_value=0, value=st.session_state.get("num_docs_paradigmas_pca", 0), step=1)
        st.session_state.num_docs_paradigmas_pce = st.number_input("Nº de Documentos Padrão ENCONTRADOS (PCE)", min_value=0, value=st.session_state.get("num_docs_paradigmas_pce", 0), step=1)

        # Lógica para garantir o tamanho correto das listas de paradigmas
        def _resize_doc_list(key, size):
            current_list = st.session_state.get(key, [])
            while len(current_list) < size:
                current_list.append({"TIPO_DOCUMENTO": "", "FLS_DOCUMENTOS": ""})
            st.session_state[key] = current_list[:size]

        _resize_doc_list("documentos_paradigmas_pca_list", st.session_state.num_docs_paradigmas_pca)
        _resize_doc_list("documentos_paradigmas_pce_list", st.session_state.num_docs_paradigmas_pce)

        with st.form(key="form_etapa_3"):
            # Formulário para PCA
            st.subheader("A. Padrões Colhidos no Ato Pericial (PCA)")
            pca_temp = st.session_state.documentos_paradigmas_pca_list.copy()
            if pca_temp:
                for i in range(len(pca_temp)):
                    col1, col2 = st.columns(2)
                    with col1:
                        pca_temp[i]["TIPO_DOCUMENTO"] = st.text_input(f"Tipo do Documento PCA #{i+1}", value=pca_temp[i].get("TIPO_DOCUMENTO", ""), key=f"doc_pca_{i}_tipo")
                    with col2:
                        pca_temp[i]["FLS_DOCUMENTOS"] = st.text_input(f"Fls. PCA #{i+1}", value=pca_temp[i].get("FLS_DOCUMENTOS", ""), key=f"doc_pca_{i}_fls")
            else:
                st.info("Nenhum PCA a ser listado.")
            
            # Formulário para PCE
            st.subheader("B. Padrões Encontrados nos Autos (PCE)")
            pce_temp = st.session_state.documentos_paradigmas_pce_list.copy()
            if pce_temp:
                for i in range(len(pce_temp)):
                    col1, col2 = st.columns(2)
                    with col1:
                        pce_temp[i]["TIPO_DOCUMENTO"] = st.text_input(f"Tipo do Documento PCE #{i+1}", value=pce_temp[i].get("TIPO_DOCUMENTO", ""), key=f"doc_pce_{i}_tipo")
                    with col2:
                        pce_temp[i]["FLS_DOCUMENTOS"] = st.text_input(f"Fls. PCE #{i+1}", value=pce_temp[i].get("FLS_DOCUMENTOS", ""), key=f"doc_pce_{i}_fls")
            else:
                st.info("Nenhum PCE a ser listado.")
            
            # Campo final da etapa 3 (resumo)
            st.session_state.doc_padrao_final = st.text_area(
                "Descrição Final dos Documentos Padrão (Para o Laudo)",
                value=st.session_state.get("doc_padrao_final", "Os documentos padrão submetidos ao exame pericial (Padrão de Confronto - PC) são os seguintes, a saber: [LISTA DE DOCUMENTOS ACIMA]."),
                height=100
            )

            if st.form_submit_button("Concluir Etapa 3"):
                st.session_state.documentos_paradigmas_pca_list = pca_temp
                st.session_state.documentos_paradigmas_pce_list = pce_temp
                st.session_state.etapas_concluidas.add(3)
                save_process_data()
                st.success("Etapa 3 concluída e salva.")
                st.rerun()

# --------------------------
# ETAPA 4: Exames Periciais e Metodologia
# --------------------------
if 3 in st.session_state.etapas_concluidas:
    with st.expander(f"ETAPA 4: Exames Periciais (Status: {'✅' if 4 in st.session_state.etapas_concluidas else '⏳'})", expanded=(4 not in st.session_state.etapas_concluidas)):
        st.markdown("Preencha as seções de Análise dos Padrões e Confronto Grafoscópico.")

        with st.form(key="form_etapa_4"):
            st.subheader("5.1. Análise dos Paradigmas")
            st.session_state.descricao_analise_padrao = st.text_area(
                "Descrição da Análise",
                value=st.session_state.get("descricao_analise_padrao", "O material de confronto (Padrão) foi submetido a exames técnicos, onde se verificou [ADJETIVOS E CARACTERÍSTICAS POSITIVAS/NEGATIVAS]."),
                height=150
            )

            st.subheader("5.2. Confronto Grafoscópico")
            st.session_state.descricao_confronto = st.text_area(
                "Descrição do Confronto",
                value=st.session_state.get("descricao_confronto", "Após a análise dos elementos de ordem geral (calibre, andamento, velocidade, inclinação, etc.) e de ordem particular (construção gráfica, ataque, remate, etc.), o confronto entre o Padrão Questionado (PQ) e o Padrão de Confronto (PC) revelou [DESCREVER CONVERGÊNCIAS/DIVERGÊNCIAS ENCONTRADAS]."),
                height=300
            )

            if st.form_submit_button("Concluir Etapa 4"):
                st.session_state.etapas_concluidas.add(4)
                save_process_data()
                st.success("Etapa 4 concluída e salva.")
                st.rerun()

# --------------------------
# ETAPA 5: Conclusão
# --------------------------
if 4 in st.session_state.etapas_concluidas:
    with st.expander(f"ETAPA 5: Conclusão (Status: {'✅' if 5 in st.session_state.etapas_concluidas else '⏳'})", expanded=(5 not in st.session_state.etapas_concluidas)):
        st.markdown("Defina a conclusão final do laudo.")
        
        with st.form(key="form_etapa_5"):
            st.session_state.conclusao_tipo = st.radio(
                "Tipo de Conclusão",
                options=["Autenticidade Total", "Falsidade Total", "Mista (Parte autêntica, parte falsa)"],
                index=["Autenticidade Total", "Falsidade Total", "Mista (Parte autêntica, parte falsa)"].index(st.session_state.get("conclusao_tipo", "Autenticidade Total"))
            )

            if st.session_state.conclusao_tipo == "Mista (Parte autêntica, parte falsa)":
                st.session_state.docs_autenticos_conc = st.text_input("Documentos AUTÊNTICOS na Conclusão (Ex: Cédula A, Contrato B)", value=st.session_state.get("docs_autenticos_conc", ""))
                st.session_state.docs_falsos_conc = st.text_input("Documentos FALSOS na Conclusão (Ex: Cheque 123, Promissória X)", value=st.session_state.get("docs_falsos_conc", ""))

            st.session_state.conclusao_final = st.text_area(
                "Texto Descritivo da Conclusão",
                value=st.session_state.get("conclusao_final", "Diante do exposto e das análises realizadas, concluo que a assinatura questionada é [AUTÊNTICA/FALSA], tendo em vista [DESCREVER OS ELEMENTOS FINAIS]."),
                height=200
            )

            if st.form_submit_button("Concluir Etapa 5"):
                st.session_state.etapas_concluidas.add(5)
                save_process_data()
                st.success("Etapa 5 concluída e salva.")
                st.rerun()

# --------------------------
# ETAPA 6: Quesitos (Autor)
# --------------------------
if 5 in st.session_state.etapas_concluidas:
    with st.expander(f"ETAPA 6: Quesitos do Autor (Status: {'✅' if 6 in st.session_state.etapas_concluidas else '⏳'})", expanded=(6 not in st.session_state.etapas_concluidas)):
        st.markdown("Preencha as Fls. e o quadro de Respostas aos Quesitos da Parte Autora.")
        
        with st.form(key="form_etapa_6"):
            st.session_state.fls_quesitos_autor = st.text_input(
                "Fls. dos Quesitos da Parte Autora nos Autos", 
                value=st.session_state.get("fls_quesitos_autor", "NÚMEROS")
            )
            
            st.subheader("Quadro de Quesitos e Respostas")
            
            # Edição dos Quesitos
            quesitos_autor_temp = st.session_state.quesitos_autor.copy()
            for i in range(len(quesitos_autor_temp)):
                quesito = quesitos_autor_temp[i]
                
                st.markdown(f"#### Quesito Nº {quesito['N']}")
                
                # Campos de edição
                quesito['Quesito'] = st.text_area(f"Transcrever Quesito {quesito['N']}", value=quesito['Quesito'], key=f"q_autor_{i}_quesito")
                quesito['Resposta'] = st.text_area(f"Resposta do Perito {quesito['N']}", value=quesito['Resposta'], key=f"q_autor_{i}_resposta")
                
                # Lógica para Imagem
                col_img_1, col_img_2 = st.columns(2)
                with col_img_1:
                    quesito['anexar_imagem'] = st.checkbox("Anexar Imagem/Demonstração", value=quesito.get('anexar_imagem', False), key=f"q_autor_{i}_check")
                
                if quesito['anexar_imagem']:
                    with col_img_2:
                        quesito['imagem_anexa'] = st.file_uploader(f"Anexar Imagem para Quesito {quesito['N']}", type=["png", "jpg", "jpeg"], key=f"q_autor_{i}_upload")
                    
                    quesito['descricao_imagem'] = st.text_input("Descrição da Imagem/Gráfico", value=quesito.get('descricao_imagem', ""), key=f"q_autor_{i}_desc_img")
                
                st.markdown("---")

            # Botão para adicionar novo quesito
            if st.form_submit_button("Adicionar Novo Quesito"):
                _add_quesito("autor")
                st.rerun() # Rerun para o novo campo aparecer
            
            # Botão de conclusão da etapa
            if st.form_submit_button("Concluir Etapa 6"):
                st.session_state.quesitos_autor = quesitos_autor_temp
                st.session_state.etapas_concluidas.add(6)
                save_process_data()
                st.success("Etapa 6 concluída e salva.")
                st.rerun()

# --------------------------
# ETAPA 7: Quesitos (Réu)
# --------------------------
if 6 in st.session_state.etapas_concluidas:
    with st.expander(f"ETAPA 7: Quesitos do Réu (Status: {'✅' if 7 in st.session_state.etapas_concluidas else '⏳'})", expanded=(7 not in st.session_state.etapas_concluidas)):
        st.markdown("Preencha as Fls. e o quadro de Respostas aos Quesitos da Parte Ré.")

        with st.form(key="form_etapa_7"):
            st.session_state.fls_quesitos_reu = st.text_input(
                "Fls. dos Quesitos da Parte Ré nos Autos", 
                value=st.session_state.get("fls_quesitos_reu", "NÚMEROS")
            )
            
            st.subheader("Quadro de Quesitos e Respostas")
            
            # Edição dos Quesitos
            quesitos_reu_temp = st.session_state.quesitos_reu.copy()
            for i in range(len(quesitos_reu_temp)):
                quesito = quesitos_reu_temp[i]
                
                st.markdown(f"#### Quesito Nº {quesito['N']}")
                
                # Campos de edição
                quesito['Quesito'] = st.text_area(f"Transcrever Quesito {quesito['N']}", value=quesito['Quesito'], key=f"q_reu_{i}_quesito")
                quesito['Resposta'] = st.text_area(f"Resposta do Perito {quesito['N']}", value=quesito['Resposta'], key=f"q_reu_{i}_resposta")
                
                # Lógica para Imagem
                col_img_1, col_img_2 = st.columns(2)
                with col_img_1:
                    quesito['anexar_imagem'] = st.checkbox("Anexar Imagem/Demonstração", value=quesito.get('anexar_imagem', False), key=f"q_reu_{i}_check")
                
                if quesito['anexar_imagem']:
                    with col_img_2:
                        quesito['imagem_anexa'] = st.file_uploader(f"Anexar Imagem para Quesito {quesito['N']}", type=["png", "jpg", "jpeg"], key=f"q_reu_{i}_upload")
                    
                    quesito['descricao_imagem'] = st.text_input("Descrição da Imagem/Gráfico", value=quesito.get('descricao_imagem', ""), key=f"q_reu_{i}_desc_img")
                
                st.markdown("---")

            # Botão para adicionar novo quesito
            if st.form_submit_button("Adicionar Novo Quesito do Réu"):
                _add_quesito("reu")
                st.rerun()
                
            # Botão de conclusão da etapa
            if st.form_submit_button("Concluir Etapa 7"):
                st.session_state.quesitos_reu = quesitos_reu_temp
                st.session_state.etapas_concluidas.add(7)
                save_process_data()
                st.success("Etapa 7 concluída e salva.")
                st.rerun()

# --------------------------
# ETAPA 8: Encerramento e Assinatura
# --------------------------
if 7 in st.session_state.etapas_concluidas:
    with st.expander(f"ETAPA 8: Anexos, Adendos e Encerramento (Status: {'✅' if 8 in st.session_state.etapas_concluidas else '⏳'})", expanded=(8 not in st.session_state.etapas_concluidas)):
        st.markdown("Defina a numeração final de páginas e anexe documentos adicionais.")
        
        with st.form(key="form_etapa_8"):
            
            # --- Seção de Anexos (Arquivos) ---
            st.subheader("Anexos (Arquivos PDF/DOCX)")
            st.markdown("Anexos serão listados no laudo, mas os arquivos não são incluídos no DOCX final.")
            
            def _add_anexo(tipo_lista):
                st.session_state[tipo_lista].append({
                    "DESCRICAO": "Descrever o documento", 
                    "ARQUIVO": None # UploadedFile
                })

            if st.button("Adicionar Anexo", key="add_anexo"):
                _add_anexo("anexos")
            
            anexos_temp = st.session_state.anexos.copy()
            for i, anexo in enumerate(anexos_temp):
                col1, col2 = st.columns([3, 1])
                with col1:
                    anexo["DESCRICAO"] = st.text_input(f"Descrição do Anexo {i+1}", value=anexo.get("DESCRICAO", ""), key=f"anexo_desc_{i}")
                with col2:
                    # Este campo só armazena o objeto na sessão, não será persistido no Sheets
                    anexo["ARQUIVO"] = st.file_uploader(f"Anexar Arquivo (Opcional) {i+1}", type=["pdf", "docx"], key=f"anexo_file_{i}")
            st.session_state.anexos = anexos_temp

            # --- Seção de Adendos (Imagens/Gráficos) ---
            st.subheader("Adendos (Imagens no Corpo do Laudo)")
            st.markdown("Adendos serão listados e, opcionalmente, podem ser incluídos no DOCX final se a lógica `word_handler.py` suportar.")
            
            def _add_adendo():
                st.session_state.adendos.append({
                    "DESCRICAO": "Descrever a Imagem/Gráfico", 
                    "ARQUIVO": None # UploadedFile
                })
            
            if st.button("Adicionar Adendo", key="add_adendo"):
                _add_adendo()
                
            adendos_temp = st.session_state.adendos.copy()
            for i, adendo in enumerate(adendos_temp):
                col1, col2 = st.columns([3, 1])
                with col1:
                    adendo["DESCRICAO"] = st.text_input(f"Descrição do Adendo {i+1}", value=adendo.get("DESCRICAO", ""), key=f"adendo_desc_{i}")
                with col2:
                    adendo["ARQUIVO"] = st.file_uploader(f"Anexar Imagem (PNG/JPG) {i+1}", type=["png", "jpg", "jpeg"], key=f"adendo_file_{i}")
            st.session_state.adendos = adendos_temp
            
            # --- Numeração de Laudas e Assinatura ---
            st.subheader("Encerramento")
            st.session_state.num_laudas = st.number_input(
                "Número de Laudas (Páginas Finais)", 
                min_value=1, 
                value=st.session_state.get("num_laudas", 10), 
                step=1
            )
            
            st.session_state.assinaturas = st.text_area(
                "Texto do Encerramento (Assinaturas e Declaração)",
                value=st.session_state.get("assinaturas", "Eu, [SEU NOME COMPLETO], Perito(a) Judicial, declaro que as informações contidas neste Laudo são verdadeiras e que cumpri com meu dever."),
                height=150
            )

            if st.form_submit_button("Concluir Etapa 8"):
                st.session_state.etapas_concluidas.add(8)
                save_process_data()
                st.success("Etapa 8 concluída e salva.")
                st.rerun()


# --------------------------
# GERAÇÃO FINAL DO LAUDO (Botão Principal)
# --------------------------
if 8 in st.session_state.etapas_concluidas:
    
    st.markdown("---")
    st.header("🎉 Gerar Laudo Final")
    st.info("Todos os passos foram concluídos. Pressione o botão para gerar o documento Word (.docx).")

    if st.button("GERAR LAUDO E BAIXAR DOCUMENTO", type="primary", use_container_width=True):
        
        # 0. Garante que os últimos dados estejam salvos antes de gerar
        save_process_data() 
        
        # 1. Agrupa os dados para o word_handler
        nome_arquivo_saida = os.path.join("output", f"LAUDO_{st.session_state.numero_processo}.docx")
        
        # Lista para coletar as imagens dos quesitos (para o word_handler)
        quesito_images_list = []
        
        # Função interna para gerar a string de blocos de quesitos (tabela)
        def _generate_quesito_block(quesitos: list) -> str:
            bloco = "Nº,Quesito,Resposta do Perito\r\n"
            for q in quesitos:
                bloco += f"{q['N']},\"{q['Quesito']}\",\"{q['Resposta']}\"\r\n"
                
                # Se houver imagem, adiciona à lista para ser processada pelo word_handler
                if q['anexar_imagem'] and q['imagem_anexa']:
                    quesito_images_list.append({
                        "id": f"Q_{q['N']}", # ID para placeholder no Word
                        "description": q['descricao_imagem'],
                        "file_obj": q['imagem_anexa']
                    })
                    # Adiciona uma referência ao placeholder no bloco de resposta
                    bloco += f",, [Ver Imagem/Gráfico Q_{q['N']}] \r\n"
            return bloco
        
        bloco_quesitos_autor_final = _generate_quesito_block(st.session_state.quesitos_autor)
        bloco_quesitos_reu_final = _generate_quesito_block(st.session_state.quesitos_reu)
        
        # Tratamento das listas de documentos
        def _format_doc_list(doc_list: list) -> str:
            return "\n".join([f"- {d['TIPO_DOCUMENTO']} (Fls. {d['FLS_DOCUMENTOS']})" for d in doc_list])

        docs_questionados_bloco = _format_doc_list(st.session_state.documentos_questionados_list)
        docs_pca_bloco = _format_doc_list(st.session_state.documentos_paradigmas_pca_list)
        docs_pce_bloco = _format_doc_list(st.session_state.documentos_paradigmas_pce_list)
        
        # 2. Monta o dicionário de dados (Merge Fields)
        dados = ({
            # Etapa 1
            "NUMERO DO PROCESSO": st.session_state.numero_processo,
            "nome do autor": st.session_state.autor_0,
            "nome do réu": st.session_state.reu_0,
            "data do laudo": st.session_state.data_laudo.strftime("%d/%m/%Y"),
            "TIPO_JUSTICA": st.session_state.tipo_justica,
            "VARA": st.session_state.vara,
            "COMARCA": st.session_state.comarca,
            "OBJETO_PERICIA": st.session_state.obj_pericia,
            
            # Etapa 2 e 3
            "DOCS QUESTIONADOS LIST": docs_questionados_bloco,
            "DOCS PCA LIST": docs_pca_bloco,
            "DOCS PCE LIST": docs_pce_bloco,
            "DESCRICAO DOCS Q": st.session_state.doc_questionado_final,
            "DESCRICAO DOCS P": st.session_state.doc_padrao_final,
            
            # Etapa 4 e 5
            "ANALISE PADRAO": st.session_state.descricao_analise_padrao,
            "CONFRONTO": st.session_state.descricao_confronto,
            "CONCLUSAO DESCRITIVA": st.session_state.conclusao_final,
            "CONCLUSAO TIPO": st.session_state.conclusao_tipo,
            "DOCS AUTENTICOS CONC": st.session_state.get("docs_autenticos_conc", ""),
            "DOCS FALSOS CONC": st.session_state.get("docs_falsos_conc", ""),
            
            # Etapa 6 e 7
            "FLS_QUESITOS_AUTOR": st.session_state.fls_quesitos_autor,
            "FLS_QUESITOS_REU": st.session_state.fls_quesitos_reu,
            "BLOCO_QUESITOS_AUTOR": bloco_quesitos_autor_final,
            "BLOCO_QUESITOS_REU": bloco_quesitos_reu_final,
        
            # Etapa 8 (Encerramento)
            "ANEXOS_LIST": _format_doc_list(st.session_state.anexos),
            "ADENDOS_LIST": _format_doc_list(st.session_state.adendos),
            "NUM_LAUDAS": str(st.session_state.num_laudas),
            "NUM_LAUDAS_EXTENSO": num2words(st.session_state.num_laudas, lang='pt_BR').upper(),
            "ASSINATURAS": st.session_state.assinaturas
        })
        
        # 3. Geração do Laudo
        try:
            os.makedirs("output", exist_ok=True)
            
            # Adiciona o novo argumento para o word_handler (lista de imagens dos quesitos)
            gerar_laudo(
                caminho_modelo, 
                nome_arquivo_saida, 
                dados, 
                st.session_state.anexos, 
                st.session_state.adendos,
                quesito_images_list # Lista de imagens dos quesitos para o word_handler
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
            st.error(f"❌ Erro ao gerar o laudo. Verifique se o arquivo '{caminho_modelo}' está na pasta 'template/' e se o seu `word_handler.py` está atualizado.")
            st.exception(e)