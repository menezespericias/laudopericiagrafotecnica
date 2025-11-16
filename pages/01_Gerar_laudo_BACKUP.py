# 01_Gerar_laudo.py — versão atualizada com correções EOG, salvamento, load, e editor de imagens
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
from num2words import num2words  # já usado pelo word_handler

# Tenta importar o editor (opcional). Se não existir, habilita fallback.
try:
    from streamlit_cropper import st_cropper
    from streamlit_drawable_canvas import st_canvas
    from PIL import Image
    EDITOR_AVAILABLE = True
except Exception:
    EDITOR_AVAILABLE = False

# --- Importações dos módulos de backend (Assumindo que estão na pasta 'src' ou na raiz) ---
try:
    from src.word_handler import gerar_laudo
    from src.data_handler import save_process_data, load_process_data
    from src.db_handler import atualizar_status
except Exception:
    # tenta importar do root (caso não tenha movido para src)
    try:
        from word_handler import gerar_laudo
        from data_handler import save_process_data, load_process_data
        from db_handler import atualizar_status
    except Exception as e:
        st.error(f"Erro ao importar módulos backend: {e}. Verifique a estrutura de pastas ('src' ou arquivos na raiz').")
        # define dummies para não quebrar execução
        def gerar_laudo(*a, **k): st.error("word_handler não disponível.")
        def save_process_data(*a, **k): return False
        def load_process_data(*a, **k): return {}
        def atualizar_status(*a, **k): pass

# --- Configuração de paths ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.join(SCRIPT_DIR, '..')
CAMINHO_MODELO = os.path.join(PROJECT_ROOT, "template", "LAUDO PERICIAL GRAFOTÉCNICO.docx")
OUTPUT_FOLDER = os.path.join(PROJECT_ROOT, "output")
DATA_FOLDER = os.path.join(PROJECT_ROOT, "data")
os.makedirs(DATA_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# --------------------------------------------------------------------------------
# Constantes, opções e mapeamentos
# --------------------------------------------------------------------------------

ETAPA_ID_1 = 1
ETAPA_ID_2 = 2
ETAPA_ID_3 = 3
ETAPA_ID_4 = 4
ETAPA_ID_5 = 5
ETAPA_ID_6 = 6
ETAPA_ID_7 = 7
ETAPA_ID_8 = 8

TIPO_DOCUMENTO_OPCOES = [
    "Cédula de Identidade",
    "Procuração",
    "Declaração de Residência",
    "Contrato Social",
    "Outros"
]

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

EOG_OPCOES = {
    "ADEQUADO": "Adequado / Compatível com o padrão",
    "DIVERGENTE": "Divergente / Não compatível",
    "LIMITADO": "Limitação por escassez de material",
    "PENDENTE": "PENDENTE / Não Avaliado"
}

EOG_OPCOES_RADAR = {
    "ADEQUADO": 2,
    "DIVERGENTE": 0,
    "LIMITADO": 1,
    "PENDENTE": 1
}

CONCLUSOES_OPCOES = {
    "AUTENTICA": "Autêntica (Promanou do punho escritor)",
    "FALSA": "Falsa (Não promanou do punho escritor)",
    "PENDENTE": "PENDENTE / Não Avaliada"
}

NO_QUESITOS_TEXT = "Não foram encaminhados quesitos para resposta para o Perito nomeado."

# --------------------------------------------------------------------------------
# Funções utilitárias e inicialização de estado
# --------------------------------------------------------------------------------

def init_session_state():
    """Inicializa chaves essenciais e corrige tipos após o carregamento."""
    if 'etapas_concluidas' not in st.session_state:
        st.session_state.etapas_concluidas = set()
    elif isinstance(st.session_state.etapas_concluidas, list):
        st.session_state.etapas_concluidas = set(st.session_state.etapas_concluidas)

    if 'questionados_list' not in st.session_state: st.session_state.questionados_list = []
    if 'padroes_pce_list' not in st.session_state: st.session_state.padroes_pce_list = []
    if 'analises_eog_list' not in st.session_state: st.session_state.analises_eog_list = []
    if 'anexos' not in st.session_state: st.session_state.anexos = []
    if 'adendos' not in st.session_state: st.session_state.adendos = []

    if 'quesitos_autora_data' not in st.session_state:
        st.session_state.quesitos_autora_data = {"list": [], "nao_enviados": False}
    if 'quesitos_reu_data' not in st.session_state:
        st.session_state.quesitos_reu_data = {"list": [], "nao_enviados": False}

    if 'process_loaded' not in st.session_state:
        st.session_state.process_loaded = False

    if 'CAMINHO_MODELO' not in st.session_state:
        st.session_state.CAMINHO_MODELO = CAMINHO_MODELO

    if 'BLOCO_CONCLUSAO_DINAMICO' not in st.session_state: st.session_state.BLOCO_CONCLUSAO_DINAMICO = ""
    if 'BLOCO_QUESITOS_AUTOR' not in st.session_state: st.session_state.BLOCO_QUESITOS_AUTOR = ""
    if 'BLOCO_QUESITOS_REU' not in st.session_state: st.session_state.BLOCO_QUESITOS_REU = ""

# --------------------------------------------------------------------------------
# Save / Load: serialização robusta e mapeamento de chaves
# --------------------------------------------------------------------------------

def save_current_state() -> bool:
    """
    Salva st.session_state no JSON do processo.
    - Converte set -> list; date/datetime -> string
    - Remove blobs binários antes de salvar
    - Usa save_process_data(process_id, data)
    """
    process_id = st.session_state.get('numero_processo')
    if not process_id:
        st.error("Não foi possível salvar: Número de processo ausente.")
        return False

    raw = dict(st.session_state)

    keys_to_exclude_prefixes = ('input_', 'doc_', 'anexo_', 'quesito_', 'editing_', 'form_')
    keys_to_exclude = {'process_to_load', 'CAMINHO_MODELO'}

    for k in list(raw.keys()):
        if any(k.startswith(pref) for pref in keys_to_exclude_prefixes):
            keys_to_exclude.add(k)
    for k in keys_to_exclude:
        raw.pop(k, None)

    from datetime import date, datetime
    def make_serializable(obj):
        if isinstance(obj, set):
            return list(obj)
        if isinstance(obj, datetime):
            return obj.strftime("%d/%m/%Y %H:%M:%S")
        if isinstance(obj, date):
            return obj.strftime("%d/%m/%Y")
        if isinstance(obj, list):
            new_list = []
            for item in obj:
                if isinstance(item, dict):
                    item = {kk: vv for kk, vv in item.items() if kk not in ('imagem_obj', 'imagem_bytes', 'bytes', 'file_obj')}
                    new_list.append({kk: make_serializable(vv) for kk, vv in item.items()})
                else:
                    new_list.append(make_serializable(item))
            return new_list
        if isinstance(obj, dict):
            new_dict = {}
            for kk, vv in obj.items():
                if kk in ('imagem_obj', 'imagem_bytes', 'bytes', 'file_obj'):
                    continue
                new_dict[kk] = make_serializable(vv)
            return new_dict
        return obj

    serializable_data = {k: make_serializable(v) for k, v in raw.items()}

    if 'etapas_concluidas' in serializable_data and isinstance(serializable_data['etapas_concluidas'], (set, tuple)):
        serializable_data['etapas_concluidas'] = list(serializable_data['etapas_concluidas'])

    serializable_data.setdefault('BLOCO_CONCLUSAO_DINAMICO', '')
    serializable_data.setdefault('BLOCO_QUESITOS_AUTOR', '')
    serializable_data.setdefault('BLOCO_QUESITOS_REU', '')
    serializable_data.setdefault('RESUMO_CABECALHO', '')

    try:
        save_path = save_process_data(process_id, serializable_data)
        return bool(save_path)
    except Exception as e:
        st.error(f"Erro ao salvar o estado do processo: {e}")
        return False

def save_current_state_and_log() -> bool:
    try:
        ok = save_current_state()
        if ok:
            st.success("Estado salvo com sucesso.")
        else:
            st.warning("O estado não pôde ser salvo. Verifique mensagens de erro.")
        return ok
    except Exception as e:
        st.error(f"Erro inesperado ao salvar: {e}")
        return False

def load_process(process_id: str):
    """Carrega dados de um processo existente para st.session_state, com mapeamentos de chaves antigos."""
    try:
        dados_carregados = load_process_data(process_id)

        if dados_carregados:
            st.session_state.clear()

            # Mapeamentos de compatibilidade
            if 'AUTORES' in dados_carregados and 'AUTOR' not in dados_carregados:
                dados_carregados['AUTOR'] = dados_carregados.pop('AUTORES')
            if 'REUS' in dados_carregados and 'REU' not in dados_carregados:
                dados_carregados['REU'] = dados_carregados.pop('REUS')
            if 'NUMERO_PROCESSO' in dados_carregados and 'numero_processo' not in dados_carregados:
                dados_carregados['numero_processo'] = dados_carregados.get('NUMERO_PROCESSO')

            for key, value in dados_carregados.items():
                st.session_state[key] = value

            init_session_state()

            st.session_state.setdefault('AUTOR', st.session_state.get('AUTOR', 'N/A'))
            st.session_state.setdefault('REU', st.session_state.get('REU', 'N/A'))
            st.session_state.process_loaded = True
            st.session_state.numero_processo = process_id

            st.success(f"✅ Processo **{process_id}** carregado com sucesso!")
            st.rerun()
        else:
            st.session_state.process_loaded = False
            st.error(f"❌ Não há dados salvos para o processo **{process_id}**.")
    except FileNotFoundError:
        st.session_state.process_loaded = False
        st.error(f"❌ Arquivo do processo {process_id} não encontrado.")
    except Exception as e:
        st.error(f"❌ Erro ao carregar dados: {e}")

# --------------------------------------------------------------------------------
# Auxiliares de lista / render pequenos formulários (modulares)
# --------------------------------------------------------------------------------

def add_item(list_key: str, default_data: Dict[str, Any]):
    if list_key not in st.session_state:
        st.session_state[list_key] = []
    new_item = {"id": str(uuid.uuid4()), **default_data}
    st.session_state[list_key].append(new_item)

def remove_item(list_key: str, item_id: str):
    if list_key in st.session_state:
        st.session_state[list_key] = [item for item in st.session_state[list_key] if item.get('id') != item_id]
        st.rerun()

def get_analysis_for_questionado(questionado_id: str, session_state: Dict[str, Any]) -> Dict[str, Any]:
    analises_list = session_state.get('analises_eog_list', [])
    for analysis in analises_list:
        if analysis.get('questionado_id') == questionado_id:
            return analysis

    new_analysis = {
        "id": str(uuid.uuid4()),
        "questionado_id": questionado_id,
        "is_saved": False,
        "conclusao_status": "PENDENTE",
        "eog_elements": {key: "PENDENTE" for key in EOG_ELEMENTS.keys()},
        "confronto_texts": {key: "" for key in CONFRONTO_ELEMENTS.keys()},
        "descricao_analise": "",
        "imagem_analise_bytes": None,
        "tem_imagem_analise": False
    }
    session_state.analises_eog_list.append(new_analysis)
    return new_analysis

# --------------------------------------------------------------------------------
# GRÁFICO EOG: implementação robusta e atualizável
# --------------------------------------------------------------------------------

def plot_eog_radar(eog_data: Dict[str, str]):
    """
    Gera e exibe o gráfico de radar corrigido para os Elementos de Ordem Geral (EOG).
    """
    # Ordem fixa para o radar (garante consistência)
    ordered_keys = [
        "HABILIDADE_VELOCIDADE",
        "ESPONTANEIDADE_DINAMISMO",
        "CALIBRE",
        "ALINHAMENTO_GRAFICO",
        "ATAQUES_REMATES"
    ]

    values = [EOG_OPCOES_RADAR.get(eog_data.get(k, "PENDENTE"), 1) for k in ordered_keys]
    values += values[:1]

    labels = [EOG_ELEMENTS[k] for k in ordered_keys]
    labels += labels[:1]

    N = len(ordered_keys)
    angles = [n / float(N) * 2 * 3.14159 for n in range(N)]
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(6,6), subplot_kw=dict(polar=True))
    ax.clear()
    ax.plot(angles, values, linewidth=2, linestyle='solid')
    ax.fill(angles, values, alpha=0.25)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels[:-1], fontsize=9)

    ax.set_yticks([0,1,2])
    ax.set_yticklabels(["Divergente", "Limitado", "Adequado"], color="grey", size=8)
    ax.set_ylim(0,2)

    ax.set_title("Resumo dos Elementos de Ordem Gráfica (EOG)", size=12, y=1.08)

    st.pyplot(fig)

