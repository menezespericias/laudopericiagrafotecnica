# ======================================================================
# 01_Gerar_laudo.py
# Sistema de Geração de Laudo Pericial Grafotécnico
# Versão revisada por ChatGPT – com melhorias de EOG, Editor de Imagem (Mesa Gráfica)
# ======================================================================

# ------------------------------
# IMPORTS ROBUSTOS
# ------------------------------
import streamlit as st
import uuid
import json
import os
import io
import datetime
from datetime import date, datetime as dt_datetime
from typing import Dict, Any, Callable, List
import matplotlib.pyplot as plt
from io import BytesIO
from PIL import Image

# Tentativa de import dos módulos backend em 'src', com fallback para raiz
try:
    from src.data_handler import save_process_data, load_process_data, list_processes, PROCESS_DATA_DIR
    from src.word_handler import generate_report_from_template
    from src.db_handler import atualizar_status
except Exception:
    try:
        from data_handler import save_process_data, load_process_data, list_processes, PROCESS_DATA_DIR
        from word_handler import generate_report_from_template
        from db_handler import atualizar_status
    except Exception as exc_import:
        st.error(f"⚠️ Falha ao importar módulos backend (src/ ou raiz). Alguns recursos podem não funcionar: {exc_import}")

        # stubs seguros para evitar crash da interface — exibem erro se usados
        def save_process_data(*a, **k):
            st.error("save_process_data indisponível (import falhou)")
            return False

        def load_process_data(*a, **k):
            st.error("load_process_data indisponível (import falhou)")
            return {}

        def list_processes(*a, **k):
            return []

        def generate_report_from_template(*a, **k):
            raise FileNotFoundError("generate_report_from_template indisponível (import falhou)")

        def atualizar_status(*a, **k):
            pass

# ------------------------------
# Tenta habilitar editor (dependências opcionais)
# ------------------------------
EDITOR_AVAILABLE = True
try:
    # streamlit-cropper / drawable canvas são opcionais: checar disponibilidade
    from streamlit_cropper import st_cropper
    from streamlit_drawable_canvas import st_canvas
except Exception:
    EDITOR_AVAILABLE = False
    # não falhar se não instalado; a UI mostrará aviso quando usuário tentar usar

# ------------------------------
# CONFIGURAÇÕES GERAIS DA PÁGINA
# ------------------------------
st.set_page_config(
    page_title="Gerar Laudo Pericial Grafotécnico",
    layout="wide",
    page_icon="✒️"
)

# ------------------------------
# PASTAS DO PROJETO
# ------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
TEMPLATE_FOLDER = os.path.join(PROJECT_ROOT, "template")
DATA_FOLDER = os.path.join(PROJECT_ROOT, "data")
OUTPUT_FOLDER = os.path.join(PROJECT_ROOT, "output")

