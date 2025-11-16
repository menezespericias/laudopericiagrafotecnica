# pages/01_Gerar_laudo.py (O MÓDULO INTEGRADO/CONTROLADOR DE FLUXO)

import streamlit as st
import os
import json
import uuid
import base64
import io
import pandas as pd
import matplotlib.pyplot as plt
from datetime import date, datetime
from typing import Dict, Any, Set, List, Callable, Union
from num2words import num2words # Necessário para a lógica do word_handler

# --- Importações dos módulos de backend (Assumindo que estão na pasta 'src') ---
try:
    # Atenção: Se ocorrer ModuleNotFoundError aqui, certifique-se que o diretório 'src'
    # está na raiz do projeto e contém um arquivo __init__.py vazio.
    from src.word_handler import gerar_laudo
    from src.data_handler import save_process_data, load_process_data
    from src.db_handler import atualizar_status
except ImportError as e:
    st.error(f"Erro de Importação: {e}. Certifique-se de que os arquivos 'data_handler.py', 'db_handler.py' e 'word_handler.py' estão na pasta 'src' e que o 'src' está na raiz do projeto.")
    def gerar_laudo(*args, **kwargs): st.error("Erro: word_handler não carregado.")
    def save_process_data(*args, **kwargs): return False
    def load_process_data(*args, **kwargs): return {}
    def atualizar_status(*args, **kwargs): pass