# Mantém compatibilidade com eventuais chamadas a render_radar_chart
def render_radar_chart(eog_data: Dict[str, str]):
    plot_eog_radar(eog_data)

# --------------------------------------------------------------------------------
# Funções auxiliares para geração de blocos do laudo e processamento de adendos / quesitos
# --------------------------------------------------------------------------------

def get_questionado_item(questionado_id: str, questionados_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    return next((item for item in questionados_list if item['id'] == questionado_id), {})

def get_final_conclusion_text(session_state: Dict[str, Any]) -> str:
    analises = session_state.get('analises_eog_list', [])
    questionados = session_state.get('questionados_list', [])
    if not analises:
        return ""
    conclusoes_text = []
    for analise in analises:
        q_id = analise['questionado_id']
        q_item = get_questionado_item(q_id, questionados)
        if not q_item: continue
        status_key = analise.get('conclusao_status')
        status_text = CONCLUSOES_OPCOES.get(status_key, CONCLUSOES_OPCOES["PENDENTE"])
        conclusao_formatada = (
            f"Em relação ao **{q_item.get('TIPO_DOCUMENTO', 'Documento Questionado')}** "
            f"(Grafismo: {q_item.get('DESCRICAO_IMAGEM', 'N/A')}, Fls. {q_item.get('FLS_DOCUMENTOS', 'N/A')}), "
            f"o signatário é levado a CONCLUIR que: **{status_text}**."
        )
        conclusoes_text.append(conclusao_formatada)
    return "\n\n".join(conclusoes_text)

def gather_all_references(session_state: Dict[str, Any]) -> List[str]:
    references = []
    for idx, item in enumerate(session_state.get('questionados_list', [])):
        references.append(f"Doc. Questionado {idx+1}: {item.get('TIPO_DOCUMENTO', 'S/N')} (Fls. {item.get('FLS_DOCUMENTOS', 'S/N')})")
    for idx, item in enumerate(session_state.get('padroes_pce_list', [])):
        tipo = item.get('TIPO_DOCUMENTO_OPCAO', 'S/N')
        if tipo == "Outros":
            tipo = item.get('TIPO_DOCUMENTO_CUSTOM', 'Outros')
        references.append(f"Doc. Padrão {idx+1}: {tipo} (Fls. {item.get('NUMEROS', 'S/N')})")
    for idx, item in enumerate(session_state.get('analises_eog_list', [])):
        q_item = get_questionado_item(item['questionado_id'], session_state.get('questionados_list', []))
        if q_item:
            references.append(f"Análise Gráfica ({idx+1}): {q_item.get('TIPO_DOCUMENTO', 'N/A')} (Fls. {q_item.get('FLS_DOCUMENTOS', 'N/A')})")
    references.append("6. CONCLUSÃO (Bloco de texto final)")
    return references

def process_quesitos_for_adendos(quesitos_list: List[Dict[str, Any]], party_name: str):
    session_state = st.session_state
    existing_adendo_ids = {a['id_adendo'] for a in session_state.adendos if a.get('origem') == f'quesito_{party_name.lower()}'}
    new_adendo_ids = set()
    for idx, quesito in enumerate(quesitos_list):
        quesito_id = quesito['id']
        if quesito.get('imagem_bytes') is not None and quesito_id not in new_adendo_ids:
            adendo_id = str(uuid.uuid4())
            new_adendo_ids.add(quesito_id)
            session_state.adendos = [a for a in session_state.adendos if a.get('id_referencia') != quesito_id]
            session_state.adendos.append({
                "id_adendo": adendo_id,
                "origem": f"quesito_{party_name.lower()}",
                "id_referencia": quesito_id,
                "descricao": f"{get_quesito_id_text(party_name, idx)} (Imagem de Adendo)",
                "bytes": quesito['imagem_bytes'],
                "filename": f"quesito_{party_name.lower()}_{idx+1}.png"
            })
            quesito.pop('imagem_bytes', None)
            quesito['tem_imagem'] = True
        elif quesito.get('imagem_bytes') is None and not quesito.get('tem_imagem', False):
            session_state.adendos = [a for a in session_state.adendos if a.get('id_referencia') != quesito_id]

def get_quesito_id_text(party_name: str, index: int) -> str:
    return f"Quesito da Parte {party_name} nº {index + 1}"

def generate_quesito_block_text(party_name: str, quesitos_data: Dict[str, Any]) -> str:
    if quesitos_data.get('nao_enviados', False):
        return NO_QUESITOS_TEXT
    quesitos_list = quesitos_data.get('list', [])
    if not quesitos_list:
        return NO_QUESITOS_TEXT
    block_text = f"Quesitos da Parte {party_name}"
    for idx, quesito in enumerate(quesitos_list):
        block_text += f"\n\n**{get_quesito_id_text(party_name, idx)}:**"
        resposta = quesito.get('resposta', 'Resposta Pendente.')
        block_text += f"\n{resposta}"
        if quesito.get('referencias'):
            referencias = "\n".join([f"- {ref}" for ref in quesito['referencias']])
            block_text += f"\n\nReferências do Perito:\n{referencias}"
        if quesito.get('tem_imagem', False):
            block_text += f"\n\n(A resposta a este quesito faz referência à Imagem de Adendo de Quesito {idx+1} ao final do Laudo.)"
    return block_text

# --------------------------------------------------------------------------------
# RENDER: pequenos formulários usados por Módulos (para evitar duplicação removi refatoraçoes)
# --------------------------------------------------------------------------------

def render_questionado_form(item: Dict[str, Any], idx: int, save_callback: Callable[[], bool]):
    item_id = item['id']
    with st.container():
        st.caption(f"Documento Questionado {idx+1}")

        col_tipo, col_num, col_desc = st.columns([2,1,3])
        item['TIPO_DOCUMENTO'] = col_tipo.text_input(
            "Tipo do Documento",
            value=item.get('TIPO_DOCUMENTO', f"Doc. Questionado {idx+1}"),
            key=f"doc_q_tipo_{item_id}"
        )
        item['FLS_DOCUMENTOS'] = col_num.text_input(
            "Fls.",
            value=item.get('FLS_DOCUMENTOS', f"10-{idx+10}"),
            key=f"doc_q_fls_{item_id}"
        )
        item['DESCRICAO_IMAGEM'] = col_desc.text_area(
            "Descrição do Grafismo a Ser Analisado (Ex: Assinatura, rubrica, texto)",
            value=item.get('DESCRICAO_IMAGEM', "Assinatura contestada"),
            key=f"doc_q_desc_{item_id}",
            height=80
        )

        col_save, col_delete = st.columns([4,1])

        # botão SALVAR fora de um form (uso direto)
        if col_save.button("💾 Salvar Item", key=f"save_doc_q_{item_id}"):
            item['is_saved'] = True
            if save_callback():
                st.success(f"Documento Questionado {idx+1} salvo!")
            else:
                st.error("Falha ao salvar o estado.")
            st.rerun()

        if col_delete.button("🗑️ Excluir", key=f"delete_doc_q_{item_id}"):
            remove_item("questionados_list", item_id)
            st.session_state.analises_eog_list = [a for a in st.session_state.analises_eog_list if a.get('questionado_id') != item_id]
            st.rerun()

def render_padrao_form(item: Dict[str, Any], idx: int, save_callback: Callable[[], bool]):
    item_id = item['id']
    with st.container():
        st.caption(f"Documento Padrão {idx+1} (Tipo: {item.get('TIPO_DOCUMENTO_OPCAO', 'N/A')})")
        col_tipo, col_num, col_data = st.columns([2,1,2])
        tipo_selecionado = col_tipo.selectbox(
            "Tipo do Documento",
            options=TIPO_DOCUMENTO_OPCOES,
            index=TIPO_DOCUMENTO_OPCOES.index(item.get('TIPO_DOCUMENTO_OPCAO', TIPO_DOCUMENTO_OPCOES[0])),
            key=f"doc_p_tipo_select_{item_id}"
        )
        item['TIPO_DOCUMENTO_OPCAO'] = tipo_selecionado
        item['TIPO_DOCUMENTO_CUSTOM'] = ""
        if tipo_selecionado == "Outros":
            item['TIPO_DOCUMENTO_CUSTOM'] = col_tipo.text_input(
                "Nome do Documento",
                value=item.get('TIPO_DOCUMENTO_CUSTOM', 'Outro Documento'),
                key=f"doc_p_tipo_custom_{item_id}"
            )
        item['NUMEROS'] = col_num.text_input(
            "Fls. / Nº do Documento",
            value=item.get('NUMEROS', 'Fls. X'),
            key=f"doc_p_num_{item_id}"
        )

        data_salva = item.get('DATA_DOCUMENTO')
        if isinstance(data_salva, str):
            try:
                data_obj = datetime.strptime(data_salva, "%d/%m/%Y").date()
            except Exception:
                data_obj = date.today()
        elif isinstance(data_salva, date):
            data_obj = data_salva
        else:
            data_obj = date.today()

        data_input = col_data.date_input(
            "Data do Documento",
            value=data_obj,
            key=f"doc_p_data_{item_id}"
        )
        item['DATA_DOCUMENTO'] = data_input.strftime("%d/%m/%Y")

        item['DESCRICAO_IMAGEM'] = st.text_area(
            "Descrição dos Padrões (Ex: Assinaturas no campo 'testemunha')",
            value=item.get('DESCRICAO_IMAGEM', "Assinatura"),
            key=f"doc_p_desc_{item_id}",
            height=80
        )

        col_save, col_delete = st.columns([4,1])
        if col_save.button("💾 Salvar Item", key=f"save_doc_p_{item_id}"):
            item['is_saved'] = True
            if save_callback():
                st.success(f"Documento Padrão {idx+1} salvo!")
            else:
                st.error("Falha ao salvar o estado.")
            st.rerun()

        if col_delete.button("🗑️ Excluir", key=f"delete_doc_p_{item_id}"):
            remove_item("padroes_pce_list", item_id)
            st.rerun()

# --------------------------------------------------------------------------------
# RENDER ETAPAS (1..8) - mantenho mesma ordem e lógica, alterando Etapa 5 para radar ao vivo e editor de imagem
# --------------------------------------------------------------------------------

def render_etapa_1(session_state: Dict[str, Any], save_callback: Callable[[], bool]):
    ETAPA_TITULO = "1. APRESENTAÇÃO, 2. OBJETIVOS e 3. INTRODUÇÃO"
    is_completed = ETAPA_ID_1 in session_state.etapas_concluidas and ETAPA_ID_2 in session_state.etapas_concluidas and ETAPA_ID_3 in session_state.etapas_concluidas

    with st.expander(f"✅ {ETAPA_TITULO}" if is_completed else f"➡️ {ETAPA_TITULO}", expanded=not is_completed):
        st.markdown("##### 1. APRESENTAÇÃO E 2. OBJETIVOS")
        with st.form("bloco_1_e_2_form"):
            st.info(f"Processo: **{session_state.get('numero_processo', 'N/A')}** | Autor: **{session_state.get('AUTOR', 'N/A')}** | Réu: **{session_state.get('REU', 'N/A')}**")

            col1, col2 = st.columns(2)
            session_state.JUIZO_DE_DIREITO = col1.text_input(
                "Juízo de Direito / Autoridade Solicitante",
                value=session_state.get('JUIZO_DE_DIREITO', 'Excelentíssimo(a) Senhor(a) Doutor(a) Juiz(a) de Direito'),
                key='input_JUIZO_DE_DIREITO'
            )
            session_state.ID_NOMEACAO = col2.text_input(
                "ID Nomeação (Fls. da Nomeação e Documentos Questionados)",
                value=session_state.get('ID_NOMEACAO', '1-2'),
                key='input_ID_NOMEACAO'
            )
            session_state.DATA_LAUDO = col1.date_input(
                "Data do Laudo",
                value=session_state.get('DATA_LAUDO', date.today()),
                key='input_DATA_LAUDO'
            )
            st.markdown("---")
            st.markdown("##### 3. INTRODUÇÃO (Contexto da Perícia)")

            session_state.ID_PADROES = st.text_input(
                "ID Padrões (Fls. dos Padrões Encontrados nos Autos)",
                value=session_state.get('ID_PADROES', '100-110'),
                key='input_ID_PADROES'
            )
            session_state.ID_AUTORIDADE_COLETORA = st.text_input(
                "ID Autoridade Coletora (Ex: Perito, Cartório, Delegacia)",
                value=session_state.get('ID_AUTORIDADE_COLETORA', 'este Perito'),
                key='input_ID_AUTORIDADE_COLETORA'
            )
            session_state.AUTOR_ASSINATURA = st.text_input(
                "Nome Completo do Autor da Assinatura (Contestada)",
                value=session_state.get('AUTOR_ASSINATURA', 'NOME COMPLETO DO AUTOR DA ASSINATURA'),
                key='input_AUTOR_ASSINATURA'
            )
            submitted = st.form_submit_button("💾 Salvar Blocos 1, 2 e 3")
            if submitted:
                session_state.etapas_concluidas.add(ETAPA_ID_1)
                session_state.etapas_concluidas.add(ETAPA_ID_2)
                session_state.etapas_concluidas.add(ETAPA_ID_3)
                if save_callback():
                    st.success("Dados de Apresentação, Objetivos e Introdução salvos com sucesso!")
                    st.rerun()
                else:
                    st.error("Falha ao salvar o estado do processo.")

def render_etapa_4(session_state: Dict[str, Any], save_callback: Callable[[], bool]):
    ETAPA_TITULO = "4. DOCUMENTOS SUBMETIDOS A EXAME"
    is_completed = ETAPA_ID_4 in session_state.etapas_concluidas

    with st.expander(f"✅ {ETAPA_TITULO}" if is_completed else f"➡️ {ETAPA_TITULO}", expanded=not is_completed):
        st.markdown("#### 4.1 Documentos Questionados (PQ)")
        st.info("Cadastre os documentos que contêm o grafismo contestado (Questionados).")

        with st.container():
            for idx, item in enumerate(session_state.questionados_list):
                render_questionado_form(item, idx, save_callback)

            if not session_state.questionados_list:
                st.info("Nenhum documento questionado adicionado.")

            col_add_pq, col_save_pq = st.columns([1,4])
            if col_add_pq.button("➕ Adicionar Questionado (PQ)", key="add_questionado"):
                add_item("questionados_list", {
                    "TIPO_DOCUMENTO": "Doc. Questionado",
                    "FLS_DOCUMENTOS": "Fls. X",
                    "DESCRICAO_IMAGEM": "Assinatura contestada"
                })
                st.rerun()

            if col_save_pq.button("💾 Concluir Etapa 4 (Verificar e Salvar)", key="save_docs_q"):
                if not session_state.questionados_list:
                    st.warning("É obrigatório cadastrar pelo menos um **Documento Questionado**.")
                    return
                is_pca_active = session_state.get('ID_AUTORIDADE_COLETORA', 'este Perito') != '' and session_state.get('COLETA_DE_PADROES_ATIVA', True)
                is_pce_active = len(session_state.padroes_pce_list) > 0
                if not is_pca_active and not is_pce_active:
                    st.warning("É obrigatório cadastrar pelo menos um **Documento Padrão** (PCA ou PCE).")
                    return
                all_q_saved = all(item.get('is_saved', False) for item in session_state.questionados_list)
                all_p_saved = all(item.get('is_saved', False) for item in session_state.padroes_pce_list)
                if not all_q_saved or (is_pce_active and not all_p_saved):
                    st.warning("Salve todos os documentos (Questionados e Padrões) antes de concluir a etapa.")
                    return
                session_state.etapas_concluidas.add(ETAPA_ID_4)
                if save_callback():
                    st.success("Etapa 4 (Documentos) concluída e salva!")
                    st.rerun()
                else:
                    st.error("Falha ao salvar o estado do processo.")

        st.markdown("#### 4.2 Documentos Padrão (PC)")
        st.markdown("##### ➡️ A. Padrões Colhidos no Ato Pericial (PCA)")
        session_state.COLETA_DE_PADROES_ATIVA = st.checkbox(
            "Houve Coleta de Padrões no Ato Pericial (PCA)",
            value=session_state.get('COLETA_DE_PADROES_ATIVA', True),
            key='pca_checkbox'
        )
        if session_state.COLETA_DE_PADROES_ATIVA:
            st.markdown(f"O Perito utilizará o Bloco 4.2 A no laudo, referenciando a autoridade coletora como: **{session_state.get('ID_AUTORIDADE_COLETORA', 'este Perito')}**.")
        else:
            st.warning("O Bloco 4.2 A não será incluído no laudo.")

        st.markdown("##### ➡️ B. Padrões Encontrados nos Autos (PCE)")
        with st.container():
            for idx, item in enumerate(session_state.padroes_pce_list):
                render_padrao_form(item, idx, save_callback)
            if not session_state.padroes_pce_list:
                st.info("Nenhum documento padrão (PCE) adicionado.")
            col_add_pce, col_save_pce = st.columns([1,4])
            if col_add_pce.button("➕ Adicionar Padrão (PCE)", key="add_padrao"):
                add_item("padroes_pce_list", {
                    "TIPO_DOCUMENTO_OPCAO": TIPO_DOCUMENTO_OPCOES[0],
                    "NUMEROS": "Fls. X",
                    "DATA_DOCUMENTO": date.today().strftime("%d/%m/%Y"),
                    "DESCRICAO_IMAGEM": "Assinatura"
                })
                st.rerun()
            if col_save_pce.button("💾 Salvar Documentos Padrão (PCE)", key="save_docs_p"):
                all_p_saved = all(item.get('is_saved', False) for item in session_state.padroes_pce_list)
                if not all_p_saved:
                    st.warning("Salve todos os Documentos Padrão antes de salvar.")
                    return
                if save_callback():
                    st.success("Documentos Padrão (PCE) salvos!")
                    st.rerun()
                else:
                    st.error("Falha ao salvar o estado do processo.")

def render_etapa_5(session_state: Dict[str, Any], save_callback: Callable[[], bool]):
    ETAPA_TITULO = "5. EXAMES PERICIAIS E METODOLOGIA"
    is_completed = ETAPA_ID_5 in session_state.etapas_concluidas

    if ETAPA_ID_4 not in session_state.get('etapas_concluidas', set()):
        st.warning("⚠️ **Etapa 4 Incompleta:** Conclua o cadastro de Documentos (Etapa 4) para iniciar a Análise Pericial.")
        return

    questionados_list = session_state.get('questionados_list', [])
    if not questionados_list:
        st.warning("⚠️ **Documentos Ausentes:** Não há documentos questionados cadastrados para realizar a análise.")
        return

    questionados_options = {
        item['id']: f"Doc. {idx + 1}: {item.get('TIPO_DOCUMENTO', 'S/N')} (Fls. {item.get('FLS_DOCUMENTOS', 'S/N')})"
        for idx, item in enumerate(questionados_list)
    }

    existing_q_ids = {a['questionado_id'] for a in session_state.analises_eog_list}
    for q_id in questionados_options.keys():
        if q_id not in existing_q_ids:
            get_analysis_for_questionado(q_id, session_state)

    with st.expander(f"✅ {ETAPA_TITULO}" if is_completed else f"➡️ {ETAPA_TITULO}", expanded=not is_completed):
        st.markdown("##### 5.0 Selecione o Documento para Análise")
        selected_id = st.selectbox(
            "Selecione o Documento Questionado que deseja analisar:",
            options=list(questionados_options.keys()),
            format_func=lambda x: questionados_options[x],
            key='analise_selected_questionado'
        )
        if not selected_id:
            return st.info("Selecione um documento questionado para iniciar a análise.")

        current_analysis = get_analysis_for_questionado(selected_id, session_state)

        # Form para salvar a análise (submissão)
        with st.form(f"analise_form_{selected_id}"):
            st.markdown("---")
            st.markdown("##### 5.1 Análise dos Paradigmas (EOG - Elementos de Ordem Geral)")

            eog_data = current_analysis['eog_elements']
            col_eog1, col_eog2 = st.columns(2)

            # Selects com keys únicas — valores ficam em st.session_state
            col_eog1.selectbox(
                f"1. {EOG_ELEMENTS['HABILIDADE_VELOCIDADE']}",
                options=list(EOG_OPCOES.keys()),
                format_func=lambda x: EOG_OPCOES[x],
                index=list(EOG_OPCOES.keys()).index(eog_data.get("HABILIDADE_VELOCIDADE", "PENDENTE")),
                key=f'eog_hab_{selected_id}'
            )
            col_eog1.selectbox(
                f"3. {EOG_ELEMENTS['CALIBRE']}",
                options=list(EOG_OPCOES.keys()),
                format_func=lambda x: EOG_OPCOES[x],
                index=list(EOG_OPCOES.keys()).index(eog_data.get("CALIBRE", "PENDENTE")),
                key=f'eog_calibre_{selected_id}'
            )
            col_eog1.selectbox(
                f"5. {EOG_ELEMENTS['ATAQUES_REMATES']}",
                options=list(EOG_OPCOES.keys()),
                format_func=lambda x: EOG_OPCOES[x],
                index=list(EOG_OPCOES.keys()).index(eog_data.get("ATAQUES_REMATES", "PENDENTE")),
                key=f'eog_ataques_{selected_id}'
            )

            col_eog2.selectbox(
                f"2. {EOG_ELEMENTS['ESPONTANEIDADE_DINAMISMO']}",
                options=list(EOG_OPCOES.keys()),
                format_func=lambda x: EOG_OPCOES[x],
                index=list(EOG_OPCOES.keys()).index(eog_data.get("ESPONTANEIDADE_DINAMISMO", "PENDENTE")),
                key=f'eog_esp_{selected_id}'
            )
            col_eog2.selectbox(
                f"4. {EOG_ELEMENTS['ALINHAMENTO_GRAFICO']}",
                options=list(EOG_OPCOES.keys()),
                format_func=lambda x: EOG_OPCOES[x],
                index=list(EOG_OPCOES.keys()).index(eog_data.get("ALINHAMENTO_GRAFICO", "PENDENTE")),
                key=f'eog_alin_{selected_id}'
            )

            st.markdown("##### ➡️ Visualização da Análise de EOG")
            st.info("As alterações nos selects são refletidas automaticamente no gráfico abaixo (visualização ao vivo).")
            # Ao vivo: monta valores a partir de st.session_state (se há interação, os keys dos selectbox são atualizados)
            live_eog = {
                "HABILIDADE_VELOCIDADE": st.session_state.get(f"eog_hab_{selected_id}", current_analysis['eog_elements'].get("HABILIDADE_VELOCIDADE", "PENDENTE")),
                "ESPONTANEIDADE_DINAMISMO": st.session_state.get(f"eog_esp_{selected_id}", current_analysis['eog_elements'].get("ESPONTANEIDADE_DINAMISMO", "PENDENTE")),
                "CALIBRE": st.session_state.get(f"eog_calibre_{selected_id}", current_analysis['eog_elements'].get("CALIBRE", "PENDENTE")),
                "ALINHAMENTO_GRAFICO": st.session_state.get(f"eog_alin_{selected_id}", current_analysis['eog_elements'].get("ALINHAMENTO_GRAFICO", "PENDENTE")),
                "ATAQUES_REMATES": st.session_state.get(f"eog_ataques_{selected_id}", current_analysis['eog_elements'].get("ATAQUES_REMATES", "PENDENTE")),
            }
            plot_eog_radar(live_eog)

            st.markdown("---")
            st.markdown("##### 5.2 Confronto Grafoscópico (Elementos de Ordem Genética/Individual)")
            confronto_texts = current_analysis['confronto_texts']
            for key, description in CONFRONTO_ELEMENTS.items():
                confronto_texts[key] = st.text_area(
                    description,
                    value=confronto_texts.get(key, f"Descrição do Confronto para {description}"),
                    key=f'confronto_text_{key}_{selected_id}',
                    height=100
                )

            st.markdown("---")
            st.markdown("##### 5.3 Descrição da Análise Detalhada (Opcional - Adendo de Imagem)")
            current_analysis['descricao_analise'] = st.text_area(
                "Descrição Detalhada do Exame (Texto livre)",
                value=current_analysis.get('descricao_analise', 'Análise detalhada do grafismo...'),
                key=f'desc_analise_{selected_id}',
                height=150
            )

            # Editor de imagem integrado (opcional)
            col_img_up, col_img_info = st.columns([1,4])
            if EDITOR_AVAILABLE:
                uploaded_file = col_img_up.file_uploader(
                    "Adicionar Imagem para Editar / Anotar (Adendo)",
                    type=['png','jpg','jpeg'],
                    key=f'analise_upload_adendo_{selected_id}'
                )
                if uploaded_file is not None:
                    pil_img = Image.open(uploaded_file).convert("RGBA")
                    st.markdown("**Recorte (Cropper)**")
                    cropped = st_cropper(pil_img, realtime_update=True, box_color="#0000FF")
                    st.markdown("**Desenhe sobre a imagem (linhas, setas, formas)**")
                    canvas_result = st_canvas(
                        fill_color="rgba(255, 165, 0, 0.3)",
                        stroke_width=3,
                        stroke_color="#FF0000",
                        background_image=cropped,
                        update_streamlit=True,
                        height=400,
                        drawing_mode="freedraw"
                    )
                    if canvas_result.image_data is not None:
                        img = Image.fromarray(canvas_result.image_data.astype('uint8'), 'RGBA')
                        buf = io.BytesIO()
                        img.save(buf, format="PNG")
                        img_bytes = buf.getvalue()
                        # salva no current analysis como adendo
                        current_analysis['imagem_analise_bytes'] = img_bytes
                        current_analysis['tem_imagem_analise'] = True
                        col_img_up.image(img_bytes, caption="Imagem Anotada", use_column_width=True)
                else:
                    # fallback se já tiver um adendo salvo
                    if current_analysis.get('tem_imagem_analise', False):
                        col_img_info.info("Adendo de imagem de análise já salvo.")
            else:
                uploaded_file = col_img_up.file_uploader(
                    "Adicionar Imagem de Análise (Adendo)",
                    type=['png','jpg','jpeg'],
                    key=f'analise_upload_adendo_{selected_id}'
                )
                if uploaded_file is not None:
                    file_bytes = uploaded_file.read()
                    current_analysis['imagem_analise_bytes'] = file_bytes
                    current_analysis['tem_imagem_analise'] = True
                    col_img_up.image(file_bytes, caption="Imagem para Adendo Carregada", use_column_width=True)
                elif current_analysis.get('tem_imagem_analise', False):
                    col_img_info.info("Adendo de imagem de análise já salvo.")

            submitted = st.form_submit_button("💾 Salvar Análise (5.1 e 5.2)")
            if submitted:
                # Atualiza o objeto current_analysis a partir dos campos "ao vivo"
                # garante que st.session_state valores estejam persistidos no objeto
                current_analysis['eog_elements'] = {
                    "HABILIDADE_VELOCIDADE": st.session_state.get(f"eog_hab_{selected_id}", current_analysis['eog_elements'].get("HABILIDADE_VELOCIDADE", "PENDENTE")),
                    "ESPONTANEIDADE_DINAMISMO": st.session_state.get(f"eog_esp_{selected_id}", current_analysis['eog_elements'].get("ESPONTANEIDADE_DINAMISMO", "PENDENTE")),
                    "CALIBRE": st.session_state.get(f"eog_calibre_{selected_id}", current_analysis['eog_elements'].get("CALIBRE", "PENDENTE")),
                    "ALINHAMENTO_GRAFICO": st.session_state.get(f"eog_alin_{selected_id}", current_analysis['eog_elements'].get("ALINHAMENTO_GRAFICO", "PENDENTE")),
                    "ATAQUES_REMATES": st.session_state.get(f"eog_ataques_{selected_id}", current_analysis['eog_elements'].get("ATAQUES_REMATES", "PENDENTE")),
                }
                image_bytes = current_analysis.get('imagem_analise_bytes')
                if image_bytes:
                    adendo_id = str(uuid.uuid4())
                    session_state.adendos = [a for a in session_state.adendos if a.get('origem') != 'analise_eog' or a.get('id_referencia') != selected_id]
                    session_state.adendos.append({
                        "id_adendo": adendo_id,
                        "origem": "analise_eog",
                        "id_referencia": selected_id,
                        "descricao": f"Análise Gráfica Detalhada (5.0) para {questionados_options[selected_id]}",
                        "bytes": image_bytes,
                        "filename": f"analise_{selected_id}.png"
                    })
                    current_analysis.pop('imagem_analise_bytes', None)
                current_analysis['is_saved'] = True
                all_saved = all(item.get('is_saved', False) for item in session_state.analises_eog_list)
                if all_saved:
                    session_state.etapas_concluidas.add(ETAPA_ID_5)
                if save_callback():
                    st.success(f"Análise para **{questionados_options[selected_id]}** salva com sucesso!")
                    if all_saved:
                        st.info("✅ Todas as análises de EOG/Confronto foram salvas. Você pode prosseguir para a próxima etapa.")
                    st.rerun()
                else:
                    st.error("Falha ao salvar o estado do processo.")

def render_etapa_6(session_state: Dict[str, Any], save_callback: Callable[[], bool]):
    ETAPA_TITULO = "6. CONCLUSÃO"
    is_completed = ETAPA_ID_6 in session_state.etapas_concluidas
    if ETAPA_ID_5 not in session_state.get('etapas_concluidas', set()):
        st.warning("⚠️ **Etapa 5 Incompleta:** Conclua a Análise Pericial (Etapa 5) para gerar a Conclusão.")
        return
    analises = session_state.get('analises_eog_list', [])
    questionados = session_state.get('questionados_list', [])
    if not analises:
        st.info("Não há documentos questionados com análise para gerar conclusões.")
        return
    with st.expander(f"✅ {ETAPA_TITULO}" if is_completed else f"➡️ {ETAPA_TITULO}", expanded=not is_completed):
        st.markdown("##### ➡️ Conclusão Individual para cada Documento Questionado")
        with st.form("conclusao_form"):
            for idx, analise in enumerate(analises):
                q_id = analise['questionado_id']
                q_item = get_questionado_item(q_id, questionados)
                if not q_item:
                    st.warning(f"Documento questionado de ID {q_id} não encontrado. Ignorando.")
                    continue
                st.markdown(f"**Documento Questionado {idx+1}:** {q_item.get('TIPO_DOCUMENTO', 'N/A')} (Fls. {q_item.get('FLS_DOCUMENTOS', 'N/A')})")
                analise['conclusao_status'] = st.selectbox(
                    "Resultado da Perícia:",
                    options=list(CONCLUSOES_OPCOES.keys()),
                    format_func=lambda x: CONCLUSOES_OPCOES[x],
                    index=list(CONCLUSOES_OPCOES.keys()).index(analise.get('conclusao_status', "PENDENTE")),
                    key=f'conclusao_status_{q_id}'
                )
                analise['justificativa_conclusao'] = st.text_area(
                    "Justificativa para a Conclusão (Texto Opcional, para consulta interna)",
                    value=analise.get('justificativa_conclusao', 'Justificar se a conclusão é Autêntica ou Falsa.'),
                    key=f'justificativa_conclusao_{q_id}',
                    height=100
                )
                if analise['conclusao_status'] == "FALSA":
                    analise['is_simulacao'] = st.checkbox(
                        "Adicionar texto sobre 'Esforço e simulação por terceiro' no bloco de justificativa",
                        value=analise.get('is_simulacao', False),
                        key=f'simulacao_checkbox_{q_id}'
                    )
                else:
                    analise.pop('is_simulacao', None)
                st.markdown("---")
            submitted = st.form_submit_button("💾 Gerar e Salvar Conclusão Final")
            if submitted:
                all_concluded = all(a.get('conclusao_status') in ["AUTENTICA", "FALSA"] for a in analises)
                if all_concluded:
                    session_state.etapas_concluidas.add(ETAPA_ID_6)
                    final_text = get_final_conclusion_text(session_state)
                    session_state.BLOCO_CONCLUSAO_DINAMICO = final_text
                    if save_callback():
                        st.success("Conclusões salvas com sucesso!")
                        st.rerun()
                    else:
                        st.error("Falha ao salvar o estado do processo.")
                else:
                    st.warning("É necessário selecionar um resultado final (Autêntica ou Falsa) para TODOS os documentos questionados.")
        if ETAPA_ID_6 in session_state.etapas_concluidas:
            st.markdown("##### Prévia do Texto de Conclusão (Bloco 6)")
            st.markdown(session_state.get('BLOCO_CONCLUSAO_DINAMICO', 'N/A'))

def render_quesito_form(quesito: Dict[str, Any], idx: int, party_name: str, fls_text: str, references: List[str]):
    quesito_id = quesito['id']
    st.markdown(f"**{get_quesito_id_text(party_name, idx)}**")
    col_fls, col_save_state = st.columns([4,1])
    quesito['fls'] = col_fls.text_input(
        "Fls. (Onde o quesito está no processo)",
        value=quesito.get('fls', fls_text),
        key=f'quesito_{party_name.lower()}_fls_{quesito_id}'
    )
    quesito['texto'] = st.text_area(
        "Texto do Quesito (Referência)",
        value=quesito.get('texto', f"Quesito {idx+1}"),
        key=f'quesito_{party_name.lower()}_texto_{quesito_id}',
        height=70
    )
    quesito['resposta'] = st.text_area(
        "Resposta do Perito (Texto que irá para o Laudo)",
        value=quesito.get('resposta', 'Com base nos exames realizados, o Perito responde:'),
        key=f'quesito_{party_name.lower()}_resposta_{quesito_id}',
        height=150
    )
    referencias_selecionadas = st.multiselect(
        "Selecione as referências que sustentam a resposta (Opcional)",
        options=references,
        default=quesito.get('referencias', []),
        key=f'quesito_{party_name.lower()}_refs_{quesito_id}'
    )
    quesito['referencias'] = referencias_selecionadas

    col_img, col_info = st.columns([1,4])
    tem_imagem_previa = quesito.get('tem_imagem', False)
    uploaded_file = col_img.file_uploader(
        "Adicionar Imagem (Adendo de Quesito)",
        type=['png','jpg','jpeg'],
        key=f'quesito_{party_name.lower()}_upload_{quesito_id}'
    )
    if uploaded_file is not None:
        file_bytes = uploaded_file.read()
        quesito['imagem_bytes'] = file_bytes
        quesito['tem_imagem'] = True
        col_img.image(file_bytes, caption="Imagem Carregada", use_column_width=True)
    elif tem_imagem_previa:
        col_img.info("Adendo de imagem já salvo para este quesito.")
    if col_save_state.button("🗑️ Excluir Quesito", key=f'delete_quesito_{party_name.lower()}_{quesito_id}'):
        quesito_list_key = f'quesitos_{party_name.lower()}_data'
        if quesito_list_key in st.session_state:
            st.session_state[quesito_list_key]['list'] = [item for item in st.session_state[quesito_list_key]['list'] if item.get('id') != quesito_id]
        st.rerun()

def render_quesitos_party(session_state: Dict[str, Any], party_name: str, fls_text: str, save_callback: Callable[[], bool], references: List[str]):
    state_key = f'quesitos_{party_name.lower()}_data'
    if state_key not in session_state:
        session_state[state_key] = {"list": [], "nao_enviados": False}
    nao_enviados = st.checkbox(
        f"A Parte **{party_name}** não encaminhou quesitos",
        value=session_state[state_key]['nao_enviados'],
        key=f'{state_key}_nao_enviados_checkbox'
    )
    session_state[state_key]['nao_enviados'] = nao_enviados
    if nao_enviados:
        st.info(f"O bloco de resposta para a Parte {party_name} será o texto padrão.")
        session_state[state_key]['list'] = []
        return
    for idx, quesito in enumerate(session_state[state_key]['list']):
        with st.expander(get_quesito_id_text(party_name, idx), expanded=False):
            render_quesito_form(quesito, idx, party_name, fls_text, references)
    if st.button(f"➕ Adicionar Quesito da Parte {party_name}", key=f'add_quesito_{party_name.lower()}'):
        new_quesito = {
            "id": str(uuid.uuid4()),
            "fls": fls_text,
            "texto": f"Quesito {len(session_state[state_key]['list']) + 1} da Parte {party_name}",
            "resposta": 'Com base nos exames realizados, o Perito responde:',
            "referencias": [],
            "imagem_bytes": None,
            "tem_imagem": False
        }
        session_state[state_key]['list'].append(new_quesito)
        st.rerun()

def render_etapa_7(session_state: Dict[str, Any], save_callback: Callable[[], bool]):
    ETAPA_TITULO = "7. RESPOSTA AOS QUESITOS"
    is_completed = ETAPA_ID_7 in session_state.etapas_concluidas
    if ETAPA_ID_6 not in session_state.get('etapas_concluidas', set()):
        st.warning("⚠️ **Etapa 6 Incompleta:** Conclua a Conclusão (Etapa 6) para iniciar a Resposta aos Quesitos.")
        return
    references = gather_all_references(session_state)
    with st.expander(f"✅ {ETAPA_TITULO}" if is_completed else f"➡️ {ETAPA_TITULO}", expanded=not is_completed):
        with st.form("quesitos_form"):
            st.markdown("#### 7.1 Quesitos da Parte Autora")
            render_quesitos_party(session_state=session_state, party_name="Autora",
                                  fls_text=f"Fls. {session_state.get('ID_NOMEACAO', '1-2')}", save_callback=save_callback, references=references)
            st.markdown("---")
            st.markdown("#### 7.2 Quesitos da Parte Ré")
            render_quesitos_party(session_state=session_state, party_name="Réu",
                                  fls_text="Fls. 50-60", save_callback=save_callback, references=references)
            st.markdown("---")
            submitted = st.form_submit_button("💾 Salvar Respostas aos Quesitos")
            if submitted:
                process_quesitos_for_adendos(session_state.quesitos_autora_data.get('list', []), "Autora")
                process_quesitos_for_adendos(session_state.quesitos_reu_data.get('list', []), "Réu")
                session_state.BLOCO_QUESITOS_AUTOR = generate_quesito_block_text("Autora", session_state.quesitos_autora_data)
                session_state.BLOCO_QUESITOS_REU = generate_quesito_block_text("Réu", session_state.quesitos_reu_data)
                session_state.etapas_concluidas.add(ETAPA_ID_7)
                if save_callback():
                    st.success("Respostas aos Quesitos salvas com sucesso!")
                    st.rerun()
                else:
                    st.error("Falha ao salvar o estado do processo.")
        if ETAPA_ID_7 in session_state.etapas_concluidas:
            st.markdown("##### Prévia do Bloco de Quesitos do Laudo")
            st.markdown("---")
            st.markdown("###### Bloco Quesitos Autora (`[BLOCO_QUESITOS_AUTOR]`)")
            st.markdown(session_state.get('BLOCO_QUESITOS_AUTOR', 'N/A'))
            st.markdown("---")
            st.markdown("###### Bloco Quesitos Réu (`[BLOCO_QUESITOS_REU]`)")
            st.markdown(session_state.get('BLOCO_QUESITOS_REU', 'N/A'))

def find_anexo_for_questionado(q_id: str, anexos: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    return next((a for a in anexos if a.get('origem') == 'documento_questionado' and a.get('id_referencia') == q_id), None)

def render_anexo_upload_form(q_item: Dict[str, Any], anexos: List[Dict[str, Any]], session_state: Dict[str, Any], save_callback: Callable[[], bool]):
    q_id = q_item['id']
    anexo_existente = find_anexo_for_questionado(q_id, anexos)
    descricao = f"ANEXO para {q_item.get('TIPO_DOCUMENTO', 'Documento')} (Fls. {q_item.get('FLS_DOCUMENTOS', 'N/A')})"
    with st.container():
        st.caption(descricao)
        col1, col2 = st.columns([4,1])
        if anexo_existente:
            col1.info("Anexo de documento questionado já carregado.")
            if col2.button("🗑️ Excluir Anexo", key=f'delete_anexo_{q_id}'):
                session_state.anexos = [a for a in session_state.anexos if a.get('id_referencia') != q_id]
                if save_callback():
                    st.success(f"Anexo de {q_item.get('TIPO_DOCUMENTO')} excluído.")
                st.rerun()
        else:
            uploaded_file = col1.file_uploader(
                f"Upload do Arquivo (ANEXO)",
                type=['pdf','png','jpg','jpeg'],
                key=f'anexo_upload_{q_id}'
            )
            if uploaded_file is not None:
                file_bytes = uploaded_file.read()
                file_name = uploaded_file.name
                session_state.anexos.append({
                    "id": str(uuid.uuid4()),
                    "origem": "documento_questionado",
                    "id_referencia": q_id,
                    "descricao": descricao,
                    "bytes": file_bytes,
                    "filename": file_name,
                    "mime_type": uploaded_file.type
                })
                if save_callback():
                    st.success(f"Anexo de {q_item.get('TIPO_DOCUMENTO')} carregado com sucesso!")
                st.rerun()
            else:
                col2.empty()

def render_etapa_8(session_state: Dict[str, Any], save_callback: Callable[[], bool], project_root: str):
    ETAPA_TITULO = "8. ENCERRAMENTO E GERAÇÃO DO LAUDO"
    is_completed = ETAPA_ID_8 in session_state.etapas_concluidas
    if ETAPA_ID_7 not in session_state.get('etapas_concluidas', set()):
        st.warning("⚠️ **Etapa 7 Incompleta:** Conclua a Resposta aos Quesitos (Etapa 7) para iniciar o Encerramento.")
        return
    with st.expander(f"✅ {ETAPA_TITULO}" if is_completed else f"➡️ {ETAPA_TITULO}", expanded=True):
        st.markdown("##### ➡️ Anexos de Documentos Questionados (Etapa 4.1)")
        questionados = session_state.get('questionados_list', [])
        anexos = session_state.get('anexos', [])
        if not questionados:
            st.info("Nenhum documento questionado cadastrado na Etapa 4.")
        else:
            for q_item in questionados:
                render_anexo_upload_form(q_item, anexos, session_state, save_callback)
        st.markdown("---")
        st.markdown("##### ➡️ Adendos (Imagens de Análise e Quesitos)")
        adendos = session_state.get('adendos', [])
        if not adendos:
            st.info("Nenhum adendo de imagem (Análise ou Quesitos) foi gerado.")
        else:
            st.caption(f"Total de {len(adendos)} adendos gerados.")
            for adendo in adendos:
                st.markdown(f"* 🖼️ **{adendo.get('descricao', 'Adendo Sem Descrição')}** (Origem: {adendo.get('origem', 'N/A')})")
        st.markdown("---")
        col_save_anexos, _ = st.columns([3,1])
        if col_save_anexos.button("💾 Salvar Anexos e Adendos (Pré-Geração)"):
            if save_callback():
                st.success("Dados de encerramento salvos!")
                st.rerun()
            else:
                st.error("Falha ao salvar o estado do processo.")
        st.markdown("---")
        if st.button("🚀 GERAR LAUDO FINAL (.DOCX)"):
            dados_para_word = {
                'numero_processo': session_state.get('numero_processo'),
                'AUTOR': session_state.get('AUTOR', 'N/A'),
                'REU': session_state.get('REU', 'N/A'),
                'BLOCO_CONCLUSAO_DINAMICO': session_state.get('BLOCO_CONCLUSAO_DINAMICO', ''),
                'BLOCO_QUESITOS_AUTOR': session_state.get('BLOCO_QUESITOS_AUTOR', ''),
                'BLOCO_QUESITOS_REU': session_state.get('BLOCO_QUESITOS_REU', ''),
                'questionados_list': session_state.get('questionados_list', []),
                'padroes_pce_list': session_state.get('padroes_pce_list', []),
                'analises_eog_list': session_state.get('analises_eog_list', [])
            }
            now = datetime.now().strftime("%Y%m%d_%H%M%S")
            caminho_saida = os.path.join(OUTPUT_FOLDER, f"{session_state.numero_processo}_LAUDO_{now}.docx")
            caminho_modelo = session_state.get('CAMINHO_MODELO', CAMINHO_MODELO)
            try:
                gerar_laudo(
                    caminho_modelo=caminho_modelo,
                    caminho_saida=caminho_saida,
                    dados=dados_para_word,
                    anexos=session_state.anexos,
                    adendos=session_state.adendos
                )
                session_state.etapas_concluidas.add(ETAPA_ID_8)
                if save_callback():
                    st.success(f"Laudo **{session_state.numero_processo}** gerado com sucesso em {caminho_saida}!")
                    with open(caminho_saida, "rb") as file:
                        st.download_button(
                            label="⬇️ Baixar Laudo .DOCX",
                            data=file,
                            file_name=os.path.basename(caminho_saida),
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                        )
                    st.balloons()
                else:
                    st.success("Laudo gerado, porém falha ao salvar estado.")
            except FileNotFoundError:
                st.error(f"❌ Arquivo de modelo não encontrado: {caminho_modelo}")
            except Exception as e:
                st.error(f"❌ Erro na Geração do Laudo: {e}")

# --------------------------------------------------------------------------------
# Execução principal do dashboard
# --------------------------------------------------------------------------------

init_session_state()

st.title("Geração de Laudo Grafotécnico")
st.write("Selecione um processo ativo para continuar ou inicie um novo preenchendo as informações.")

with st.expander("📂 Carregar Processo Existente", expanded=not st.session_state.process_loaded):
    col1, col2 = st.columns([3,1])
    process_id_to_load = col1.text_input("Número do Processo a Carregar", key="process_to_load")
    if col2.button("Carregar Dados"):
        if process_id_to_load:
            load_process(process_id_to_load)
        else:
            st.warning("Insira um número de processo válido.")

st.markdown("---")

if st.session_state.process_loaded:
    st.header(f"Processo Atual: `{st.session_state.numero_processo}`")
    st.caption(f"Autor: {st.session_state.get('AUTOR', 'N/A')} | Réu: {st.session_state.get('REU', 'N/A')}")
    st.caption(f"Juízo: {st.session_state.get('JUIZO_DE_DIREITO', 'N/A')}")

    def save_current_state_and_log_wrapper():
        return save_current_state_and_log()

    if ETAPA_ID_1 not in st.session_state.etapas_concluidas:
        st.info("Inicie preenchendo as informações de Apresentação/Objetivos/Introdução (Etapas 1,2,3).")
        render_etapa_1(st.session_state, save_current_state_and_log_wrapper)
    elif ETAPA_ID_4 not in st.session_state.etapas_concluidas:
        st.info("✅ Dados iniciais concluídos. Avance para a Etapa 4.")
        render_etapa_4(st.session_state, save_current_state_and_log_wrapper)
    elif ETAPA_ID_5 not in st.session_state.etapas_concluidas:
        render_etapa_5(st.session_state, save_current_state_and_log_wrapper)
    elif ETAPA_ID_6 not in st.session_state.etapas_concluidas:
        render_etapa_6(st.session_state, save_current_state_and_log_wrapper)
    elif ETAPA_ID_7 not in st.session_state.etapas_concluidas:
        render_etapa_7(st.session_state, save_current_state_and_log_wrapper)
    else:
        render_etapa_8(st.session_state, save_current_state_and_log_wrapper, PROJECT_ROOT)
else:
    st.info("Carregue ou crie um processo para iniciar o preenchimento.")

# --------------------------------------------------------------------------------
# Fim do arquivo
# --------------------------------------------------------------------------------