os.makedirs(DATA_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# ------------------------------
# CONSTANTES / ENUMS / MAPEAMENTOS
# ------------------------------
ETAPA_ID_1 = 1
ETAPA_ID_2 = 2
ETAPA_ID_3 = 3
ETAPA_ID_4 = 4
ETAPA_ID_5 = 5
ETAPA_ID_6 = 6
ETAPA_ID_7 = 7
ETAPA_ID_8 = 8

EOG_ELEMENTS = {
    "HABILIDADE_VELOCIDADE": "Habilidade / Velocidade",
    "ESPONTANEIDADE_DINAMISMO": "Espontaneidade / Dinamismo",
    "CALIBRE": "Calibre",
    "ALINHAMENTO_GRAFICO": "Alinhamento Gráfico",
    "ATAQUES_REMATES": "Ataques / Remates"
}

EOG_OPCOES = ["ADEQUADO", "LIMITADO", "DIVERGENTE", "PENDENTE"]

EOG_OPCOES_RADAR = {
    "ADEQUADO": 2,
    "LIMITADO": 1,
    "DIVERGENTE": 0,
    "PENDENTE": 1
}

CONFRONTO_ELEMENTS = {
    "NATUREZA_GESTO": "Natureza do gesto gráfico (velocidade/pressão/spontaneidade).",
    "MORFOLOGIA": "Morfologia das letras e dimensão.",
    "VALORES_ANGULARES": "Valores angulares e curvaturas predominantes.",
    "ATAQUES_REMATES_5_2": "Ataques e remates - características de início/fim de traço.",
    "PONTOS_CONEXAO": "Pontos de conexão entre elementos gráficos."
}

CONCLUSOES_OPCOES = {
    "AUTENTICA": "Autêntica",
    "FALSA": "Falsa",
    "PENDENTE": "PENDENTE"
}

# ------------------------------
# UTILITÁRIOS DE SESSÃO E INICIALIZAÇÃO
# ------------------------------
def ensure_session_defaults():
    """
    Inicializa chaves essenciais em st.session_state de forma idempotente.
    Substitua/adicione aqui se sua app precisar de mais chaves.
    """
    defaults = {
        "process_loaded": False,
        "selected_process_id": None,
        "etapas_concluidas": set(),
        "questionados_list": [],
        "padroes_list": [],
        "anexos": [],
        "adendos": [],
        "saved_analyses": {},
        "quesitos_autora_data": {"list": [], "nao_enviados": False},
        "quesitos_reu_data": {"list": [], "nao_enviados": False},
        "AUTOR": "",
        "REU": "",
        "DATA_LAUDO": date.today(),
        "BLOCO_CONCLUSAO_DINAMICO": "",
        "BLOCO_QUESITOS_AUTOR": "",
        "BLOCO_QUESITOS_REU": ""
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
        else:
            # corrige formatos (ex.: se carregou de JSON com listas)
            if k == "etapas_concluidas" and isinstance(st.session_state[k], list):
                st.session_state[k] = set(st.session_state[k])

ensure_session_defaults()

# ------------------------------
# FUNÇÕES DE SAVE / LOAD (serialização robusta)
# ------------------------------
def _make_serializable(obj):
    """Recursivamente converte tipos não-serializáveis para JSON-serializable."""
    from datetime import date, datetime as _dt
    if isinstance(obj, set):
        return list(obj)
    if isinstance(obj, _dt):
        return obj.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _make_serializable(v) for k, v in obj.items() if k not in ("imagem_obj", "imagem_bytes", "file_obj", "bytes")}
    if isinstance(obj, list):
        return [_make_serializable(i) for i in obj]
    return obj

def save_current_state(data: dict = None) -> bool:
    """
    Salva estado do processo no arquivo JSON. Se 'data' for None, salva um conjunto padrão de chaves.
    Retorna True se salvo com sucesso.
    """
    try:
        process_id = st.session_state.get("selected_process_id")
        if not process_id:
            st.error("Número do processo não informado. Não foi possível salvar.")
            return False

        if data is None:
            # salva conjunto mínimo
            data = {
                "AUTOR": st.session_state.get("AUTOR"),
                "REU": st.session_state.get("REU"),
                "DATA_LAUDO": st.session_state.get("DATA_LAUDO").isoformat() if isinstance(st.session_state.get("DATA_LAUDO"), date) else st.session_state.get("DATA_LAUDO"),
                "questionados_list": st.session_state.get("questionados_list", []),
                "padroes_list": st.session_state.get("padroes_list", []),
                "saved_analyses": st.session_state.get("saved_analyses", {}),
                "anexos": st.session_state.get("anexos", []),
                "adendos": st.session_state.get("adendos", []),
                "etapas_concluidas": list(st.session_state.get("etapas_concluidas", [])),
                "BLOCO_CONCLUSAO_DINAMICO": st.session_state.get("BLOCO_CONCLUSAO_DINAMICO", ""),
                "BLOCO_QUESITOS_AUTOR": st.session_state.get("BLOCO_QUESITOS_AUTOR", ""),
                "BLOCO_QUESITOS_REU": st.session_state.get("BLOCO_QUESITOS_REU", "")
            }

        serializable = _make_serializable(data)
        save_process_data(process_id, serializable)
        return True
    except Exception as e:
        st.error(f"Erro ao salvar estado: {e}")
        return False

def load_process(process_id: str):
    """
    Carrega os dados do processo para st.session_state (faz mapeamentos compatíveis).
    """
    try:
        dados = load_process_data(process_id)
        if not dados:
            st.error("Não foi possível localizar o processo especificado.")
            return False

        # Mapeamentos compatíveis (legacy)
        if "AUTORES" in dados and "AUTOR" not in dados:
            dados["AUTOR"] = dados.pop("AUTORES")
        if "REUS" in dados and "REU" not in dados:
            dados["REU"] = dados.pop("REUS")
        # Atualiza session_state cuidadosamente
        for k, v in dados.items():
            if k == "etapas_concluidas" and isinstance(v, list):
                st.session_state[k] = set(v)
            else:
                st.session_state[k] = v

        st.session_state["selected_process_id"] = process_id
        st.session_state["process_loaded"] = True

        # garante chaves essenciais
        ensure_session_defaults()
        st.success(f"Processo {process_id} carregado.")
        return True
    except FileNotFoundError:
        st.error("Arquivo do processo não encontrado.")
        return False
    except Exception as e:
        st.error(f"Erro ao carregar processo: {e}")
        return False

# ------------------------------
# UTILS / HELPERS
# ------------------------------
def gerar_id(short: bool = True) -> str:
    idv = str(uuid.uuid4())
    return idv[:8] if short else idv

def get_questionado_by_id(qid: str):
    return next((q for q in st.session_state.get("questionados_list", []) if q.get("id") == qid), None)

def gather_all_references(session_state_local: Dict[str, Any]) -> List[str]:
    refs = []
    for idx, q in enumerate(session_state_local.get("questionados_list", [])):
        refs.append(f"Doc Questionado {idx+1}: {q.get('TIPO_DOCUMENTO','S/N')} (Fls. {q.get('FLS_DOCUMENTOS','S/N')})")
    for idx, p in enumerate(session_state_local.get("padroes_list", [])):
        refs.append(f"Padrão {idx+1}: {p.get('TIPO_DOCUMENTO','S/N')}")
    return refs

# ------------------------------
# MESA GRÁFICA (Editor centralizado) — função reutilizável
# ------------------------------
def image_editor_tool(img_bytes: bytes, image_title: str = "Imagem"):
    """
    Mesa Gráfica integrada:
    - crop (st_cropper)
    - anotação com st_canvas (linhas, setas, shapes)
    - retorna bytes PNG do resultado final, ou None se cancelado
    """
    if not EDITOR_AVAILABLE:
        st.warning("Editor gráfico não disponível. Instale: streamlit-cropper streamlit-drawable-canvas Pillow")
        return None

    try:
        st.markdown(f"### ✏️ Mesa Gráfica — {image_title}")
        img = Image.open(BytesIO(img_bytes)).convert("RGBA")

        st.markdown("#### 1) Recorte / Zoom")
        cropped_img = st_cropper(img, realtime_update=True, box_color="#00AAFF", aspect_ratio=None)

        st.markdown("#### 2) Ferramenta de Anotações")
        canvas_result = st_canvas(
            fill_color="rgba(255, 165, 0, 0.25)",
            stroke_width=3,
            stroke_color="#FF0000",
            background_image=cropped_img,
            update_streamlit=True,
            height=600,
            width=800,
            drawing_mode="freedraw"
        )

        if canvas_result.image_data is not None:
            # mostra visualização do trabalho
            st.markdown("#### Visualização — Resultado")
            st.image(canvas_result.image_data, use_column_width=True)

            buf = BytesIO()
            result_img = Image.fromarray(canvas_result.image_data.astype("uint8"))
            result_img.save(buf, format="PNG")
            return buf.getvalue()

        return None
    except Exception as e:
        st.error(f"Erro no editor de imagem: {e}")
        return None

# ------------------------------
# FUNÇÃO DE PLOTAÇÃO DO EOG (RADAR)
# ------------------------------
def plot_eog_radar(eog_data: Dict[str, str]):
    """
    Constrói e desenha radar para os elementos EOG.
    eog_data: dict com chaves do EOG_ELEMENTS e valores (ADEQUADO/LIMITADO/DIVERGENTE/PENDENTE)
    """
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

    fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True))
    ax.clear()
    ax.plot(angles, values, linewidth=2, linestyle='solid')
    ax.fill(angles, values, alpha=0.25)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels[:-1], fontsize=9)

    ax.set_yticks([0, 1, 2])
    ax.set_yticklabels(["Divergente", "Limitado", "Adequado"], color="grey", size=8)
    ax.set_ylim(0, 2)

    ax.set_title("Resumo dos Elementos de Ordem Gráfica (EOG)", size=12, y=1.08)

    st.pyplot(fig)