# --- Configurações de Ambiente (Paths) ---
# Se '01_Gerar_laudo.py' está em 'pages', PROJECT_ROOT deve subir um nível.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.join(SCRIPT_DIR, '..')
CAMINHO_MODELO = os.path.join(PROJECT_ROOT, "template", "LAUDO PERICIAL GRAFOTÉCNICO.docx")
OUTPUT_FOLDER = os.path.join(PROJECT_ROOT, "output")
DATA_FOLDER = os.path.join(PROJECT_ROOT, "data")
os.makedirs(DATA_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# --- Constantes de Etapas (INTEGRADO DE module_0x_...py) ---
ETAPA_ID_1 = 1 # Apresentação
ETAPA_ID_2 = 2 # Objetivos
ETAPA_ID_3 = 3 # Introdução
ETAPA_ID_4 = 4 # Documentos
ETAPA_ID_5 = 5 # Análise (EOG/Confronto)
ETAPA_ID_6 = 6 # Conclusão
ETAPA_ID_7 = 7 # Quesitos
ETAPA_ID_8 = 8 # Encerramento

# Constantes de Análise (INTEGRADO DE module_05_analise.py)
EOG_ELEMENTS = {
    "HABILIDADE_VELOCIDADE": "Habilidade e Velocidade",
    "ESPONTANEIDADE_DINAMISMO": "Espontaneidade e Dinamismo",
    "CALIBRE": "Calibre",
    "ALINHAMENTO_GRAFICO": "Alinhamento Gráfico",
    "ATAQUES_REMATES": "Ataques e Remates"
}
CONFRONTO_ELEMENTS = {
    "NATUREZA_GESTO": "Natureza do Gesto Gráfico: Velocidade, pressão, espontaneidade.",
    "MORFOLOGIA": "Morfologia: Forma e dimensão dos caracteres.",
    "VALORES_ANGULARES": "Valores Angulares e Curvilíneos: Inclinação dos traços.",
    "ATAQUES_REMATES_5_2": "Ataques e Remates: Modo como o traço se inicia e termina.",
    "PONTOS_CONEXAO": "Pontos de Conexão e Ligação: União entre letras e palavras."
}
EOG_STATUS_OPCOES = {
    "PRESENTE": "Presente e Normal",
    "PRESENTE_ANOMALO": "Presente com Anomalia",
    "AUSENTE": "Ausente"
}
TIPO_DOCUMENTO_OPCOES = [
    "Cédula de Identidade", "Procuração", "Declaração de Residência", "Contrato Social", "Outros"
]
CONCLUSOES_OPCOES = {
    "AUTENTICA": "Autêntica (Promanou do punho escritor)",
    "FALSA": "Falsa (Não promanou do punho escritor)",
    "PENDENTE": "PENDENTE / Não Avaliada"
}
NO_QUESITOS_TEXT = "Não foram encaminhados quesitos para resposta para o Perito nomeado."

# --- Funções de Controle de Estado ---

def init_session_state():
    """Inicializa chaves essenciais e corrige o tipo de dados após o carregamento."""
    
    # CRÍTICO: 'etapas_concluidas' deve ser um set para permitir a adição (add)
    if 'etapas_concluidas' not in st.session_state or not isinstance(st.session_state.etapas_concluidas, set):
        # Converte a lista (se carregada do JSON) para um set (se inicializada)
        if isinstance(st.session_state.get('etapas_concluidas'), list):
            st.session_state.etapas_concluidas = set(st.session_state.etapas_concluidas)
        else:
            st.session_state.etapas_concluidas = set()
            
    # CRÍTICO: Inicialização de listas vazias
    st.session_state.setdefault('questionados_list', [])
    st.session_state.setdefault('padroes_pca_list', [])
    st.session_state.setdefault('padroes_pce_list', [])
    st.session_state.setdefault('analises_eog_list', [])
    st.session_state.setdefault('anexos', []) # Usado para imagens do Word
    st.session_state.setdefault('adendos', []) # Usado para imagens de EOG e Quesitos
    st.session_state.setdefault('quesitos_autora_data', {'fls': '', 'list': []})
    st.session_state.setdefault('quesitos_reu_data', {'fls': '', 'list': []})
    st.session_state.setdefault('process_loaded', False) # Flag de carregamento
    st.session_state.setdefault('numero_processo', '')
    st.session_state.setdefault('DATA_LAUDO', date.today())
    # Campos que o Word Handler espera:
    st.session_state.setdefault('BLOCO_CONCLUSAO_DINAMICO', '')
    st.session_state.setdefault('BLOCO_QUESITOS_AUTOR', '')
    st.session_state.setdefault('BLOCO_QUESITOS_REU', '')
    st.session_state.setdefault('RESUMO_CABECALHO', '')


def save_current_state():
    """Salva o estado atual do processo no JSON e atualiza o DB."""
    if st.session_state.numero_processo:
        try:
            # Converte 'etapas_concluidas' para list para ser serializado no JSON
            temp_etapas = st.session_state.etapas_concluidas
            st.session_state.etapas_concluidas = list(temp_etapas)
            
            save_process_data(st.session_state.numero_processo, st.session_state)
            
            # Atualiza a data de modificação no DB para manter o home.py atualizado
            atualizar_status(st.session_state.numero_processo, st.session_state.get('status', 'Em andamento'))
            
            # Converte de volta para set para uso no Streamlit
            st.session_state.etapas_concluidas = temp_etapas
            
            return True
        except Exception as e:
            st.error(f"Erro ao salvar: {e}")
            return False
    return False

def load_process(process_id: str):
    """Carrega os dados de um processo existente."""
    try:
        dados = load_process_data(process_id)
        
        # Copia dados carregados para o session_state
        for key, value in dados.items():
            st.session_state[key] = value
            
        # Garante a inicialização e correção de tipos (set, date)
        init_session_state()
        
        st.session_state.process_loaded = True
        st.session_state.numero_processo = process_id
        
        st.success(f"Dados do processo **{process_id}** carregados com sucesso!")
        st.rerun()
        
    except FileNotFoundError:
        st.error(f"❌ Não há dados salvos para o processo **{process_id}**.")
    except Exception as e:
        st.error(f"❌ Erro ao carregar dados: {e}")

# --- Funções Auxiliares (INTEGRADO DE module_0x_...py) ---

def add_item(list_key: str, default_data: Dict[str, Any]):
    """Adiciona um novo item à lista de documentos (Questionados ou Padrões)."""
    if list_key not in st.session_state:
        st.session_state[list_key] = []
        
    new_item = {"id": str(uuid.uuid4()), **default_data}
    st.session_state[list_key].append(new_item)

def remove_item(list_key: str, item_id: str):
    """Remove um item da lista de documentos pelo ID."""
    if list_key in st.session_state:
        st.session_state[list_key] = [item for item in st.session_state[list_key] if item['id'] != item_id]

def get_questionado_item(questionado_id: str, questionados_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Busca o item de documento questionado pelo ID."""
    return next((item for item in questionados_list if item['id'] == questionado_id), {})

def generate_image_base64(fig: plt.Figure) -> bytes:
    """Converte a figura Matplotlib para bytes PNG em base64."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    return buf.getvalue()

def get_quesito_id_text(party_name: str, index: int) -> str:
    """Gera o texto de identificação do quesito."""
    return f"Quesito da Parte {party_name} nº {index + 1}"

def gather_all_references(session_state: Dict[str, Any]) -> List[str]:
    """Coleta todas as referências possíveis (documentos, análises, adendos)."""
    references = []
    
    # 1. Documentos Questionados (4.1)
    for idx, item in enumerate(session_state.get('questionados_list', [])):
        references.append(f"Doc. Questionado {idx+1}: {item.get('TIPO_DOCUMENTO', 'S/N')} (Fls. {item.get('FLS_DOCUMENTOS', 'S/N')})")
        
    # 2. Documentos Padrão (4.2) - PC
    for idx, item in enumerate(session_state.get('padroes_pca_list', [])):
        references.append(f"Doc. Padrão Colhido {idx+1}: {item.get('TIPO_DOCUMENTO_OPCAO', 'S/N')} (Fls. {item.get('NUMEROS', 'S/N')})")
        
    # 3. Documentos Padrão (4.2) - PCE
    for idx, item in enumerate(session_state.get('padroes_pce_list', [])):
        references.append(f"Doc. Padrão Autos {idx+1}: {item.get('TIPO_DOCUMENTO_OPCAO', 'S/N')} (Fls. {item.get('NUMEROS', 'S/N')})")
        
    # 4. Análises Gráficas (5.0)
    for idx, item in enumerate(session_state.get('analises_eog_list', [])):
        ref_doc = get_questionado_item(item.get('questionado_id', ''), session_state.get('questionados_list', []))
        doc_tipo = ref_doc.get('TIPO_DOCUMENTO', 'S/N')
        references.append(f"Análise Gráfica {idx+1}: {doc_tipo} (Item 5.1/5.2)")
    
    return references

def add_quesito_item(party_key: str, default_data: Dict[str, Any]):
    """Adiciona um novo quesito à lista da parte (Autora ou Réu)."""
    list_key = party_key + '_data'
    if list_key not in st.session_state:
        st.session_state[list_key] = {'fls': '', 'list': []}
        
    new_item = {"id": str(uuid.uuid4()), **default_data}
    st.session_state[list_key]['list'].append(new_item)

def remove_quesito_item(party_key: str, item_id: str):
    """Remove um quesito da lista da parte pelo ID."""
    list_key = party_key + '_data'
    if list_key in st.session_state:
        st.session_state[list_key]['list'] = [item for item in st.session_state[list_key]['list'] if item['id'] != item_id]

def process_quesitos_for_adendos(quesitos_list: List[Dict[str, Any]], party_name: str):
    """Processa imagens de quesitos e as move para a lista de adendos (para o Word)."""
    
    # Filtra adendos antigos (se houver) para remover imagens de quesitos da mesma parte
    st.session_state.adendos = [a for a in st.session_state.adendos if not (a.get('origem') == 'quesito' and a.get('parte') == party_name)]
    
    for idx, quesito in enumerate(quesitos_list):
        if quesito.get('imagem_bytes'):
            adendo_id = f"Quesito_{party_name}_{idx}"
            
            # Adiciona a imagem à lista de adendos
            st.session_state.adendos.append({
                "origem": "quesito",
                "parte": party_name,
                "id_referencia": adendo_id,
                "descricao": get_quesito_id_text(party_name, idx),
                "bytes": quesito['imagem_bytes'],
                "filename": f"quesito_{party_name.lower()}_{idx+1}.png"
            })
            # Limpa o campo de bytes para não salvar no JSON
            quesito.pop('imagem_bytes', None)
            
def generate_quesito_block_text(party_name: str, quesitos_data: Dict[str, Any]) -> str:
    """Gera o bloco de texto formatado para os Quesitos (Bloco 7)."""
    
    quesitos_list = quesitos_data.get('list', [])
    
    if not quesitos_list:
        return NO_QUESITOS_TEXT
        
    fls = quesitos_data.get('fls', 'N/A')
    
    # Título do Bloco 7
    bloco_text = f"**Quesitos da Parte {party_name} - Fls. {fls}**\n\n"
    
    for idx, item in enumerate(quesitos_list):
        # Título do Quesito
        bloco_text += f"**{get_quesito_id_text(party_name, idx)}:**\n"
        
        # Resposta (em itálico)
        bloco_text += f"*R: {item.get('resposta', 'Resposta pendente.')}*\n"
        
        # Referência ao Adendo/Anexo
        if item.get('tem_imagem', False):
            bloco_text += f"(Ver Adendo Fotográfico nº {idx+1} para a demonstração gráfica.)\n\n"
        else:
             bloco_text += "\n" # Espaço após a resposta se não houver imagem
             
    return bloco_text.strip() # Remove espaços extras no final

def find_anexo_for_questionado(q_id: str, anexos: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    """Encontra o anexo correspondente a um documento questionado pelo ID de referência."""
    # Anexos de documentos questionados devem ter a 'origem' como 'documento_questionado'
    return next((a for a in anexos if a.get('origem') == 'documento_questionado' and a.get('id_referencia') == q_id), None)

def get_final_conclusion_text(session_state: Dict[str, Any]) -> str:
    """Gera o texto final da conclusão (BLOCO_CONCLUSAO_DINAMICO)."""
    
    analises = session_state.get('analises_eog_list', [])
    
    if not analises:
        return "Não foi possível emitir uma conclusão pericial devido à ausência de documentos questionados ou análise completa."
        
    conclusoes = {}
    
    # Agrupa as conclusões
    for analise in analises:
        questionado_id = analise.get('questionado_id', 'S/N')
        status = analise.get('conclusao_status', 'PENDENTE')
        
        # Busca o tipo de documento original
        q_item = get_questionado_item(questionado_id, session_state.get('questionados_list', []))
        doc_tipo = q_item.get('TIPO_DOCUMENTO', 'Documento S/N')
        doc_fls = q_item.get('FLS_DOCUMENTOS', 'Fls. S/N')
        
        if status not in conclusoes:
            conclusoes[status] = []
            
        conclusoes[status].append(f"{doc_tipo} de {doc_fls}")
        
    text_parts = []
    
    if CONCLUSOES_OPCOES['AUTENTICA'] in conclusoes:
        doc_list = ", ".join(conclusoes[CONCLUSOES_OPCOES['AUTENTICA']])
        text_parts.append(f"Os lançamentos gráficos contidos nos documentos: **{doc_list}**, **PROMANARAM DO PUNHO ESCRITOR** de {session_state.get('AUTOR', 'N/A')} (ou {session_state.get('REU', 'N/A')}, dependendo do caso), sendo classificados como **AUTÊNTICOS**.")
        
    if CONCLUSOES_OPCOES['FALSA'] in conclusoes:
        doc_list = ", ".join(conclusoes[CONCLUSOES_OPCOES['FALSA']])
        text_parts.append(f"Os lançamentos gráficos contidos nos documentos: **{doc_list}**, **NÃO PROMANARAM DO PUNHO ESCRITOR** de {session_state.get('AUTOR', 'N/A')} (ou {session_state.get('REU', 'N/A')}, dependendo do caso), sendo classificados como **FALSOS** (ou produzidos por pessoa diversa).")

    if not text_parts:
        return "Não foi possível emitir uma conclusão pericial, pois todas as análises estão pendentes ou não salvas."
        
    return "\n\n".join(text_parts)


# --- Funções de Renderização de Etapas (INTEGRADO DE module_0x_...py) ---

# RENDERIZAÇÃO 1: APRESENTAÇÃO/OBJETIVOS/INTRODUÇÃO (Blocos 1, 2, 3)
def render_etapa_1(session_state: Dict[str, Any], save_callback: Callable[[], bool]):
    
    is_completed = ETAPA_ID_1 in session_state.etapas_concluidas
    
    with st.expander(f"✅ 1-3. APRESENTAÇÃO, OBJETIVOS e INTRODUÇÃO" if is_completed else f"➡️ 1-3. APRESENTAÇÃO, OBJETIVOS e INTRODUÇÃO", expanded=not is_completed):
        
        st.markdown("Preencha os dados básicos que serão inseridos nos blocos iniciais e no cabeçalho do laudo.")
        
        with st.form("form_etapa_1"):
            st.subheader("Informações Básicas do Laudo")
            
            col1, col2 = st.columns(2)
            
            session_state.JUIZO_DE_DIREITO = col1.text_input(
                "Juízo de Direito",
                value=session_state.get('JUIZO_DE_DIREITO', 'Excelentíssimo(a) Senhor(a) Doutor(a) Juiz(a) de Direito'),
                key='input_JUIZO_DE_DIREITO'
            )
            
            # ID_NOMEACAO (necessário para os Blocos 1, 2 e 7 (título da Etapa 7))
            session_state.ID_NOMEACAO = col2.text_input(
                "ID Nomeação (Fls. da Nomeação e Documentos Questionados)",
                value=session_state.get('ID_NOMEACAO', '1-2'),
                key='input_ID_NOMEACAO'
            )
            
            # Campo de Data do Laudo
            session_state.DATA_LAUDO = col1.date_input(
                "Data do Laudo",
                value=session_state.get('DATA_LAUDO', date.today()),
                key='input_DATA_LAUDO'
            )
            
            # Campo para o resumo do cabeçalho
            resumo_texto = f"Processo: {session_state.get('numero_processo', 'N/A')}\\nAutor: {session_state.get('AUTOR', 'N/A')}\\nRéu: {session_state.get('REU', 'N/A')}"
            session_state.RESUMO_CABECALHO = st.text_area(
                 "Prévia do Resumo do Cabeçalho (O Word Handler irá formatar isso)",
                 value=resumo_texto,
                 height=100,
                 key='input_RESUMO_CABECALHO_PREVIEW',
                 disabled=True
            )

            submitted = st.form_submit_button("💾 Salvar Blocos 1, 2 e 3", type="primary")
            
            if submitted:
                # 1. Marca TODOS os módulos de texto fixo/endereçamento como concluídos
                session_state.etapas_concluidas.add(ETAPA_ID_1)
                session_state.etapas_concluidas.add(ETAPA_ID_2)
                session_state.etapas_concluidas.add(ETAPA_ID_3)
                
                # 2. Salva o estado completo
                if save_callback():
                    st.success("Informações dos Blocos 1, 2 e 3 salvas com sucesso!")
                    st.rerun()
                else:
                    st.error("Falha ao salvar o estado do processo.")

# RENDERIZAÇÃO 4: DOCUMENTOS (Bloco 4)

# Funções de renderização de formulários de Documentos (Auxiliares do Módulo 4)
def render_questionado_form(item: Dict[str, Any], idx: int, save_callback: Callable[[], bool]):
    with st.container(border=True):
        st.caption(f"Documento Questionado {idx+1}")
        col_q1, col_q2, col_q3 = st.columns([3, 3, 1])

        item['TIPO_DOCUMENTO'] = col_q1.text_input(
            "Tipo de Documento",
            value=item.get('TIPO_DOCUMENTO', 'Contrato'),
            key=f"q_tipo_{item['id']}"
        )
        item['FLS_DOCUMENTOS'] = col_q2.text_input(
            "Fls. (Números de Fls.)",
            value=item.get('FLS_DOCUMENTOS', '20-22'),
            key=f"q_fls_{item['id']}"
        )
        
        # Adiciona campo para imagem do documento questionado (para Anexo)
        file_bytes = item.get('imagem_obj')
        uploaded_file = st.file_uploader(
            "Anexar Imagem do Documento Questionado (Opcional)",
            type=["png", "jpg", "jpeg"],
            key=f"q_upload_{item['id']}"
        )
        
        if uploaded_file is not None:
            file_bytes = uploaded_file.read()
            item['imagem_obj'] = file_bytes # Salva o objeto binário temporariamente

        if file_bytes:
            st.image(file_bytes, caption=f"Imagem carregada para {item['TIPO_DOCUMENTO']}", width=100)
            
            if st.button("Remover Imagem", key=f"q_remove_img_{item['id']}"):
                 item.pop('imagem_obj', None)
                 st.info("Imagem removida. Clique em 'Salvar Documentos' para confirmar.")
                 st.rerun()
        
        if col_q3.button("🗑️ Remover", key=f"q_remove_{item['id']}"):
            remove_item("questionados_list", item['id'])
            save_callback()
            st.rerun()

def render_padrao_form(item: Dict[str, Any], idx: int, save_callback: Callable[[], bool]):
    with st.container(border=True):
        st.caption(f"Documento Padrão {idx+1} (Tipo: {item.get('TIPO_DOCUMENTO_OPCAO', 'N/A')})")
        col_p1, col_p2, col_p3 = st.columns([3, 3, 1])
        
        item['TIPO_DOCUMENTO_OPCAO'] = col_p1.selectbox(
            "Tipo de Documento",
            options=TIPO_DOCUMENTO_OPCOES,
            index=TIPO_DOCUMENTO_OPCOES.index(item.get('TIPO_DOCUMENTO_OPCAO', TIPO_DOCUMENTO_OPCOES[0])),
            key=f"p_tipo_{item['id']}"
        )
        item['NUMEROS'] = col_p2.text_input(
            "Fls. / Local de Colheita",
            value=item.get('NUMEROS', 'Fls. X'),
            key=f"p_fls_{item['id']}"
        )
        item['DESCRICAO_IMAGEM'] = st.text_input(
            "Descrição do Lançamento Gráfico (Ex: Assinatura, Rubrica, Escrita Cursiva)",
            value=item.get('DESCRICAO_IMAGEM', 'Assinatura'),
            key=f"p_desc_{item['id']}"
        )
        
        if col_p3.button("🗑️ Remover", key=f"p_remove_{item['id']}"):
            remove_item("padroes_pce_list", item['id'])
            save_callback()
            st.rerun()


def render_etapa_4(session_state: Dict[str, Any], save_callback: Callable[[], bool]):
    is_completed = ETAPA_ID_4 in session_state.etapas_concluidas
    ETAPA_TITULO = "4. DOCUMENTOS SUBMETIDOS A EXAME"
    
    with st.expander(f"✅ {ETAPA_TITULO}" if is_completed else f"➡️ {ETAPA_TITULO}", expanded=not is_completed):
        
        with st.form("form_etapa_4"):
            st.subheader("4.1. Documentos Questionados (PQ)")
            st.info("Adicione todos os documentos que contêm os lançamentos gráficos a serem examinados.")
            
            # Renderiza os itens Questionados existentes
            for idx, item in enumerate(session_state.questionados_list):
                render_questionado_form(item, idx, save_callback)
            
            col_add_q, col_save_q = st.columns([1, 4])
            if col_add_q.button("➕ Adicionar Questionado", key="add_questionado", type="secondary", use_container_width=True):
                add_item("questionados_list", {"TIPO_DOCUMENTO": "Contrato", "FLS_DOCUMENTOS": "1"})
                st.rerun()

            st.markdown("---")
            st.subheader("4.2. Documentos Padrão (PC) - Padrões de Confronto")
            
            # 4.2 A. Padrões Colhidos no Ato Pericial (PCA) - (Geralmente lista vazia)
            st.caption("A. Padrões Colhidos no Ato Pericial (PCA) - Não editável aqui.")
            
            # 4.2 B. Padrões Encontrados nos Autos (PCE)
            st.markdown("B. Padrões Encontrados nos Autos (PCE)")
            
            # Renderiza os itens Padrão (PCE) existentes
            for idx, item in enumerate(session_state.padroes_pce_list):
                render_padrao_form(item, idx, save_callback)

            col_add_pce, col_save_pce = st.columns([1, 4])
            if col_add_pce.button("➕ Adicionar Padrão (PCE)", key="add_padrao", type="secondary", use_container_width=True):
                add_item("padroes_pce_list", {
                    "TIPO_DOCUMENTO_OPCAO": TIPO_DOCUMENTO_OPCOES[0],
                    "NUMEROS": "Fls. X",
                    "DESCRICAO_IMAGEM": "Assinatura"
                })
                st.rerun()

            st.markdown("---")
            submitted = st.form_submit_button("💾 Salvar Documentos e Prosseguir", type="primary")

            if submitted:
                # 1. CRÍTICO: Transfere imagens de Questionados para a lista de Anexos
                session_state.anexos = [a for a in session_state.anexos if a.get('origem') != 'documento_questionado']
                for item in session_state.questionados_list:
                    if item.get('imagem_obj'):
                        # Se houver imagem, adiciona à lista de anexos
                        session_state.anexos.append({
                            "origem": "documento_questionado",
                            "id_referencia": item['id'],
                            "descricao": f"Documento Questionado: {item['TIPO_DOCUMENTO']} ({item['FLS_DOCUMENTOS']})",
                            "bytes": item['imagem_obj'],
                            "filename": f"questionado_{item['id']}.png"
                        })
                        # Remove o objeto binário para não salvar no JSON
                        item.pop('imagem_obj', None)
                        
                # 2. Verifica se há pelo menos 1 questionado e 1 padrão
                if not session_state.questionados_list or not (session_state.padroes_pca_list or session_state.padroes_pce_list):
                     st.warning("⚠️ É necessário adicionar pelo menos **um Documento Questionado** e **um Documento Padrão** para prosseguir.")
                else:
                    session_state.etapas_concluidas.add(ETAPA_ID_4)
                    
                    # 3. CRÍTICO: Inicializa a lista de análises para a Etapa 5
                    # Garante que cada Documento Questionado tenha uma entrada em 'analises_eog_list'
                    existing_q_ids = {a['questionado_id'] for a in session_state.analises_eog_list}
                    for q_item in session_state.questionados_list:
                        if q_item['id'] not in existing_q_ids:
                             session_state.analises_eog_list.append({
                                'id': str(uuid.uuid4()),
                                'questionado_id': q_item['id'],
                                'is_saved': False,
                                'conclusao_status': CONCLUSOES_OPCOES['PENDENTE'],
                                # Inicializa os dicionários de EOG e Confronto
                                'EOG_STATUS': {key: EOG_STATUS_OPCOES['PRESENTE'] for key in EOG_ELEMENTS},
                                'CONFRONTO_STATUS': {key: 'CONVERGÊNCIA' for key in CONFRONTO_ELEMENTS},
                                'obs_eog': '',
                                'obs_confronto': '',
                                'imagem_analise_bytes': None # Imagem do gráfico EOG
                             })

                    if save_callback():
                        st.success("Documentos e Anexos salvos. Avance para a Análise.")
                        st.rerun()
                    else:
                        st.error("Falha ao salvar o estado do processo.")


# RENDERIZAÇÃO 5: ANÁLISE PERICIAL (Bloco 5)
def render_analise_form(item: Dict[str, Any], save_callback: Callable[[], bool], questionados_options: Dict[str, str], current_questionado_id: str):
    """Renderiza o formulário de Análise EOG e Confronto."""
    
    questionado_id = item.get('questionado_id', 'S/N')
    questionado_nome = questionados_options.get(questionado_id, 'Documento Desconhecido')
    is_saved = item.get('is_saved', False)
    
    with st.expander(f"{'✅' if is_saved else '➡️'} Análise para: **{questionado_nome}**", expanded=questionado_id == current_questionado_id):
        
        # O ID da análise selecionada no st.selectbox
        selected_id = questionado_id

        # Verifica se o ID do item corresponde ao ID selecionado para renderizar o formulário
        if selected_id == questionado_id:
            current_analysis = next(a for a in st.session_state.analises_eog_list if a['questionado_id'] == selected_id)
            
            with st.form(f"form_analise_{selected_id}"):
                
                st.subheader("5.1. Análise dos Elementos de Ordem Gráfica (EOG)")
                
                # Input para EOGs
                for key, label in EOG_ELEMENTS.items():
                    current_analysis['EOG_STATUS'][key] = st.selectbox(
                        f"Status - {label}",
                        options=list(EOG_STATUS_OPCOES.keys()),
                        format_func=lambda x: EOG_STATUS_OPCOES[x],
                        index=list(EOG_STATUS_OPCOES.keys()).index(current_analysis['EOG_STATUS'].get(key, EOG_STATUS_OPCOES['PRESENTE'])),
                        key=f"eog_{selected_id}_{key}"
                    )
                
                current_analysis['obs_eog'] = st.text_area(
                    "Observações/Conclusão Parcial (5.1)",
                    value=current_analysis.get('obs_eog', ''),
                    key=f"obs_eog_{selected_id}"
                )

                st.markdown("---")
                st.subheader("5.2. Confronto Grafoscópico (PQ vs PC)")
                st.info("Aponte Convergência ou Divergência para cada elemento em relação aos padrões de confronto.")
                
                # Input para Confronto
                for key, label in CONFRONTO_ELEMENTS.items():
                    current_analysis['CONFRONTO_STATUS'][key] = st.selectbox(
                        f"Status - {label}",
                        options=['CONVERGÊNCIA', 'DIVERGÊNCIA'],
                        index=['CONVERGÊNCIA', 'DIVERGÊNCIA'].index(current_analysis['CONFRONTO_STATUS'].get(key, 'CONVERGÊNCIA')),
                        key=f"confronto_{selected_id}_{key}"
                    )

                current_analysis['obs_confronto'] = st.text_area(
                    "Observações/Conclusão Parcial (5.2)",
                    value=current_analysis.get('obs_confronto', ''),
                    key=f"obs_confronto_{selected_id}"
                )
                
                st.markdown("---")
                st.subheader("Visualização e Anexo do Gráfico EOG")
                
                # Lógica para gerar o gráfico de radar (EOG)
                if st.button("📊 Gerar Gráfico EOG", key=f"generate_chart_{selected_id}", type="secondary"):
                    
                    data = {
                        'elementos': list(EOG_ELEMENTS.values()),
                        'status': [current_analysis['EOG_STATUS'][key] for key in EOG_ELEMENTS.keys()]
                    }
                    df = pd.DataFrame(data)
                    
                    # Converte status para valores numéricos para o radar (Apenas como visual, 3 pontos)
                    status_map = {'PRESENTE': 3, 'PRESENTE_ANOMALO': 2, 'AUSENTE': 1}
                    df['valor'] = df['status'].map({k: i+1 for i, k in enumerate(EOG_STATUS_OPCOES.keys())}) # 1, 2, 3
                    
                    # Configuração do gráfico de radar
                    categories = df['elementos'].tolist()
                    values = df['valor'].tolist()
                    
                    # Usa o valor máximo para fechar o círculo
                    values += values[:1]
                    categories += categories[:1]
                    
                    fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True))
                    
                    # Define os ângulos para cada categoria
                    angles = [n / float(len(categories) - 1) * 2 * 3.14159 for n in range(len(categories) - 1)]
                    angles += angles[:1]
                    
                    # Desenha a área
                    ax.fill(angles, values, color='red', alpha=0.25)
                    # Desenha a linha
                    ax.plot(angles, values, color='red', linewidth=2, linestyle='solid')
                    
                    # Ajusta ticks e rótulos
                    ax.set_xticks(angles[:-1])
                    ax.set_xticklabels(categories[:-1], size=10, color='gray')
                    ax.set_yticks([1, 2, 3])
                    ax.set_yticklabels(["Ausente", "Anomalia", "Presente"], color="grey", size=8)
                    ax.set_ylim(0, 3)
                    
                    plt.title(f'Análise EOG: {questionado_nome}', size=12, y=1.1)
                    
                    # Converte figura para bytes para salvar no JSON/Adendos
                    image_bytes = generate_image_base64(fig)
                    current_analysis['imagem_analise_bytes'] = image_bytes # Salva em bytes temporariamente
                    
                    st.pyplot(fig)
                    plt.close(fig) # Fecha a figura para liberar memória

                # Exibe a imagem salva (se existir)
                if current_analysis.get('imagem_analise_bytes'):
                    st.image(current_analysis['imagem_analise_bytes'], caption="Gráfico EOG a ser anexado.", width=200)


                submitted = st.form_submit_button("💾 Salvar Análise e Gráfico (Etapa 5)", type="primary")

                if submitted:
                    # 1. Transfere a imagem (se gerada) para a lista de Adendos
                    if current_analysis.get('imagem_analise_bytes'):
                        adendo_id = f"Analise_{selected_id}"
                        
                        # Remove a versão antiga do adendo, se existir
                        st.session_state.adendos = [a for a in st.session_state.adendos if not (a.get('origem') == 'analise_eog' and a.get('id_referencia') == adendo_id)]
                        
                        # Adiciona o novo adendo
                        st.session_state.adendos.append({
                            "origem": "analise_eog",
                            "id_referencia": adendo_id,
                            "descricao": f"Análise Gráfica Detalhada (5.0) para {questionado_nome}",
                            "bytes": current_analysis['imagem_analise_bytes'],
                            "filename": f"analise_eog_{selected_id}.png"
                        })
                        
                        # Remove a chave 'imagem_analise_bytes' da análise para não poluir o JSON
                        current_analysis.pop('imagem_analise_bytes', None)
                    
                    # 2. Marca a análise como salva
                    current_analysis['is_saved'] = True

                    # 3. Verifica se todas as análises foram salvas (para concluir a etapa)
                    all_saved = all(item.get('is_saved', False) for item in session_state.analises_eog_list)
                    if all_saved:
                        session_state.etapas_concluidas.add(ETAPA_ID_5)
                    
                    # 4. Salva o estado completo
                    if save_callback():
                        st.success(f"Análise para **{questionado_nome}** salva com sucesso!")
                        if all_saved:
                            st.info("✅ Todas as análises de EOG/Confronto foram salvas. Você pode prosseguir para a próxima etapa.")
                        st.rerun()
                    else:
                        st.error("Falha ao salvar o estado do processo.")


def render_etapa_5(session_state: Dict[str, Any], save_callback: Callable[[], bool]):
    is_completed = ETAPA_ID_5 in session_state.etapas_concluidas
    ETAPA_TITULO = "5. EXAMES PERICIAIS E METODOLOGIA"
    
    with st.expander(f"✅ {ETAPA_TITULO}" if is_completed else f"➡️ {ETAPA_TITULO}", expanded=not is_completed):
        
        # Cria um mapeamento de ID do Questionado para o nome para o Selectbox
        questionados_options = {item['id']: f"{item['TIPO_DOCUMENTO']} ({item['FLS_DOCUMENTOS']})" for item in session_state.questionados_list}
        
        if not questionados_options:
            st.warning("⚠️ Adicione documentos questionados na Etapa 4 para iniciar a análise.")
            return

        st.info("Selecione um documento questionado e preencha a análise dos Elementos de Ordem Gráfica (EOG) e o Confronto Grafoscópico.")
        
        # Renderiza a análise para CADA documento questionado
        for analise_item in session_state.analises_eog_list:
             render_analise_form(analise_item, save_callback, questionados_options, st.session_state.questionados_list[0]['id']) # Sempre expande o primeiro

# RENDERIZAÇÃO 6: CONCLUSÃO (Bloco 6)
def render_etapa_6(session_state: Dict[str, Any], save_callback: Callable[[], bool]):
    is_completed = ETAPA_ID_6 in session_state.etapas_concluidas
    ETAPA_TITULO = "6. CONCLUSÃO"
    
    with st.expander(f"✅ {ETAPA_TITULO}" if is_completed else f"➡️ {ETAPA_TITULO}", expanded=not is_completed):
        
        analises = session_state.get('analises_eog_list', [])
        
        if not analises:
            st.warning("⚠️ Conclua a Etapa 4 (Documentos) e a Etapa 5 (Análise) antes de gerar a Conclusão.")
            return

        st.info("Para cada documento analisado, selecione a conclusão pericial final.")
        
        with st.form("form_etapa_6"):
            
            # Itera sobre CADA item de análise/documento questionado
            for analise in analises:
                questionado_id = analise.get('questionado_id', 'S/N')
                q_item = get_questionado_item(questionado_id, session_state.get('questionados_list', []))
                doc_nome = f"{q_item.get('TIPO_DOCUMENTO', 'S/N')} (Fls. {q_item.get('FLS_DOCUMENTOS', 'S/N')})"
                
                analise['conclusao_status'] = st.selectbox(
                    f"Conclusão para: **{doc_nome}**",
                    options=list(CONCLUSOES_OPCOES.keys()),
                    format_func=lambda x: CONCLUSOES_OPCOES[x],
                    index=list(CONCLUSOES_OPCOES.keys()).index(analise.get('conclusao_status', CONCLUSOES_OPCOES['PENDENTE'])),
                    key=f"conclusao_{analise['id']}"
                )

            st.markdown("---")
            submitted = st.form_submit_button("💾 Gerar Bloco de Conclusão e Salvar", type="primary")

            if submitted:
                # 1. Verifica se todos foram avaliados (não podem ser PENDENTE)
                all_concluded = all(a.get('conclusao_status') in ["AUTENTICA", "FALSA"] for a in analises)

                if all_concluded:
                    session_state.etapas_concluidas.add(ETAPA_ID_6)
                    
                    # 2. Gera e salva o bloco de conclusão dinâmico no session_state
                    final_text = get_final_conclusion_text(session_state)
                    # Adiciona ao session_state para ser usado pelo word_handler.py
                    session_state.BLOCO_CONCLUSAO_DINAMICO = final_text 
                    
                    # 3. Salva o estado completo
                    if save_callback():
                        st.success("Conclusões salvas com sucesso!")
                        st.rerun()
                    else:
                        st.error("Falha ao salvar o estado do processo.")
                else:
                    st.warning("É necessário selecionar um resultado final (**Autêntica** ou **Falsa**) para **TODOS** os documentos questionados.")

        
        # Exibição do resultado (após salvar)
        if ETAPA_ID_6 in session_state.etapas_concluidas:
            st.markdown("##### Prévia do Texto de Conclusão (Bloco 6)")
            st.info("O texto abaixo será inserido no laudo, no campo **[BLOCO_CONCLUSAO_DINAMICO]**.")
            st.markdown(session_state.get('BLOCO_CONCLUSAO_DINAMICO', 'N/A'), unsafe_allow_html=True)


# RENDERIZAÇÃO 7: QUESITOS (Bloco 7)
def render_quesito_form(party_name: str, item: Dict[str, Any], idx: int, save_callback: Callable[[], bool]):
    
    with st.container(border=True):
        st.caption(get_quesito_id_text(party_name, idx))
        
        item['resposta'] = st.text_area(
            "Resposta Pericial",
            value=item.get('resposta', 'Após análise...'),
            key=f"q_resp_{party_name}_{item['id']}"
        )

        st.markdown("---")
        
        # Opções de Referência
        col_ref, col_img, col_rem = st.columns([4, 2, 1])
        
        # Referências
        col_ref.selectbox(
            "Referências para a Resposta (Consulta)",
            options=gather_all_references(st.session_state),
            key=f"q_ref_{party_name}_{item['id']}"
        )
        
        # Imagem para Adendo Fotográfico
        file_bytes = item.get('imagem_bytes')
        uploaded_file = col_img.file_uploader(
            "Anexar Imagem para Adendo",
            type=["png", "jpg", "jpeg"],
            key=f"q_upload_img_{party_name}_{item['id']}"
        )
        
        if uploaded_file is not None:
            file_bytes = uploaded_file.read()
            item['imagem_bytes'] = file_bytes # Salva o objeto binário temporariamente
            item['tem_imagem'] = True
            col_img.image(file_bytes, caption="Imagem Adendo", width=50)

        # Lidar com remoção de imagem/item
        if file_bytes and col_img.button("Remover Imagem", key=f"q_rem_img_{party_name}_{item['id']}", use_container_width=True):
             item.pop('imagem_bytes', None)
             item['tem_imagem'] = False
             st.info("Imagem removida. Clique em 'Salvar' para confirmar.")
             st.rerun()
             
        if col_rem.button("🗑️ Remover Quesito", key=f"q_remove_{party_name}_{item['id']}"):
            remove_quesito_item(f"quesitos_{party_name.lower()}a" if party_name == 'Autora' else f"quesitos_{party_name.lower()}", item['id'])
            save_callback()
            st.rerun()


def render_etapa_7(session_state: Dict[str, Any], save_callback: Callable[[], bool]):
    is_completed = ETAPA_ID_7 in session_state.etapas_concluidas
    ETAPA_TITULO = f"7. RESPOSTA AOS QUESITOS (Fls. {session_state.get('ID_NOMEACAO', 'N/A')})"
    
    with st.expander(f"✅ {ETAPA_TITULO}" if is_completed else f"➡️ {ETAPA_TITULO}", expanded=not is_completed):
        
        if ETAPA_ID_6 not in session_state.etapas_concluidas:
             st.warning("⚠️ Conclua a Etapa 6 (Conclusão) antes de responder aos Quesitos.")
             return
        
        with st.form("form_etapa_7"):
            
            # --- QUESITOS DA AUTORA ---
            st.subheader("Quesitos da Parte Autora")
            session_state.quesitos_autora_data['fls'] = st.text_input(
                "Fls. dos Quesitos da Autora",
                value=session_state.quesitos_autora_data.get('fls', '1-2'),
                key='q_autora_fls'
            )
            
            for idx, item in enumerate(session_state.quesitos_autora_data['list']):
                 render_quesito_form("Autora", item, idx, save_callback)

            col_add_a, _ = st.columns([1, 4])
            if col_add_a.button("➕ Adicionar Quesito Autora", key="add_quesito_autora", type="secondary"):
                add_quesito_item("quesitos_autora", {"resposta": "Resposta pericial...", "tem_imagem": False})
                st.rerun()

            st.markdown("---")
            # --- QUESITOS DO RÉU ---
            st.subheader("Quesitos da Parte Ré")
            session_state.quesitos_reu_data['fls'] = st.text_input(
                "Fls. dos Quesitos da Ré",
                value=session_state.quesitos_reu_data.get('fls', '3-4'),
                key='q_reu_fls'
            )
            
            for idx, item in enumerate(session_state.quesitos_reu_data['list']):
                 render_quesito_form("Réu", item, idx, save_callback)

            col_add_r, _ = st.columns([1, 4])
            if col_add_r.button("➕ Adicionar Quesito Réu", key="add_quesito_reu", type="secondary"):
                add_quesito_item("quesitos_reu", {"resposta": "Resposta pericial...", "tem_imagem": False})
                st.rerun()
            
            st.markdown("---")
            submitted = st.form_submit_button("💾 Salvar Respostas aos Quesitos", type="primary")

            if submitted:
                # 1. Processa imagens e move para a lista de adendos (para o Word)
                process_quesitos_for_adendos(session_state.quesitos_autora_data.get('list', []), "Autora")
                process_quesitos_for_adendos(session_state.quesitos_reu_data.get('list', []), "Réu")
                
                # 2. Gera os blocos de texto finais
                session_state.BLOCO_QUESITOS_AUTOR = generate_quesito_block_text("Autora", session_state.quesitos_autora_data)
                session_state.BLOCO_QUESITOS_REU = generate_quesito_block_text("Réu", session_state.quesitos_reu_data)
                
                # 3. Marca a etapa como concluída
                session_state.etapas_concluidas.add(ETAPA_ID_7)
                
                # 4. Salva o estado completo
                if save_callback():
                    st.success("Respostas aos Quesitos salvas com sucesso!")
                    st.rerun()
                else:
                    st.error("Falha ao salvar o estado do processo.")
        
        # Prévia dos Blocos (após salvar)
        if ETAPA_ID_7 in session_state.etapas_concluidas:
            st.markdown("##### Prévia do Bloco de Quesitos do Laudo")
            st.info("O texto abaixo será inserido no laudo.")
            
            st.markdown("---")
            st.markdown("###### Bloco Quesitos Autora (`[BLOCO_QUESITOS_AUTOR]`)")
            st.markdown(session_state.get('BLOCO_QUESITOS_AUTOR', 'N/A'), unsafe_allow_html=True)
            st.markdown("###### Bloco Quesitos Réu (`[BLOCO_QUESITOS_REU]`)")
            st.markdown(session_state.get('BLOCO_QUESITOS_REU', 'N/A'), unsafe_allow_html=True)


# RENDERIZAÇÃO 8: ENCERRAMENTO E GERAÇÃO (Bloco 8)
def render_etapa_8(session_state: Dict[str, Any], save_callback: Callable[[], bool], project_root: str):
    is_completed = ETAPA_ID_8 in session_state.etapas_concluidas
    ETAPA_TITULO = "8. ENCERRAMENTO E GERAÇÃO DO LAUDO"

    with st.expander(f"✅ {ETAPA_TITULO}" if is_completed else f"➡️ {ETAPA_TITULO}", expanded=not is_completed):
        
        # Pré-requisito: Etapa 7 concluída
        if ETAPA_ID_7 not in session_state.get('etapas_concluidas', set()):
            st.warning("⚠️ **Etapa 7 Incompleta:** Conclua a Resposta aos Quesitos (Etapa 7) para iniciar o Encerramento.")
            return

        st.info("Confirme os dados e gere o arquivo final do Laudo Pericial.")

        # --- Prévia dos Itens a Serem Inseridos ---
        st.subheader("Prévia dos Itens Dinâmicos")
        
        # 1. Lista de Anexos
        st.markdown(f"**Anexos de Documentos Questionados:** {len([a for a in session_state.anexos if a.get('origem') == 'documento_questionado'])} arquivos.")
        
        # 2. Lista de Adendos (EOG e Quesitos)
        st.markdown(f"**Adendos Fotográficos:** {len([a for a in session_state.adendos if a.get('origem') in ['analise_eog', 'quesito']])} arquivos.")
        
        st.markdown("---")
        
        with st.form("form_etapa_8"):
            st.markdown("Clique abaixo para gerar o arquivo `.docx` final.")
            submitted = st.form_submit_button("🚀 Gerar e Finalizar Laudo", type="primary")

            if submitted:
                # 1. Monta os dados simples para o Word Handler
                dados_para_word = {
                    key: session_state.get(key)
                    for key in ['numero_processo', 'AUTOR', 'REU', 'JUIZO_DE_DIREITO', 'ID_NOMEACAO', 'DATA_LAUDO', 
                                'BLOCO_CONCLUSAO_DINAMICO', 'BLOCO_QUESITOS_AUTOR', 'BLOCO_QUESITOS_REU']
                }

                # Adiciona dados da lista de documentos (apenas os campos principais)
                # OBS: O word_handler deve buscar os dados complexos (listas) do session_state, mas aqui passamos os dados simples
                dados_para_word['questionados_list'] = session_state.questionados_list
                dados_para_word['padroes_pce_list'] = session_state.padroes_pce_list
                
                # 2. Caminhos de Geração
                nome_laudo = f"LAUDO_{session_state.numero_processo.replace('.', '_').replace('-', '_')}_{date.today().strftime('%Y%m%d')}"
                caminho_saida = os.path.join(OUTPUT_FOLDER, f"{nome_laudo}.docx")
                caminho_modelo = CAMINHO_MODELO
                
                try:
                    # 3. Chama o Word Handler
                    gerar_laudo(
                        caminho_modelo=caminho_modelo,
                        caminho_saida=caminho_saida,
                        dados=dados_para_word,
                        anexos=session_state.anexos,
                        adendos=session_state.adendos
                    )
                    
                    # 4. Finaliza
                    session_state.etapas_concluidas.add(ETAPA_ID_8)
                    session_state.status = 'Finalizado'
                    
                    if save_callback():
                        st.success(f"Laudo **{session_state.numero_processo}** gerado e salvo com sucesso! Baixe o arquivo abaixo.")
                    
                    # 5. Adiciona botão de download
                    with open(caminho_saida, "rb") as file:
                        st.download_button(
                            label="⬇️ Baixar Laudo .DOCX",
                            data=file,
                            file_name=os.path.basename(caminho_saida),
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                        )
                    st.rerun()

                except FileNotFoundError:
                    st.error(f"❌ Erro de Arquivo: O arquivo de modelo não foi encontrado. Verifique se o arquivo 'LAUDO PERICIAL GRAFOTÉCNICO.docx' está na pasta 'template' na raiz do projeto.")
                except Exception as e:
                    st.error(f"❌ Erro na Geração do Laudo: {e}")


# --- Dashboard (O Fluxo Principal) ---

init_session_state()

st.title("Geração de Laudo Grafotécnico")
st.write("Selecione um processo ativo para continuar ou inicie um novo preenchendo as informações.")

# 1. Seleção e Carregamento de Processo
with st.expander("📂 Carregar Processo Existente", expanded=not st.session_state.process_loaded):
    col1, col2 = st.columns([3, 1])
    process_id_to_load = col1.text_input("Número do Processo a Carregar", key="process_to_load")
    if col2.button("Carregar Dados", use_container_width=True):
        if process_id_to_load:
            load_process(process_id_to_load)
        else:
            st.warning("Insira um número de processo válido.")

st.markdown("---")

# 2. Área de Trabalho Modular (Executado SOMENTE SE um processo estiver carregado)

if st.session_state.process_loaded:
    st.header(f"Processo Atual: `{st.session_state.numero_processo}`")
    st.caption(f"Autor: {st.session_state.get('AUTOR', 'N/A')} | Réu: {st.session_state.get('REU', 'N/A')} | Fls. Nomeação: {st.session_state.get('ID_NOMEACAO', 'N/A')}")
    st.markdown("---")

    # O FLUXO DE TRABALHO: RENDERIZA A PRÓXIMA ETAPA INCOMPLETA

    # MÓDULO 1, 2, 3: APRESENTAÇÃO/OBJETIVOS/INTRODUÇÃO (Blocos 1, 2, 3 - Etapa 1)
    if not (ETAPA_ID_1 in st.session_state.etapas_concluidas and ETAPA_ID_2 in st.session_state.etapas_concluidas and ETAPA_ID_3 in st.session_state.etapas_concluidas):
        render_etapa_1(st.session_state, save_current_state)
    
    # MÓDULO 4: DOCUMENTOS (Bloco 4 - Etapa 4)
    elif ETAPA_ID_4 not in st.session_state.etapas_concluidas:
        st.info("✅ Dados iniciais concluídos. Avance para a Etapa 4.")
        render_etapa_4(st.session_state, save_current_state)
    
    # MÓDULO 5: ANÁLISE PERICIAL (Bloco 5 - Etapa 5)
    elif ETAPA_ID_5 not in st.session_state.etapas_concluidas:
        st.info("✅ Documentos cadastrados. Avance para a Etapa 5.")
        render_etapa_5(st.session_state, save_current_state)

    # MÓDULO 6: CONCLUSÃO (Bloco 6 - Etapa 6)
    elif ETAPA_ID_6 not in st.session_state.etapas_concluidas:
        st.info("✅ Análise EOG/Confronto concluída. Avance para a Etapa 6.")
        render_etapa_6(st.session_state, save_current_state)
        
    # MÓDULO 7: RESPOSTA AOS QUESITOS (Bloco 7 - Etapa 7)
    elif ETAPA_ID_7 not in st.session_state.etapas_concluidas:
        st.info("✅ Conclusão finalizada. Avance para a Etapa 7.")
        render_etapa_7(st.session_state, save_current_state)

    # MÓDULO 8: ENCERRAMENTO (Bloco 8 - Etapa 8)
    elif ETAPA_ID_8 not in st.session_state.etapas_concluidas:
        st.info("✅ Resposta aos Quesitos concluída. Avance para a Etapa 8.")
        render_etapa_8(st.session_state, save_current_state, PROJECT_ROOT)

    else:
        st.success("🎉 Laudo Concluído e Gerado! Você pode gerar novamente na Etapa 8 ou voltar para a tela inicial.")
        render_etapa_8(st.session_state, save_current_state, PROJECT_ROOT) # Permite gerar de novo