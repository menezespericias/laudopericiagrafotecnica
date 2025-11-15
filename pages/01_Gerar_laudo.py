import streamlit as st
import os
import json
from datetime import date, datetime
from num2words import num2words
from typing import List, Dict, Any, Union
from word_handler import gerar_laudo
from data_handler import save_process_data, load_process_data
from db_handler import atualizar_status

# --- Configuração Inicial ---
st.set_page_config(page_title="Laudo Grafotécnico", layout="wide")

# CORREÇÃO CRÍTICA DO PATH: Garante o caminho absoluto para o modelo
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.join(SCRIPT_DIR, '..')

# --- Variáveis Globais ---
CAMINHO_MODELO = os.path.join(PROJECT_ROOT, "LAUDO PERICIAL GRAFOTÉCNICO.docx") 
OUTPUT_FOLDER = os.path.join(PROJECT_ROOT, "output")
DATA_FOLDER = os.path.join(PROJECT_ROOT, "data")

os.makedirs(DATA_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# --- Funções de Callback (Defesa na Escrita) ---

def update_session_date_format(key_data: str, key_input: str):
    """Callback para forçar que a data salva no session_state seja sempre uma STRING."""
    try:
        date_object = st.session_state[key_input]
        if isinstance(date_object, date):
            st.session_state[key_data] = date_object.strftime("%d/%m/%Y")
        elif isinstance(date_object, (list, tuple)) and date_object and isinstance(date_object[0], date):
            st.session_state[key_data] = date_object[0].strftime("%d/%m/%Y")
    except KeyError:
        pass
    except Exception:
        pass

def update_laudo_date():
    update_session_date_format("DATA_LAUDO", "input_data_laudo")

def update_vencimento_date():
    update_session_date_format("HONORARIOS_VENCIMENTO", "input_data_vencimento")

def update_colheita_date():
    update_session_date_format("DATA_COLHEITA", "input_data_colheita")

def get_date_object_from_state(key: str) -> date:
    """Sanitização Máxima: Extrai e valida o valor de data do session_state, forçando-o a ser um único objeto date."""
    data_val = st.session_state.get(key)
    if isinstance(data_val, (list, tuple)) and data_val:
        data_val = data_val[0]
    if isinstance(data_val, str) and data_val:
        data_str = data_val.strip()
        formatos = ["%d/%m/%Y", "%Y-%m-%d"] 
        for fmt in formatos:
            try:
                return datetime.strptime(data_str, fmt).date()
            except:
                continue 
    elif isinstance(data_val, date):
        return data_val
    return date.today()

def add_list_item(key: str, item_data: dict, list_key: str = None):
    final_key = list_key if list_key else key
    if final_key not in st.session_state:
        st.session_state[final_key] = []
    
    item_data['id'] = len(st.session_state[final_key]) + 1
    st.session_state[final_key].append(item_data)
    # Não usamos st.rerun() aqui, a re-renderização acontece no final do formulário ou com o botão de salvar.

def remove_list_item(list_key: str, item_id: int):
    if list_key in st.session_state:
        st.session_state[list_key] = [item for item in st.session_state[list_key] if item.get('id') != item_id]
        for i, item in enumerate(st.session_state[list_key]):
            item['id'] = i + 1
        st.rerun()

# --- Inicialização do Estado de Sessão (INCLUINDO NOVOS CAMPOS) ---
def init_session_state():
    if 'editing_etapa_1' not in st.session_state:
        st.session_state.editing_etapa_1 = True

    # CORREÇÃO CRÍTICA DO AttributeError: Garante que etapas_concluidas seja sempre um SET.
    if 'etapas_concluidas' not in st.session_state:
        st.session_state.etapas_concluidas = set()
    elif not isinstance(st.session_state.etapas_concluidas, set):
        try:
            st.session_state.etapas_concluidas = set(st.session_state.etapas_concluidas)
        except:
            st.session_state.etapas_concluidas = set()

    # NOVOS CAMPOS ADICIONADOS COM BASE NO TEMPLATE
    campos_base = [
        # Etapa 1
        "JUIZO", "VARA", "COMARCA", "DATA_LAUDO", "PERITO", "ESPECIALIZACAO", "NUMERO_REGISTRO", 
        "numero_processo", "autor", "reu", "ID_NOMEACAO_FLS", 
        # Etapa 2
        "quesitos_autor", "quesitos_reu", "PQ_FLS_INICIAIS_FINAIS", 
        # Etapa 3
        "DOCUMENTOS_QUESTIONADOS", "PADROES_ENCONTRADOS", "NUM_ESPECIMES", "DATA_COLHEITA", "FLS_COLHEITA", 
        # Etapa 4
        "METODOLOGIA_TEXTO", "CORPUS_CONFRONTO_TEXTO", 
        "HABILIDADE_VELOCIDADE", "ESPONTANEIDADE_DINAMISMO", "CALIBRE", "ALINHAMENTO_GRAFICO", "ATAQUES_REMATES",
        # Etapa 5
        "ANALISE_TEXTO", "adendos", 
        # Etapa 6
        "HONORARIOS_VALOR", "HONORARIOS_VENCIMENTO", "CONCLUSÃO_TIPO", "CONCLUSION", "RESPOSTAS_QUESITOS_MAP", "NUM_LAUDAS",
        # Outros
        "status_db"
    ]
    for campo in campos_base:
        if campo not in st.session_state:
            if campo in ["DATA_LAUDO", "HONORARIOS_VENCIMENTO", "DATA_COLHEITA"]:
                st.session_state[campo] = date.today().strftime("%d/%m/%Y")
            elif campo in ["quesitos_autor", "quesitos_reu", "adendos", "DOCUMENTOS_QUESTIONADOS", "PADROES_ENCONTRADOS"]:
                st.session_state[campo] = []
            elif campo == "CONCLUSÃO_TIPO":
                st.session_state[campo] = "Selecione a Conclusão"
            elif campo == "RESPOSTAS_QUESITOS_MAP":
                st.session_state[campo] = {}
            else:
                st.session_state[campo] = ""

# --- Funções de Carregamento e Salvar ---
def save_current_state():
    if st.session_state.numero_processo:
        process_id = st.session_state.numero_processo
        
        try:
            update_laudo_date()
            update_vencimento_date()
            update_colheita_date()
            
            # Salva os dados no JSON
            save_process_data(process_id, st.session_state) 
            
            NOVO_STATUS = "Em andamento"
            atualizar_status(process_id, NOVO_STATUS)
            
            st.session_state.status_db = NOVO_STATUS 
            
            if isinstance(st.session_state.etapas_concluidas, set):
                # Marca a Etapa 1 como concluída
                st.session_state.etapas_concluidas.add(1) 
            
            st.toast(f"✅ Dados do Processo {process_id} salvos e status atualizado para '{NOVO_STATUS}'.")
            return True
            
        except Exception as e:
            st.error(f"Erro inesperado ao salvar: {e}")
            return False
    else:
        st.error("Erro: Número do Processo não definido para salvar.")
        return False


# --- Carregamento automático do processo selecionado ---
if "process_to_load" in st.session_state and st.session_state["process_to_load"]:
    process_id = st.session_state["process_to_load"]
    try:
        dados_carregados = load_process_data(process_id)
        
        for key, value in dados_carregados.items():
            st.session_state[key] = value

        # Garante a sanitização das datas após o carregamento
        get_date_object_from_state("DATA_LAUDO")
        get_date_object_from_state("HONORARIOS_VENCIMENTO")
        get_date_object_from_state("DATA_COLHEITA")
        
        st.success(f"📂 Processo **{process_id}** carregado com sucesso!")
        
        st.session_state.process_to_load = None 
        st.session_state.editing_etapa_1 = True
        
        # Garante a coerção de tipo de 'etapas_concluidas' após o carregamento
        init_session_state() 
        
    except FileNotFoundError:
        st.error(f"❌ Arquivo JSON para o processo {process_id} não encontrado.")
        st.session_state.process_to_load = None
    except Exception as e:
        st.error(f"❌ Erro ao carregar o arquivo JSON do processo {process_id}: {e}")
        st.session_state.process_to_load = None
        

# --- Inicialização do Estado de Sessão ---
init_session_state()

# --- VERIFICAÇÃO PRINCIPAL DE NAVEGAÇÃO ---
if "numero_processo" not in st.session_state or not st.session_state.numero_processo:
    st.warning("Nenhum processo selecionado ou carregado. Por favor, volte à página inicial para selecionar ou criar um processo.")
    if st.button("🏠 Voltar para Home"): st.switch_page("home.py")
    st.stop()

# --- TÍTULO PRINCIPAL ---
st.title(f"👨‍🔬 Laudo Pericial: {st.session_state.numero_processo}")
if st.button("🏠 Voltar para Home"): st.switch_page("home.py")
st.markdown("---")

# --- ETAPA 1: DADOS BÁSICOS DO PROCESSO ---
with st.expander(f"1. Dados Básicos do Processo - {st.session_state.numero_processo}", expanded=st.session_state.editing_etapa_1):
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.session_state.numero_processo = st.text_input("Número do Processo", value=st.session_state.numero_processo, key="input_numero_processo", disabled=True)
        st.session_state.JUIZO = st.text_input("Juízo (Ex: MM. Juiz de Direito da)", value=st.session_state.get("JUIZO", ""))
        st.session_state.VARA = st.text_input("Número da Vara (Ex: 1ª)", value=st.session_state.get("VARA", "")) 
        st.session_state.COMARCA = st.text_input("Comarca", value=st.session_state.get("COMARCA", ""))
    
    with col2:
        st.session_state.autor = st.text_area("Autor(es) (Um por linha)", value=st.session_state.get("autor", ""))
        st.session_state.reu = st.text_area("Réu(s) (Um por linha)", value=st.session_state.get("reu", ""))
        st.session_state.ID_NOMEACAO_FLS = st.text_input("Fls. da Nomeação do Perito (para o Bloco 2. Objetivos)", value=st.session_state.get("ID_NOMEACAO_FLS", ""))

    with col3:
        data_obj_laudo = get_date_object_from_state("DATA_LAUDO")
        st.date_input("Data da Conclusão do Laudo", value=data_obj_laudo, key="input_data_laudo", on_change=update_laudo_date)
        
        st.session_state.PERITO = st.text_input("Nome Completo do Perito", value=st.session_state.get("PERITO", ""))
        st.session_state.ESPECIALIZACAO = st.text_input("Especialização (Ex: Grafotécnico)", value=st.session_state.get("ESPECIALIZACAO", ""))
        st.session_state.NUMERO_REGISTRO = st.text_input("Registro Profissional (Ex: 20.60660 CRA-RJ)", value=st.session_state.get("NUMERO_REGISTRO", ""))
        
    if st.button("💾 Salvar Dados Básicos (Etapa 1)"):
        if save_current_state():
            st.session_state.editing_etapa_1 = False
            st.rerun()

st.markdown("---")

# --- ETAPA 2: QUESITOS E FLS ---
with st.expander("2. Quesitos e FLS (3. Introdução e 7. Resposta)"):
    
    col_fls, col_quesitos = st.columns([1, 2])
    
    with col_fls:
        st.subheader("Informações de FLS.")
        st.session_state.PQ_FLS_INICIAIS_FINAIS = st.text_input("Fls. Iniciais e Finais dos Documentos Questionados (Ex: 100/105) (Bloco 4.1)", value=st.session_state.get("PQ_FLS_INICIAIS_FINAIS", ""))
        st.session_state.FLS_COLHEITA = st.text_input("Fls. do Auto de Colheita de Material (PCA) (Bloco 4.2.A)", value=st.session_state.get("FLS_COLHEITA", ""))
        
    with col_quesitos:
        st.subheader("Gerenciamento de Quesitos")
        
        # Formulário para adicionar Quesitos do Autor (apenas texto)
        with st.form("form_quesitos_autor"):
            st.markdown("**Adicionar Quesito do Autor**")
            novo_quesito_autor = st.text_area("Texto do Quesito do Autor")
            if st.form_submit_button("➕ Adicionar Quesito Autor"):
                if novo_quesito_autor:
                    item_data = {"texto": novo_quesito_autor}
                    add_list_item("quesitos_autor", item_data)
                else: st.error("O texto do quesito é obrigatório.")
        
        if st.session_state.quesitos_autor:
            st.markdown("**Quesitos do Autor Adicionados:**")
            for q in st.session_state.quesitos_autor:
                col_q1, col_q2 = st.columns([4, 1])
                col_q1.write(f"**Quesito {q['id']}:** {q['texto']}")
                if col_q2.button("🗑️ Remover", key=f"del_quesito_autor_{q['id']}"): remove_list_item("quesitos_autor", q['id'])
        
        with st.form("form_quesitos_reu"):
            st.markdown("**Adicionar Quesito do Réu**")
            novo_quesito_reu = st.text_area("Texto do Quesito do Réu")
            if st.form_submit_button("➕ Adicionar Quesito Réu"):
                if novo_quesito_reu:
                    item_data = {"texto": novo_quesito_reu}
                    add_list_item("quesitos_reu", item_data)
                else: st.error("O texto do quesito é obrigatório.")

        if st.session_state.quesitos_reu:
            st.markdown("**Quesitos do Réu Adicionados:**")
            for q in st.session_state.quesitos_reu:
                col_q1, col_q2 = st.columns([4, 1])
                col_q1.write(f"**Quesito {q['id']}:** {q['texto']}")
                if col_q2.button("🗑️ Remover", key=f"del_quesito_reu_{q['id']}"): remove_list_item("quesitos_reu", q['id'])
    
    if isinstance(st.session_state.etapas_concluidas, set):
        st.session_state.etapas_concluidas.add(2)

st.markdown("---")

# --- ETAPA 3: DOCUMENTOS SUBMETIDOS A EXAME (4.1 e 4.2) ---
with st.expander("3. Documentos Questionados e Padrões (Blocos 4.1 e 4.2)"):
    
    st.subheader("4.1. Documentos Questionados (PQ) - Dinâmico")
    # Formulário para adicionar Documentos Questionados
    with st.form("form_doc_questionado"):
        col_q1, col_q2 = st.columns([1, 1])
        with col_q1:
            tipo_doc = st.text_input("Tipo de Documento (Ex: Proposta de Empréstimo)", key="input_tipo_doc_q")
            num_contrato = st.text_input("Número do Contrato/Documento", key="input_num_contrato_q")
        with col_q2:
            data_doc = st.text_input("Data do Documento (DD/MM/AAAA)", key="input_data_doc_q")
            fls_doc = st.text_input("Fls. do Documento nos Autos", key="input_fls_doc_q")
        
        if st.form_submit_button("➕ Adicionar Documento Questionado"):
            if tipo_doc and data_doc:
                item_data = {"tipo": tipo_doc, "numero": num_contrato, "data": data_doc, "fls": fls_doc}
                add_list_item("DOCUMENTOS_QUESTIONADOS", item_data)
            else: st.error("Tipo e Data do Documento são obrigatórios.")

    if st.session_state.DOCUMENTOS_QUESTIONADOS:
        st.markdown("**Documentos Questionados Adicionados:**")
        for d in st.session_state.DOCUMENTOS_QUESTIONADOS:
            st.write(f"**{d['id']}**: {d['tipo']} - Nº: {d['numero']} - Data: {d['data']} - Fls: {d['fls']}")
            if st.button("🗑️ Remover", key=f"del_doc_q_{d['id']}"): remove_list_item("DOCUMENTOS_QUESTIONADOS", d['id'])
    
    st.markdown("---")
    
    st.subheader("4.2.A. Padrões Colhidos no Ato Pericial (PCA)")
    col_pca1, col_pca2 = st.columns(2)
    with col_pca1:
        st.session_state.NUM_ESPECIMES = st.text_input("Nº de Espécimes Autográficos Colhidos", value=st.session_state.get("NUM_ESPECIMES", "0"))
    with col_pca2:
        data_obj_colheita = get_date_object_from_state("DATA_COLHEITA")
        st.date_input("Data da Colheita dos Padrões", value=data_obj_colheita, key="input_data_colheita", on_change=update_colheita_date)
        
    st.markdown("---")

    st.subheader("4.2.B. Padrões Encontrados nos Autos (PCE) - Dinâmico")
    # Formulário para adicionar Padrões Encontrados
    with st.form("form_padrao_encontrado"):
        col_pce1, col_pce2 = st.columns([1, 1])
        with col_pce1:
            tipo_doc_pce = st.text_input("Tipo de Documento (Ex: Procuração, Cédula de Identidade)", key="input_tipo_doc_pce")
            fls_doc_pce = st.text_input("Fls. do Documento nos Autos", key="input_fls_doc_pce")
        with col_pce2:
            data_doc_pce = st.text_input("Data do Documento (DD/MM/AAAA)", key="input_data_doc_pce")
        
        if st.form_submit_button("➕ Adicionar Padrão Encontrado"):
            if tipo_doc_pce and fls_doc_pce and data_doc_pce:
                item_data = {"tipo": tipo_doc_pce, "fls": fls_doc_pce, "data": data_doc_pce}
                add_list_item("PADROES_ENCONTRADOS", item_data)
            else: st.error("Tipo, Fls e Data do Documento são obrigatórios.")

    if st.session_state.PADROES_ENCONTRADOS:
        st.markdown("**Padrões Encontrados Adicionados:**")
        for p in st.session_state.PADROES_ENCONTRADOS:
            st.write(f"**{p['id']}**: {p['tipo']} - Fls: {p['fls']} - Data: {p['data']}")
            if st.button("🗑️ Remover", key=f"del_padrao_e_{p['id']}"): remove_list_item("PADROES_ENCONTRADOS", p['id'])

    if isinstance(st.session_state.etapas_concluidas, set):
        st.session_state.etapas_concluidas.add(3)

st.markdown("---")

# --- ETAPA 4: EXAMES PERICIAIS E METODOLOGIA (5.1) ---
with st.expander("4. Análise dos Paradigmas e Metodologia (Bloco 5)"):
    
    st.subheader("5.1. Análise dos Paradigmas (Seleções Rápidas)")
    # Seleções Rápidas para os Elementos de Ordem Geral
    st.session_state.HABILIDADE_VELOCIDADE = st.selectbox(
        "Habilidade e Velocidade (5.1. - 1)",
        ["", "Bom grau de habilidade", "Nível primário/canhestro"],
        key="input_habilidade_velocidade"
    )
    
    st.session_state.ESPONTANEIDADE_DINAMISMO = st.selectbox(
        "Espontaneidade e Dinamismo (5.1. - 2)",
        ["", "Traçado livre e espontâneo", "Traçado lento e hesitante"],
        key="input_espontaneidade_dinamismo"
    )
    
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.session_state.CALIBRE = st.selectbox(
            "Calibre (5.1. - 3)",
            ["", "Médio", "Grosso", "Fino"],
            key="input_calibre"
        )
    with col_b:
        st.session_state.ALINHAMENTO_GRAFICO = st.selectbox(
            "Alinhamento Gráfico (5.1. - 4)",
            ["", "Horizontal", "Ascendente", "Descendente"],
            key="input_alinhamento_grafico"
        )
    with col_c:
        st.session_state.ATAQUES_REMATES = st.selectbox(
            "Ataques e Remates (5.1. - 5)",
            ["", "Apoiados", "Sem apoio", "Mistos"],
            key="input_ataques_remates"
        )

    st.markdown("---")
    
    st.subheader("Metodologia e Corpus de Confronto (Texto Livre)")
    st.session_state.METODOLOGIA_TEXTO = st.text_area("Texto Detalhado sobre a Metodologia e Técnicas Aplicadas (Bloco 5)", 
                                                      value=st.session_state.get("METODOLOGIA_TEXTO", ""), height=300)
    
    st.session_state.CORPUS_CONFRONTO_TEXTO = st.text_area("Descrição do Corpus de Confronto (Peças de Autenticidade) (Bloco 4.2)", 
                                                           value=st.session_state.get("CORPUS_CONFRONTO_TEXTO", ""), height=150)

    if isinstance(st.session_state.etapas_concluidas, set):
        st.session_state.etapas_concluidas.add(4)

st.markdown("---")

# --- ETAPA 5: ANÁLISE COMPARATIVA E ADENDOS (5.2 e 6) ---
with st.expander("5. Análise Comparativa e Adendos (Blocos 5.2 e 6)"):
    
    st.subheader("5.2. Confronto Grafoscópico - Análise Comparativa")
    st.session_state.ANALISE_TEXTO = st.text_area("Descrição Detalhada da Análise e dos Elementos Gráficos Confrontados", 
                                                  value=st.session_state.get("ANALISE_TEXTO", ""), height=500)
    
    st.markdown("---")
    
    st.subheader("6. Adendos Gráficos (Tabelas e Imagens no Corpo do Laudo)")
    with st.form("form_adendos"):
        novo_adendo_legenda = st.text_input("Legenda do Adendo (Ex: Figura 1: Comparativo de Assinaturas)", key="input_adendo_legenda")
        imagem_adendo = st.file_uploader("Imagem do Adendo", type=['png', 'jpg', 'jpeg'], key="upload_adendo")
        
        if st.form_submit_button("➕ Adicionar Adendo Gráfico"):
            if novo_adendo_legenda and imagem_adendo:
                item_data = {"legenda": novo_adendo_legenda, "imagem_obj": imagem_adendo}
                add_list_item("adendos", item_data)
            else: st.error("A legenda e a imagem são obrigatórias para o Adendo.")

    if st.session_state.adendos:
        st.markdown("**Adendos Adicionados:**")
        for d in st.session_state.adendos:
            col_d1, col_d2 = st.columns([4, 1])
            col_d1.write(f"**Adendo {d['id']}:** {d['legenda']}")
            if col_d2.button("🗑️ Remover", key=f"del_adendo_{d['id']}"): remove_list_item("adendos", d['id'])
    
    if isinstance(st.session_state.etapas_concluidas, set):
        st.session_state.etapas_concluidas.add(5)

st.markdown("---")

# --- ETAPA 6: CONCLUSÃO E RESPOSTA AOS QUESITOS (7 e 8) ---
with st.expander("6. Conclusão, Resposta aos Quesitos e Informações Finais (Blocos 6, 7 e 8)"):
    
    st.subheader("6. Conclusão - [BLOCO_CONCLUSAO_DINAMICO] (Seleção Auto-Excludente)")
    
    st.session_state.CONCLUSÃO_TIPO = st.selectbox(
        "Selecione o Tipo de Conclusão Principal",
        ["Selecione a Conclusão", "Autêntica", "Inautêntica (Falsificada)", "Inconclusiva"],
        key="input_conclusao_tipo"
    )
    
    # Preenchimento automático/personalizável do texto de conclusão (CONCLUSION)
    if st.session_state.CONCLUSÃO_TIPO != "Selecione a Conclusão":
        default_text = ""
        if st.session_state.CONCLUSÃO_TIPO == "Autêntica":
            default_text = "A conclusão é que a assinatura questionada é autêntica, pois foram encontradas convergências significativas de ordem geral e particular com os padrões gráficos do autor, não havendo indícios de imitação ou fraude."
        elif st.session_state.CONCLUSÃO_TIPO == "Inautêntica (Falsificada)":
            default_text = "A conclusão é que a assinatura questionada é inautêntica (falsificada), pois foram encontradas divergências significativas de ordem geral e particular em relação aos padrões gráficos do autor, demonstrando que o lançamento não emanou de seu punho."
        elif st.session_state.CONCLUSÃO_TIPO == "Inconclusiva":
            default_text = "A conclusão é inconclusiva, pois a qualidade do material ou outros fatores impediram a análise de elementos de valor grafotécnico suficientes para emitir um juízo de valor categórico."

        # Se o texto atual for vazio OU o texto for o padrão de outra opção, define o novo padrão.
        if not st.session_state.get("CONCLUSION") or st.session_state.get("CONCLUSION") in ["A conclusão é que a assinatura questionada é autêntica, pois foram encontradas convergências significativas de ordem geral e particular com os padrões gráficos do autor, não havendo indícios de imitação ou fraude.", "A conclusão é que a assinatura questionada é inautêntica (falsificada), pois foram encontradas divergências significativas de ordem geral e particular em relação aos padrões gráficos do autor, demonstrando que o lançamento não emanou de seu punho.", "A conclusão é inconclusiva, pois a qualidade do material ou outros fatores impediram a análise de elementos de valor grafotécnico suficientes para emitir um juízo de valor categórico."]:
            st.session_state.CONCLUSION = default_text
            
        st.session_state.CONCLUSION = st.text_area("Texto de Conclusão Detalhada (Aparece após o negrito)", 
                                                    value=st.session_state.get("CONCLUSION", default_text), height=200)

    st.markdown("---")
    st.subheader("7. Resposta aos Quesitos (7.1 e 7.2)")
    
    quesitos_a_responder = st.session_state.quesitos_autor + st.session_state.quesitos_reu
    
    if "RESPOSTAS_QUESITOS_MAP" not in st.session_state: st.session_state.RESPOSTAS_QUESITOS_MAP = {}
    
    if quesitos_a_responder:
        for q in quesitos_a_responder:
            # key_id para mapear a resposta: Autor_1, Réu_1, etc.
            key_id = f"{'Autor' if q in st.session_state.quesitos_autor else 'Réu'}_{q['id']}"
            
            st.markdown(f"**Quesito {key_id}** (Texto: *{q['texto'][:50].replace('\n', ' ')}...*)")
            
            resposta_atual = st.session_state.RESPOSTAS_QUESITOS_MAP.get(key_id, "Resposta do quesito...")
            
            st.session_state.RESPOSTAS_QUESITOS_MAP[key_id] = st.text_area(
                "Resposta Detalhada:", 
                value=resposta_atual, 
                key=f"resposta_{key_id}"
            )
    else: st.info("Nenhum quesito cadastrado na Etapa 2.")
    
    st.markdown("---")
    
    st.subheader("8. Encerramento - Informações Finais")
    col_h1, col_h2, col_h3 = st.columns(3)
    with col_h1:
        st.session_state.HONORARIOS_VALOR = st.text_input("Valor dos Honorários (R$)", 
                                                          value=st.session_state.get("HONORARIOS_VALOR", ""))
    with col_h2:
        data_obj_v = get_date_object_from_state("HONORARIOS_VENCIMENTO")
        st.date_input("Data de Vencimento do Pagamento", value=data_obj_v, key="input_data_vencimento", on_change=update_vencimento_date)
    with col_h3:
        st.session_state.NUM_LAUDAS = st.text_input("Nº de Laudas no Laudo Final (Preencha após a geração)", value=st.session_state.get("NUM_LAUDAS", "X"))
        
    if isinstance(st.session_state.etapas_concluidas, set):
        st.session_state.etapas_concluidas.add(6) 

st.markdown("---")

# --- ETAPA 7: GERAÇÃO DO LAUDO ---
with st.expander("7. Gerar Laudo Final", expanded=(7 in st.session_state.etapas_concluidas if isinstance(st.session_state.etapas_concluidas, set) else False)):
    st.subheader("Configurações de Geração")
    
    caminho_saida = os.path.join(OUTPUT_FOLDER, f"Laudo_{st.session_state.numero_processo}.docx")
    
    st.write(f"Modelo a ser usado: **{os.path.basename(CAMINHO_MODELO)}**")
    st.write(f"Arquivo de saída: **{os.path.basename(caminho_saida)}** (salvo em `{os.path.basename(OUTPUT_FOLDER)}/`)")

    is_disabled = not(isinstance(st.session_state.etapas_concluidas, set) and len(st.session_state.etapas_concluidas) >= 6)

    if st.button("🚀 Gerar Documento .DOCX", type="primary", disabled=is_disabled):
        
        update_laudo_date()
        update_vencimento_date()
        update_colheita_date()
        
        dados_simples = {k: v for k, v in st.session_state.items() if not k.startswith("editing_") and k not in ["process_to_load", "etapas_concluidas"]}
        
        dados_simples['AUTORES'] = [a.strip() for a in dados_simples.get('autor', '').split('\n') if a.strip()]
        dados_simples['REUS'] = [r.strip() for r in dados_simples.get('reu', '').split('\n') if r.strip()]
        
        dados_simples['PRIMEIRO_AUTOR'] = dados_simples['AUTORES'][0] if dados_simples['AUTORES'] else "Autor(a) Não Informado(a)"
        dados_simples['NOME COMPLETO DO RÉU'] = dados_simples['REUS'][0] if dados_simples['REUS'] else "Réu Não Informado"

        # Prepara a lista de respostas de quesitos
        respostas_quesitos_list = []
        for key, text in dados_simples.get('RESPOSTAS_QUESITOS_MAP', {}).items():
            try:
                parte, q_id = key.split('_')
            except ValueError:
                continue # Pula chaves mal formatadas
                
            if parte == 'Autor':
                lista_quesitos = dados_simples.get('quesitos_autor', [])
            else:
                lista_quesitos = dados_simples.get('quesitos_reu', [])
                
            original_text = next((q['texto'] for q in lista_quesitos if str(q['id']) == q_id), f"Quesito {q_id} não encontrado")
            
            respostas_quesitos_list.append({
                "parte": parte,
                "id": q_id,
                "quesito": original_text,
                "resposta": text
            })
        dados_simples['RESPOSTAS_QUESITOS_LIST'] = respostas_quesitos_list
        
        try:
            gerar_laudo(
                caminho_modelo=CAMINHO_MODELO,
                caminho_saida=caminho_saida,
                dados=dados_simples,
                # Passamos as listas de imagens (adendos) para o word_handler, se necessário
                adendos=st.session_state.adendos 
            )
            
            if isinstance(st.session_state.etapas_concluidas, set):
                st.session_state.etapas_concluidas.add(7) 
            
            if save_current_state():
                 st.success(f"Laudo **{st.session_state.numero_processo}** gerado com sucesso!")
            
            with open(caminho_saida, "rb") as file:
                st.download_button(
                    label="⬇️ Baixar Laudo .DOCX",
                    data=file,
                    file_name=os.path.basename(caminho_saida),
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )

        except FileNotFoundError:
            st.error(f"❌ Erro de Arquivo: O arquivo de modelo não foi encontrado. Verifique se o arquivo 'LAUDO PERICIAL GRAFOTÉCNICO.docx' está na raiz do projeto (diretório acima da pasta 'pages').")
        except Exception as e:
            st.error(f"❌ Erro durante a geração do documento: {e}")
            st.exception(e)

st.markdown("---")