# ======================================================================
# PARTE 2/4 - Auxiliares de Análise, Formulários e Render de Documentos
# ======================================================================

# ----------------------------------------------------------------------
# Auxiliares: criar/recuperar análises, processar quesitos em adendos
# ----------------------------------------------------------------------
def get_analysis_for_questionado(questionado_id: str) -> Dict[str, Any]:
    """
    Retorna a análise vinculada a um documento questionado.
    Se não existir, cria uma estrutura padrão e registra em saved_analyses.
    """
    saved = st.session_state.get("saved_analyses", {})
    if questionado_id in saved:
        return saved[questionado_id]

    new_analysis = {
        "id": gerar_id(),
        "questionado_id": questionado_id,
        "is_saved": False,
        "conclusao_status": "PENDENTE",
        "eog_elements": {k: "PENDENTE" for k in EOG_ELEMENTS.keys()},
        "confronto_texts": {k: "" for k in CONFRONTO_ELEMENTS.keys()},
        "descricao_analise": "",
        "imagem_analise_bytes": None,
        "tem_imagem_analise": False,
        "justificativa_conclusao": ""
    }
    st.session_state.saved_analyses[questionado_id] = new_analysis
    return new_analysis


def remove_analysis_for_questionado(questionado_id: str):
    saved = st.session_state.get("saved_analyses", {})
    if questionado_id in saved:
        saved.pop(questionado_id)
        st.session_state.saved_analyses = saved
        save_current_state({"saved_analyses": st.session_state.saved_analyses})


def process_quesitos_for_adendos(quesitos_list: List[Dict[str, Any]], party_name: str):
    """
    Transforma imagens em quesitos em adendos e vincula ao session_state.adendos.
    """
    adendos = st.session_state.get("adendos", [])
    for q in list(quesitos_list):
        if q.get("imagem_bytes") and not q.get("adendo_id"):
            ad_id = gerar_id()
            ad = {
                "id_adendo": ad_id,
                "origem": f"quesito_{party_name.lower()}",
                "id_referencia": q.get("id"),
                "descricao": f"Quesito {party_name} #{q.get('id')}",
                "bytes": q.get("imagem_bytes"),
                "filename": f"quesito_{party_name.lower()}_{ad_id}.png"
            }
            adendos.append(ad)
            q["adendo_id"] = ad_id
            q.pop("imagem_bytes", None)
    st.session_state.adendos = adendos
    save_current_state({"adendos": adendos})


# ----------------------------------------------------------------------
# Render de formulários menores (Questionados / Padrões / Anexos)
# ----------------------------------------------------------------------
def render_questionado_form(item: Dict[str, Any], idx: int):
    """
    Renderiza o formulário de um documento questionado (utilizado na Etapa 4).
    """
    item_id = item.get("id")
    with st.expander(f"Documento Questionado {idx+1} — {item.get('TIPO_DOCUMENTO', '')}", expanded=False):
        col1, col2 = st.columns([3,1])
        item["TIPO_DOCUMENTO"] = col1.text_input("Tipo do Documento", value=item.get("TIPO_DOCUMENTO", ""), key=f"q_tipo_{item_id}")
        item["FLS_DOCUMENTOS"] = col2.text_input("Fls.", value=item.get("FLS_DOCUMENTOS", ""), key=f"q_fls_{item_id}")
        item["DESCRICAO_IMAGEM"] = st.text_area("Descrição do Grafismo", value=item.get("DESCRICAO_IMAGEM", ""), key=f"q_desc_{item_id}", height=80)

        col_save, col_del = st.columns([4,1])
        if col_save.button("💾 Salvar Documento", key=f"save_q_{item_id}"):
            # atualiza lista no session_state e salva
            lst = st.session_state.get("questionados_list", [])
            for i, it in enumerate(lst):
                if it.get("id") == item_id:
                    lst[i] = item
                    break
            st.session_state.questionados_list = lst
            save_current_state({"questionados_list": lst})
            st.success("Documento salvo.")
        if col_del.button("🗑️ Excluir Documento", key=f"del_q_{item_id}"):
            st.session_state.questionados_list = [x for x in st.session_state.questionados_list if x.get("id") != item_id]
            # remove análise vinculada
            if item_id in st.session_state.get("saved_analyses", {}):
                st.session_state.saved_analyses.pop(item_id)
            save_current_state({"questionados_list": st.session_state.get("questionados_list", []), "saved_analyses": st.session_state.get("saved_analyses", {})})
            st.success("Documento removido.")
            st.experimental_rerun()


def render_padrao_form(item: Dict[str, Any], idx: int):
    item_id = item.get("id")
    with st.expander(f"Documento Padrão {idx+1} — {item.get('TIPO_DOCUMENTO','')}", expanded=False):
        item["TIPO_DOCUMENTO"] = st.text_input("Tipo do Documento Padrão", value=item.get("TIPO_DOCUMENTO", ""), key=f"pad_tipo_{item_id}")
        item["NUMEROS"] = st.text_input("Fls. / Nº", value=item.get("NUMEROS", ""), key=f"pad_nums_{item_id}")
        if st.button("💾 Salvar Padrão", key=f"save_pad_{item_id}"):
            lst = st.session_state.get("padroes_list", [])
            for i, it in enumerate(lst):
                if it.get("id") == item_id:
                    lst[i] = item
                    break
            st.session_state.padroes_list = lst
            save_current_state({"padroes_list": lst})
            st.success("Padrão salvo.")
        if st.button("🗑️ Excluir Padrão", key=f"del_pad_{item_id}"):
            st.session_state.padroes_list = [x for x in st.session_state.padroes_list if x.get("id") != item_id]
            save_current_state({"padroes_list": st.session_state.get("padroes_list", [])})
            st.experimental_rerun()


def render_anexo_upload_form(q_item: Dict[str, Any]):
    """
    Form para upload/exibição/exclusão de anexo vinculado a um documento questionado.
    Adiciona botão 'Mesa Gráfica' quando houver anexo para edição.
    """
    q_id = q_item.get("id")
    descr = f"ANEXO para {q_item.get('TIPO_DOCUMENTO','Documento')} (Fls. {q_item.get('FLS_DOCUMENTOS','')})"
    anexo = next((a for a in st.session_state.get("anexos", []) if a.get("id_referencia") == q_id), None)

    with st.container():
        st.caption(descr)
        col1, col2 = st.columns([4,1])
        if anexo:
            col1.markdown(f"**Arquivo:** {anexo.get('filename', 'sem_nome')}")
            if col2.button("🗑️ Excluir Anexo", key=f"del_anexo_{q_id}"):
                st.session_state.anexos = [a for a in st.session_state.anexos if a.get("id_referencia") != q_id]
                save_current_state({"anexos": st.session_state.anexos})
                st.success("Anexo removido.")
                st.experimental_rerun()

            # botão Mesa Gráfica
            if col2.button("✏️ Mesa Gráfica", key=f"mesa_anexo_{q_id}"):
                # abrir editor em expander
                with st.expander(f"Mesa Gráfica — {anexo.get('filename')}", expanded=True):
                    edited = image_editor_tool(anexo.get("bytes"), image_title=anexo.get("filename"))
                    if edited:
                        # substitui bytes do anexo e salva
                        anexo["bytes"] = edited
                        save_current_state({"anexos": st.session_state.anexos})
                        st.success("Anexo atualizado a partir da Mesa Gráfica.")
                        st.experimental_rerun()
        else:
            uploaded = col1.file_uploader("Upload do Anexo (pdf/png/jpg)", type=["pdf", "png", "jpg", "jpeg"], key=f"upload_anexo_{q_id}")
            if uploaded is not None:
                file_bytes = uploaded.read()
                new_anexo = {
                    "id": gerar_id(),
                    "origem": "documento_questionado",
                    "id_referencia": q_id,
                    "descricao": descr,
                    "bytes": file_bytes,
                    "filename": uploaded.name,
                    "mime_type": uploaded.type
                }
                lst = st.session_state.get("anexos", [])
                lst.append(new_anexo)
                st.session_state.anexos = lst
                save_current_state({"anexos": lst})
                st.success("Anexo carregado.")
                st.experimental_rerun()


# ----------------------------------------------------------------------
# Sections: Questionados / Padrões (Etapa 4)
# ----------------------------------------------------------------------
def render_questionados_section():
    st.header("4. DOCUMENTOS SUBMETIDOS A EXAME")
    st.subheader("4.1 Documentos Questionados (PQ)")
    q_list = st.session_state.get("questionados_list", [])

    if not q_list:
        st.info("Nenhum documento questionado adicionado.")
    for idx, q in enumerate(list(q_list)):
        render_questionado_form(q, idx)
        # anexo relacionado
        render_anexo_upload_form(q)

    if st.button("➕ Adicionar Documento Questionado", key="add_questionado_btn"):
        new_q = {"id": gerar_id(), "TIPO_DOCUMENTO": "Documento Questionado", "FLS_DOCUMENTOS": "", "DESCRICAO_IMAGEM": ""}
        st.session_state.questionados_list.append(new_q)
        save_current_state({"questionados_list": st.session_state.questionados_list})
        st.experimental_rerun()


def render_padroes_section():
    st.subheader("4.2 Documentos Padrão (PCE/PCA)")
    padroes = st.session_state.get("padroes_list", [])
    if not padroes:
        st.info("Nenhum documento padrão adicionado.")
    for idx, p in enumerate(list(padroes)):
        render_padrao_form(p, idx)

    if st.button("➕ Adicionar Documento Padrão", key="add_padrao_btn"):
        new_p = {"id": gerar_id(), "TIPO_DOCUMENTO": "Documento Padrão", "NUMEROS": ""}
        st.session_state.padroes_list.append(new_p)
        save_current_state({"padroes_list": st.session_state.padroes_list})
        st.experimental_rerun()


# ----------------------------------------------------------------------
# Módulo de Análise (Etapa 5) - interface que usa plot_eog_radar e Mesa Gráfica
# ----------------------------------------------------------------------
def render_module_analise():
    st.header("5. EXAMES PERICIAIS E METODOLOGIA — Análises Gráficas")
    if not st.session_state.get("questionados_list"):
        st.warning("Cadastre documentos questionados primeiro (Etapa 4).")
        return

    options = {q["id"]: f"{q.get('TIPO_DOCUMENTO','Doc')} — {q.get('FLS_DOCUMENTOS','')}" for q in st.session_state.get("questionados_list", [])}
    selected = st.selectbox("Selecione documento para análise", options=list(options.keys()), format_func=lambda k: options[k], key="analise_select")

    if not selected:
        return

    analysis = get_analysis_for_questionado(selected)

    st.subheader("5.1 Elementos de Ordem Geral (EOG)")
    col1, col2 = st.columns(2)
    key_prefix = selected

    # selects que atualizam session_state (ao vivo)
    val_hab = col1.selectbox("Habilidade / Velocidade", EOG_OPCOES, index=EOG_OPCOES.index(analysis["eog_elements"].get("HABILIDADE_VELOCIDADE", "PENDENTE")), key=f"eog_hab_{key_prefix}")
    val_cal = col1.selectbox("Calibre", EOG_OPCOES, index=EOG_OPCOES.index(analysis["eog_elements"].get("CALIBRE", "PENDENTE")), key=f"eog_cal_{key_prefix}")
    val_esp = col2.selectbox("Espontaneidade / Dinamismo", EOG_OPCOES, index=EOG_OPCOES.index(analysis["eog_elements"].get("ESPONTANEIDADE_DINAMISMO", "PENDENTE")), key=f"eog_esp_{key_prefix}")
    val_alin = col2.selectbox("Alinhamento Gráfico", EOG_OPCOES, index=EOG_OPCOES.index(analysis["eog_elements"].get("ALINHAMENTO_GRAFICO", "PENDENTE")), key=f"eog_alin_{key_prefix}")
    val_ataq = col1.selectbox("Ataques / Remates", EOG_OPCOES, index=EOG_OPCOES.index(analysis["eog_elements"].get("ATAQUES_REMATES", "PENDENTE")), key=f"eog_ataq_{key_prefix}")

    live = {
        "HABILIDADE_VELOCIDADE": st.session_state.get(f"eog_hab_{key_prefix}", analysis["eog_elements"].get("HABILIDADE_VELOCIDADE", "PENDENTE")),
        "CALIBRE": st.session_state.get(f"eog_cal_{key_prefix}", analysis["eog_elements"].get("CALIBRE", "PENDENTE")),
        "ESPONTANEIDADE_DINAMISMO": st.session_state.get(f"eog_esp_{key_prefix}", analysis["eog_elements"].get("ESPONTANEIDADE_DINAMISMO", "PENDENTE")),
        "ALINHAMENTO_GRAFICO": st.session_state.get(f"eog_alin_{key_prefix}", analysis["eog_elements"].get("ALINHAMENTO_GRAFICO", "PENDENTE")),
        "ATAQUES_REMATES": st.session_state.get(f"eog_ataq_{key_prefix}", analysis["eog_elements"].get("ATAQUES_REMATES", "PENDENTE")),
    }

    st.markdown("**Visualização do Radar (ao vivo)**")
    plot_eog_radar(live)

    st.markdown("---")
    st.subheader("5.2 Confronto Grafoscópico")
    for ck, desc in CONFRONTO_ELEMENTS.items():
        analysis["confronto_texts"][ck] = st.text_area(desc, value=analysis["confronto_texts"].get(ck, ""), key=f"conf_{ck}_{selected}", height=100)

    st.markdown("---")
    st.subheader("5.3 Descrição e Adendo de Imagem")
    analysis["descricao_analise"] = st.text_area("Descrição Livre", value=analysis.get("descricao_analise", ""), key=f"desc_analise_{selected}", height=150)

    # Upload + Mesa Gráfica
    up_col, info_col = st.columns([1,3])
    uploaded = up_col.file_uploader("Upload para Análise (PNG/JPG)", type=["png", "jpg", "jpeg"], key=f"up_img_analise_{selected}")
    if uploaded:
        img_bytes = uploaded.read()
        if st.button("✏️ Abrir Editor (Mesa Gráfica)", key=f"open_editor_{selected}"):
            edited = image_editor_tool(img_bytes, image_title=f"Análise_{selected}")
            if edited:
                analysis["imagem_analise_bytes"] = edited
                analysis["tem_imagem_analise"] = True
                st.success("Imagem editada e registrada como adendo para a análise.")

    elif analysis.get("tem_imagem_analise"):
        info_col.info("Existe adendo de imagem salvo para esta análise.")

    st.markdown("---")
    if st.button("💾 Salvar Análise (5.1 - 5.3)", key=f"save_analysis_{selected}"):
        analysis["eog_elements"] = {k: live[k] for k in live.keys()}
        analysis["is_saved"] = True
        st.session_state.saved_analyses[selected] = analysis
        save_current_state({"saved_analyses": st.session_state.saved_analyses})
        st.success("Análise salva com sucesso.")
        st.experimental_rerun()

# ======================================================================
# PARTE 3/4 - ETAPAS 6 E 7 + CONTROLE DE FLUXO DO LAUDO
# ======================================================================

# ----------------------------------------------------------------------
# ETAPA 6 — CONCLUSÃO DO PERITO
# ----------------------------------------------------------------------
def render_etapa_6():
    st.header("6. CONCLUSÃO DO PERITO")

    st.write("""
    Nesta etapa você deve registrar sua conclusão global do laudo.  
    O item será automaticamente incorporado ao arquivo DOCX final.
    """)

    st.session_state.conclusao_final = st.text_area(
        "Conclusão Final",
        value=st.session_state.get("conclusao_final", ""),
        height=220,
        key="txt_conclusao_final"
    )

    if st.button("💾 Salvar Conclusão (Etapa 6)", key="save_etp6"):
        save_current_state({"conclusao_final": st.session_state.conclusao_final})
        st.success("Conclusão salva!")
        marcar_etapa_concluida(6)


# ----------------------------------------------------------------------
# ETAPA 7 — QUESITOS E RESPOSTAS
# ----------------------------------------------------------------------

def render_quesitos_party(party_name: str, state_key: str):
    """Renderiza o formulário de quesitos da Parte Autora ou Ré."""
    st.subheader(f"7.1 Quesitos da Parte {party_name}")

    lista = st.session_state.get(state_key, [])
    if not lista:
        st.info(f"A parte {party_name} não enviou quesitos.")
        return

    for idx, q in enumerate(lista):
        with st.expander(f"Quesito {idx+1}", expanded=False):
            q["texto"] = st.text_area(
                "Texto do Quesito",
                value=q.get("texto", ""),
                key=f"{state_key}_texto_{idx}",
                height=100
            )
            q["resposta"] = st.text_area(
                "Resposta do Perito",
                value=q.get("resposta", ""),
                key=f"{state_key}_resp_{idx}",
                height=120
            )

    if st.button(f"💾 Salvar Quesitos da Parte {party_name}", key=f"save_{state_key}"):
        st.session_state[state_key] = lista
        save_current_state({state_key: lista})
        st.success(f"Quesitos da Parte {party_name} salvos com sucesso.")


def render_etapa_7():
    st.header("7. QUESITOS DAS PARTES")

    col1, col2 = st.columns(2)
    with col1:
        render_quesitos_party("Autora", "LISTA_QS_AUTOR")
    with col2:
        render_quesitos_party("Ré", "LISTA_QS_REU")

    if st.button("💾 Concluir Etapa 7", key="save_etp7"):
        marcar_etapa_concluida(7)
        st.success("Etapa 7 concluída!")


# ----------------------------------------------------------------------
# CONTROLE DE ETAPAS (check verde / lápis / cadeado)
# ----------------------------------------------------------------------
ETAPAS = {
    1: "Identificação do Processo",
    2: "Nomeação e Encargos",
    3: "Recebimento dos Autos",
    4: "Documentos Submetidos a Análise",
    5: "Exames e Metodologia",
    6: "Conclusão",
    7: "Quesitos"
}

def marcar_etapa_concluida(num):
    concluidas = st.session_state.get("etapas_concluidas", set())
    concluidas.add(num)
    st.session_state.etapas_concluidas = concluidas
    save_current_state({"etapas_concluidas": list(concluidas)})


def render_sidebar_etapas():
    """
    Renderiza o menu lateral com:
    ✔️ etapa concluída  
    ✏️ etapa atual  
    🔒 etapas não concluídas
    """
    st.sidebar.markdown("## 📌 Progresso do Laudo")

    etapa_atual = st.session_state.get("etapa_atual", 1)
    concluidas = st.session_state.get("etapas_concluidas", set())

    for num, nome in ETAPAS.items():
        if num in concluidas:
            icon = "✔️"
        elif num == etapa_atual:
            icon = "✏️"
        else:
            icon = "🔒"

        st.sidebar.markdown(f"{icon} **{num}. {nome}**")

    st.sidebar.markdown("---")
    st.sidebar.write("Use o menu abaixo para retornar a etapas já concluídas:")

    etapas_liberadas = sorted(list(concluidas))
    if etapas_liberadas:
        escolha = st.sidebar.selectbox(
            "Voltar para etapa:",
            opções := etapas_liberadas,
            index=etapas_liberadas.index(etapa_atual) if etapa_atual in etapas_liberadas else 0,
            key="sb_etapa_retorno"
        )
        if escolha != etapa_atual:
            st.session_state.etapa_atual = escolha
            st.experimental_rerun()


# ----------------------------------------------------------------------
# FLUXO PRINCIPAL DAS ETAPAS
# ----------------------------------------------------------------------
def render_etapas_do_laudo():
    """Controla a exibição da etapa atual."""

    etapa = st.session_state.get("etapa_atual", 1)

    if etapa == 1:
        render_etapa_1()
    elif etapa == 2:
        render_etapa_2()
    elif etapa == 3:
        render_etapa_3()
    elif etapa == 4:
        render_questionados_section()
        render_padroes_section()
    elif etapa == 5:
        render_module_analise()
    elif etapa == 6:
        render_etapa_6()
    elif etapa == 7:
        render_etapa_7()

    st.markdown("---")

    # botão para próxima etapa (se possível)
    if etapa < 7:
        if st.button("➡️ Avançar para próxima etapa", key=f"continue_{etapa}"):
            st.session_state.etapa_atual = etapa + 1
            salvar = {"etapa_atual": etapa + 1}
            save_current_state(salvar)
            st.experimental_rerun()

# ======================================================================
# PARTE 4/4 - Etapas iniciais, UI principal, geração DOCX e finalização
# ======================================================================

# ---------------------------------------------------------------------
# Etapas 1, 2 e 3 (simples, seguras — podem ser expandidas depois)
# ---------------------------------------------------------------------
def render_etapa_1():
    st.header("1. APRESENTAÇÃO / IDENTIFICAÇÃO")
    st.write("Preencha os dados iniciais do processo.")
    st.session_state.AUTOR = st.text_input("Nome do Autor", value=st.session_state.get("AUTOR", ""), key="ui_autor")
    st.session_state.REU = st.text_input("Nome do Réu", value=st.session_state.get("REU", ""), key="ui_reu")
    st.session_state.DATA_LAUDO = st.date_input("Data do Laudo", value=st.session_state.get("DATA_LAUDO", date.today()), key="ui_data")
    if st.button("💾 Salvar Etapa 1", key="save_1"):
        save_current_state()
        marcar_etapa_concluida(1)
        st.success("Etapa 1 salva.")

def render_etapa_2():
    st.header("2. NOMEAÇÃO E DOCUMENTOS INICIAIS")
    st.write("Campos auxiliares (preencha se aplicável).")
    st.session_state.ID_NOMEACAO = st.text_input("ID Nomeação (Fls.)", value=st.session_state.get("ID_NOMEACAO", ""), key="ui_id_nomeacao")
    if st.button("💾 Salvar Etapa 2", key="save_2"):
        save_current_state()
        marcar_etapa_concluida(2)
        st.success("Etapa 2 salva.")

def render_etapa_3():
    st.header("3. RECEBIMENTO DOS AUTOS / INTRODUÇÃO")
    st.session_state.ID_PADROES = st.text_input("ID Padrões (Fls.)", value=st.session_state.get("ID_PADROES", ""), key="ui_id_padroes")
    st.session_state.ID_AUTORIDADE_COLETORA = st.text_input("Autoridade Coletora", value=st.session_state.get("ID_AUTORIDADE_COLETORA", ""), key="ui_aut_coletora")
    if st.button("💾 Salvar Etapa 3", key="save_3"):
        save_current_state()
        marcar_etapa_concluida(3)
        st.success("Etapa 3 salva.")

# ---------------------------------------------------------------------
# Função para criar novo processo (wrapper com verificação)
# ---------------------------------------------------------------------
def create_and_load_new_process(numero_processo: str, autor: str, reu: str):
    if not numero_processo:
        st.error("Informe um número de processo válido.")
        return False
    initial_payload = {
        "numero_processo": numero_processo,
        "AUTOR": autor or "",
        "REU": reu or "",
        "DATA_LAUDO": date.today().isoformat(),
        "questionados_list": [],
        "padroes_list": [],
        "saved_analyses": {},
        "anexos": [],
        "adendos": [],
        "etapas_concluidas": []
    }
    try:
        save_process_data(numero_processo, initial_payload)
    except Exception as e:
        st.error(f"Erro ao criar processo: {e}")
        return False
    # Carrega imediatamente
    ok = load_process(numero_processo)
    if ok:
        st.success(f"Processo {numero_processo} criado e carregado.")
    return ok

# ---------------------------------------------------------------------
# Geração do DOCX final (wrapper seguro)
# ---------------------------------------------------------------------
def gerar_laudo_docx():
    st.info("Preparando dados para geração do laudo...")
    try:
        dados_para_word = {
            "numero_processo": st.session_state.get("selected_process_id"),
            "AUTOR": st.session_state.get("AUTOR"),
            "REU": st.session_state.get("REU"),
            "DATA_LAUDO": st.session_state.get("DATA_LAUDO"),
            "questionados": st.session_state.get("questionados_list", []),
            "padroes": st.session_state.get("padroes_list", []),
            "analises": st.session_state.get("saved_analyses", {}),
            "BLOCO_CONCLUSAO_DINAMICO": st.session_state.get("BLOCO_CONCLUSAO_DINAMICO", ""),
            "BLOCO_QUESITOS_AUTOR": st.session_state.get("BLOCO_QUESITOS_AUTOR", ""),
            "BLOCO_QUESITOS_REU": st.session_state.get("BLOCO_QUESITOS_REU", ""),
            "adendos": st.session_state.get("adendos", []),
            "anexos": st.session_state.get("anexos", [])
        }

        # Se generate_report_from_template existir, usa; senão gera JSON de debug
        try:
            out_path = generate_report_from_template(dados_para_word)
            st.success(f"Laudo gerado: {out_path}")
            with open(out_path, "rb") as f:
                st.download_button("⬇️ Baixar Laudo .DOCX", data=f, file_name=os.path.basename(out_path))
        except FileNotFoundError:
            # fallback: grava um JSON com os dados do laudo na pasta output para verificação
            fallback_path = os.path.join(OUTPUT_FOLDER, f"{st.session_state.get('selected_process_id')}_LAUDO_DEBUG.json")
            with open(fallback_path, "w", encoding="utf-8") as fp:
                json.dump(dados_para_word, fp, ensure_ascii=False, indent=2)
            st.warning("generate_report_from_template não disponível. Gere um arquivo JSON de verificação.")
            with open(fallback_path, "rb") as f:
                st.download_button("⬇️ Baixar JSON de Debug do Laudo", data=f, file_name=os.path.basename(fallback_path))
        # marca concluído
        st.session_state.etapas_concluidas.add(ETAPA_ID_8)
        save_current_state({"etapas_concluidas": list(st.session_state.etapas_concluidas)})
    except Exception as e:
        st.error(f"Erro ao gerar o laudo: {e}")

# ---------------------------------------------------------------------
# Sidebar: lista de processos, criação rápida, salvar manual e tema toggle
# ---------------------------------------------------------------------
def render_sidebar_controls():
    st.sidebar.title("Controle do Projeto")
    st.sidebar.markdown("---")

    # Lista processos
    try:
        procs = list_processes()
    except Exception:
        # fallback: lista arquivos na pasta DATA_FOLDER
        try:
            procs = [f.replace(".json","") for f in os.listdir(DATA_FOLDER) if f.endswith(".json")]
        except Exception:
            procs = []

    if procs:
        sel = st.sidebar.selectbox("Processos existentes", options=procs, key="sidebar_sel_proc")
        if st.sidebar.button("📂 Carregar processo selecionado"):
            load_process(sel)
            st.experimental_rerun()
    else:
        st.sidebar.info("Nenhum processo encontrado.")

    st.sidebar.markdown("---")
    st.sidebar.subheader("Criar novo processo (rápido)")
    new_num = st.sidebar.text_input("Número do Processo", key="sidebar_new_num")
    new_aut = st.sidebar.text_input("Autor", key="sidebar_new_aut")
    new_reu = st.sidebar.text_input("Réu", key="sidebar_new_reu")
    if st.sidebar.button("➕ Criar e Carregar"):
        if create_and_load_new_process(new_num, new_aut, new_reu):
            st.experimental_rerun()

    st.sidebar.markdown("---")
    if st.sidebar.button("💾 Salvar estado atual (Manual)"):
        if save_current_state():
            st.sidebar.success("Estado salvo.")
    st.sidebar.markdown("---")
    # Theme hint (Streamlit theme control is via UI; offer guidance)
    st.sidebar.caption("Para alternar tema (claro/escuro), use o menu de tema no canto superior direito do app.")

# ---------------------------------------------------------------------
# Função principal que monta a UI (chamada no bloco final)
# ---------------------------------------------------------------------
def main_app_ui():
    st.title("Geração de Laudo Pericial — Painel de Trabalho")
    render_sidebar_etapas()  # de Parte 3 (menu de etapas)
    render_sidebar_controls()

    # Cabeçalho do processo carregado
    if st.session_state.get("process_loaded", False):
        st.markdown(f"### Processo: **{st.session_state.get('selected_process_id')}**")
        st.markdown(f"**Autor:** {st.session_state.get('AUTOR', 'N/A')}  |  **Réu:** {st.session_state.get('REU', 'N/A')}")
        st.markdown("---")

        # Renderiza etapa atual
        render_etapas_do_laudo()

        st.markdown("---")
        # Área de geração / encerramento
        st.header("Encerramento e Geração do Laudo")
        st.write("Revise anexos e adendos antes de gerar o documento final.")
        st.write(f"Adendos gerados: {len(st.session_state.get('adendos', []))}   |   Anexos: {len(st.session_state.get('anexos', []))}")

        if st.button("🚀 Gerar Laudo (.docx / fallback JSON)"):
            gerar_laudo_docx()

    else:
        st.info("Carregue ou crie um processo para iniciar o preenchimento.")
        st.markdown("Use o painel lateral para criar um processo rápido ou carregar um existente.")

# ---------------------------------------------------------------------
# Executa a UI
# ---------------------------------------------------------------------
if __name__ == "__main__":
    main_app_ui()
else:
    # Em Streamlit, __name__ != "__main__" — chamamos a UI de qualquer forma
    main_app_ui()

# ---------------------------------------------------------------------
# Observações finais e instruções mínimas após a colagem das 4 partes
# ---------------------------------------------------------------------
st.markdown("---")
st.markdown("### Instruções rápidas após colar as 4 partes")
st.markdown("""
1. Faça backup do arquivo antigo (ex: renomeie `01_Gerar_laudo.py` para `01_Gerar_laudo_old.py`).  
2. Cole as 4 partes (esta é a Parte 4) na ordem: Parte1 → Parte2 → Parte3 → Parte4.  
3. Salve o arquivo e no GitHub Desktop: Commit (mensagem: `Atualiza 01_Gerar_laudo.py — EOG + Mesa + Fixes`) e Push.  
4. Reinicie a aplicação Streamlit (ou aguarde o deploy).  
5. Se receber erros, copie o traceback inteiro e cole aqui — eu corrijo rapidamente.  
6. Dependências opcionais (para Mesa Gráfica):  
   `pip install streamlit-cropper streamlit-drawable-canvas Pillow`  
""")



