# ======================================================================
# 01_Gerar_laudo.py
# Sistema de Geração de Laudo Pericial Grafotécnico
# Versão revisada por ChatGPT – com melhorias de EOG e Editor de Imagem
# ======================================================================

import streamlit as st
import uuid
import json
import os
import datetime
import matplotlib.pyplot as plt
from io import BytesIO
from PIL import Image
from streamlit_drawable_canvas import st_canvas
from streamlit_cropper import st_cropper

from src.data_handler import (
    save_process_data,
    load_process_data,
    list_processes,
    PROCESS_DATA_DIR
)

from src.word_handler import generate_report_from_template

# ======================================================================
# CONFIGURAÇÕES GERAIS
# ======================================================================

st.set_page_config(
    page_title="Gerar Laudo Pericial grafotécnico",
    layout="wide",
    page_icon="✒️"
)

# ======================================================================
# CONSTANTES E DEFINIÇÕES DE EOG
# ======================================================================

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

# ======================================================================
# FUNÇÕES AUXILIARES DO SISTEMA
# ======================================================================

def safe_get(key, default=None):
    """
    Garante leitura segura do session_state.
    """
    if key in st.session_state:
        return st.session_state[key]
    return default


def ensure_session_defaults():
    """
    Inicializa no session_state todas as chaves obrigatórias.
    """
    defaults = {
        "process_loaded": False,
        "selected_process_id": None,
        "etapas_concluidas": set(),
        "LISTA_QS_AUTOR": [],
        "LISTA_QS_REU": [],
        "AUTOR": "",
        "REU": "",
        "DATA_LAUDO": datetime.date.today(),
        "saved_analyses": {},
        "active_questionado_id": None
    }

    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def save_current_state(updated_data: dict):
    """
    Salva o estado do processo no arquivo JSON, convertendo tipos não serializáveis.
    """
    serializable_data = {}

    for key, value in updated_data.items():

        if isinstance(value, set):
            serializable_data[key] = list(value)

        elif isinstance(value, datetime.date):
            serializable_data[key] = value.isoformat()

        elif isinstance(value, dict):
            inner = {}
            for ik, iv in value.items():
                if isinstance(iv, (datetime.date, datetime.datetime)):
                    inner[ik] = iv.isoformat()
                elif isinstance(iv, set):
                    inner[ik] = list(iv)
                else:
                    inner[ik] = iv
            serializable_data[key] = inner

        else:
            serializable_data[key] = value

    save_process_data(st.session_state.selected_process_id, serializable_data)


def load_process(process_id):
    """
    Carrega um processo existente e restaura no session_state.
    """
    dados = load_process_data(process_id)

    if not dados:
        st.error("Não foi possível carregar o processo.")
        return

    st.session_state.process_loaded = True
    st.session_state.selected_process_id = process_id
    st.session_state.etapas_concluidas = set(dados.get("etapas_concluidas", []))

    st.session_state.AUTOR = dados.get("AUTOR", "N/A")
    st.session_state.REU = dados.get("REU", "N/A")

    if "DATA_LAUDO" in dados:
        try:
            st.session_state.DATA_LAUDO = datetime.date.fromisoformat(dados["DATA_LAUDO"])
        except:
            st.session_state.DATA_LAUDO = datetime.date.today()

    st.session_state.LISTA_QS_AUTOR = dados.get("LISTA_QS_AUTOR", [])
    st.session_state.LISTA_QS_REU = dados.get("LISTA_QS_REU", [])
    st.session_state.saved_analyses = dados.get("saved_analyses", {})

# ======================================================================
# FUNÇÕES DE INTERFACE GERAL
# ======================================================================

def gerar_id():
    return str(uuid.uuid4())[:8]


def format_process_label(process_id):
    dados = load_process_data(process_id)
    if not dados:
        return f"{process_id} — [ERRO AO CARREGAR]"
    autor = dados.get("AUTOR", "N/A")
    reu = dados.get("REU", "N/A")
    return f"{process_id} — Autor: {autor} | Réu: {reu}"


# ======================================================================
# EDITOR DE IMAGEM – NOVA FERRAMENTA AVANÇADA
# ======================================================================

def image_editor_tool(img_bytes: bytes):
    """
    Interface de edição de imagem:
    - Crop
    - Zoom
    - Anotações (linhas, setas, formas, cores)
    - Exporta PNG final
    """
    st.write("### ✏️ Editor de Imagem Avançado")

    img = Image.open(BytesIO(img_bytes))

    st.write("#### 1) Recorte (Crop)")
    cropped_img = st_cropper(
        img,
        realtime_update=True,
        box_color="#FF0000",
        aspect_ratio=None
    )

    st.write("#### 2) Área de Anotação")

    canvas_res = st_canvas(
        fill_color="rgba(255, 0, 0, 0.2)",
        stroke_width=2,
        stroke_color="#0000FF",
        background_image=cropped_img,
        update_streamlit=True,
        height=400,
        width=600,
        drawing_mode="freedraw",
        key=f"canvas_{uuid.uuid4()}"
    )

    if canvas_res.image_data is not None:
        edited_img = canvas_res.image_data
        st.write("#### 3) Resultado Final")
        st.image(edited_img)

        buffer = BytesIO()
        result_img = Image.fromarray(edited_img.astype("uint8"))
        result_img.save(buffer, format="PNG")

        return buffer.getvalue()

    return None


# ======================================================================
# NOVA FUNÇÃO DE RADAR (plot_eog_radar)
# ======================================================================

def plot_eog_radar(eog_data: dict):
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

    ax.plot(angles, values, linewidth=2)
    ax.fill(angles, values, alpha=0.25)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, fontsize=9)

    ax.set_yticks([0, 1, 2])
    ax.set_yticklabels(["Divergente", "Limitado", "Adequado"])
    ax.set_ylim(0, 2)

    ax.set_title("Resumo dos Elementos de Ordem Geral (EOG)", y=1.1)

    st.pyplot(fig)

# --------------------------
# PARTE 2 (continuação)
# --------------------------

# ---------------------------------------------------------------------
# Auxiliares de Análise e armazenamento local (estrutura similar ao original)
# ---------------------------------------------------------------------

def get_analysis_for_questionado(questionado_id: str):
    """
    Retorna uma estrutura de análise existente para um documento questionado
    ou cria uma nova se não houver.
    """
    saved = st.session_state.get("saved_analyses", {})
    if questionado_id in saved:
        return saved[questionado_id]

    # Cria nova estrutura
    new_analysis = {
        "id": gerar_id(),
        "questionado_id": questionado_id,
        "is_saved": False,
        "conclusao_status": "PENDENTE",
        "eog_elements": {k: "PENDENTE" for k in EOG_ELEMENTS.keys()},
        "confronto_texts": {k: "" for k in CONFRONTO_ELEMENTS.keys()},
        "descricao_analise": "",
        "imagem_analise_bytes": None,
        "tem_imagem_analise": False
    }
    st.session_state.saved_analyses[questionado_id] = new_analysis
    return new_analysis


def remove_analysis_for_questionado(questionado_id: str):
    if questionado_id in st.session_state.saved_analyses:
        st.session_state.saved_analyses.pop(questionado_id)
        save_current_state({
            "saved_analyses": st.session_state.saved_analyses
        })


# ---------------------------------------------------------------------
# Processamento de Quesitos -> geração de adendos (imagens)
# ---------------------------------------------------------------------

def process_quesitos_to_adendos():
    """
    Percorre as listas de quesitos (autor / réu) e converte quaisquer imagens
    em adendos ligados ao processo.
    """
    adendos = st.session_state.get("adendos", [])
    # Autor
    for q in st.session_state.get("LISTA_QS_AUTOR", []):
        if q.get("imagem_bytes") and not q.get("adendo_id"):
            ad_id = gerar_id()
            adendos.append({
                "id_adendo": ad_id,
                "origem": "quesito_autor",
                "id_referencia": q["id"],
                "descricao": f"Quesito Autor #{q.get('id')}",
                "bytes": q["imagem_bytes"],
                "filename": f"quesito_autor_{ad_id}.png"
            })
            q["adendo_id"] = ad_id
            q.pop("imagem_bytes", None)
    # Réu
    for q in st.session_state.get("LISTA_QS_REU", []):
        if q.get("imagem_bytes") and not q.get("adendo_id"):
            ad_id = gerar_id()
            adendos.append({
                "id_adendo": ad_id,
                "origem": "quesito_reu",
                "id_referencia": q["id"],
                "descricao": f"Quesito Réu #{q.get('id')}",
                "bytes": q["imagem_bytes"],
                "filename": f"quesito_reu_{ad_id}.png"
            })
            q["adendo_id"] = ad_id
            q.pop("imagem_bytes", None)

    st.session_state.adendos = adendos
    save_current_state({"adendos": adendos})


# ---------------------------------------------------------------------
# Funções para renderizar formulários menores
# ---------------------------------------------------------------------

def render_questionados_section():
    st.subheader("Documentos Questionados (PQ)")
    questionados = st.session_state.get("questionados_list", [])
    if not questionados:
        st.info("Nenhum documento questionado cadastrado.")
    for idx, q in enumerate(questionados):
        with st.expander(f"Documento {idx+1} — {q.get('TIPO_DOCUMENTO', 'Questionado')}"):
            col1, col2 = st.columns([3,1])
            q["TIPO_DOCUMENTO"] = col1.text_input("Tipo", value=q.get("TIPO_DOCUMENTO", f"Doc. Questionado {idx+1}"), key=f"q_tipo_{q['id']}")
            q["FLS_DOCUMENTOS"] = col2.text_input("Fls.", value=q.get("FLS_DOCUMENTOS", ""), key=f"q_fls_{q['id']}")
            q["DESCRICAO_IMAGEM"] = st.text_area("Descrição do Grafismo", value=q.get("DESCRICAO_IMAGEM", ""), key=f"q_desc_{q['id']}", height=80)
            col_save, col_del = st.columns([4,1])
            if col_save.button("💾 Salvar Documento", key=f"save_q_{q['id']}"):
                save_current_state({"questionados_list": st.session_state.get("questionados_list", [])})
                st.success("Documento salvo.")
            if col_del.button("🗑️ Excluir Documento", key=f"del_q_{q['id']}"):
                st.session_state.questionados_list = [item for item in st.session_state.questionados_list if item["id"] != q["id"]]
                # Também remove análises vinculadas
                if q["id"] in st.session_state.saved_analyses:
                    st.session_state.saved_analyses.pop(q["id"])
                save_current_state({
                    "questionados_list": st.session_state.get("questionados_list", []),
                    "saved_analyses": st.session_state.get("saved_analyses", {})
                })
                st.experimental_rerun()

    col_add = st.button("➕ Adicionar Documento Questionado")
    if col_add:
        new_q = {
            "id": gerar_id(),
            "TIPO_DOCUMENTO": "Doc. Questionado",
            "FLS_DOCUMENTOS": "",
            "DESCRICAO_IMAGEM": ""
        }
        lst = st.session_state.get("questionados_list", [])
        lst.append(new_q)
        st.session_state.questionados_list = lst
        save_current_state({"questionados_list": lst})
        st.experimental_rerun()


def render_padroes_section():
    st.subheader("Documentos Padrão (PCE / PCA)")
    padroes = st.session_state.get("padroes_list", [])
    if not padroes:
        st.info("Nenhum documento padrão cadastrado.")
    for idx, p in enumerate(padroes):
        with st.expander(f"Padrão {idx+1}"):
            p["TIPO_DOCUMENTO"] = st.text_input("Tipo do Documento", value=p.get("TIPO_DOCUMENTO", ""), key=f"pad_tipo_{p['id']}")
            p["NUMEROS"] = st.text_input("Fls. / Nº", value=p.get("NUMEROS", ""), key=f"pad_nums_{p['id']}")
            if st.button("💾 Salvar Padrão", key=f"save_pad_{p['id']}"):
                save_current_state({"padroes_list": st.session_state.get("padroes_list", [])})
                st.success("Padrão salvo.")
            if st.button("🗑️ Excluir Padrão", key=f"del_pad_{p['id']}"):
                st.session_state.padroes_list = [item for item in st.session_state.padroes_list if item["id"] != p["id"]]
                save_current_state({"padroes_list": st.session_state.get("padroes_list", [])})
                st.experimental_rerun()

    if st.button("➕ Adicionar Documento Padrão"):
        lst = st.session_state.get("padroes_list", [])
        lst.append({
            "id": gerar_id(),
            "TIPO_DOCUMENTO": "Documento Padrão",
            "NUMEROS": ""
        })
        st.session_state.padroes_list = lst
        save_current_state({"padroes_list": lst})
        st.experimental_rerun()


# ---------------------------------------------------------------------
# RENDER: Módulo de Análise (Etapa 5) — parte complementar que permite edição viva
# ---------------------------------------------------------------------

def render_module_analise():
    st.header("5. EXAMES PERICIAIS E METODOLOGIA (Análises Gráficas)")
    if not st.session_state.get("questionados_list"):
        st.warning("Cadastre primeiro documentos questionados na Etapa 4.")
        return

    options = {q["id"]: f"{q.get('TIPO_DOCUMENTO', 'Doc')} — {q.get('FLS_DOCUMENTOS','')}" for q in st.session_state.questionados_list}
    selected = st.selectbox("Selecione Documento Questionado", options=list(options.keys()), format_func=lambda k: options[k], key="select_analise_q")

    if not selected:
        return

    analysis = get_analysis_for_questionado(selected)

    st.subheader("5.1 Elementos de Ordem Geral (EOG)")
    col1, col2 = st.columns(2)
    # cria selects que atualizam st.session_state imediatamente (chaves únicas por doc)
    key_prefix = selected

    val1 = col1.selectbox("Habilidade / Velocidade", EOG_OPCOES, index=EOG_OPCOES.index(analysis["eog_elements"].get("HABILIDADE_VELOCIDADE", "PENDENTE")), key=f"eog_hab_{key_prefix}")
    val2 = col1.selectbox("Calibre", EOG_OPCOES, index=EOG_OPCOES.index(analysis["eog_elements"].get("CALIBRE", "PENDENTE")), key=f"eog_cal_{key_prefix}")
    val3 = col2.selectbox("Espontaneidade / Dinamismo", EOG_OPCOES, index=EOG_OPCOES.index(analysis["eog_elements"].get("ESPONTANEIDADE_DINAMISMO", "PENDENTE")), key=f"eog_esp_{key_prefix}")
    val4 = col2.selectbox("Alinhamento Gráfico", EOG_OPCOES, index=EOG_OPCOES.index(analysis["eog_elements"].get("ALINHAMENTO_GRAFICO", "PENDENTE")), key=f"eog_alin_{key_prefix}")
    val5 = col1.selectbox("Ataques / Remates", EOG_OPCOES, index=EOG_OPCOES.index(analysis["eog_elements"].get("ATAQUES_REMATES", "PENDENTE")), key=f"eog_ataq_{key_prefix}")

    # Monta dicionário ao vivo a partir do session_state (isso garante que o gráfico responda sem precisar submeter o form)
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

    # upload / edição de imagem
    up_col, info_col = st.columns([1,3])
    uploaded = up_col.file_uploader("Upload para Análise (PNG/JPG)", type=["png", "jpg", "jpeg"], key=f"up_img_analise_{selected}")
    if uploaded:
        img_bytes = uploaded.read()
        if st.button("✏️ Abrir Editor", key=f"open_editor_{selected}"):
            edited = image_editor_tool(img_bytes)
            if edited:
                analysis["imagem_analise_bytes"] = edited
                analysis["tem_imagem_analise"] = True
                st.success("Imagem editada e salva como adendo (não esqueça de salvar a Análise).")
    elif analysis.get("tem_imagem_analise"):
        info_col.info("Já existe imagem de adendo salva para esta análise.")

    st.markdown("---")
    if st.button("💾 Salvar Análise (5.1 - 5.3)", key=f"save_analysis_{selected}"):
        # atualiza analysis com os valores ao vivo
        analysis["eog_elements"] = {k: live[k] for k in live.keys()}
        analysis["is_saved"] = True
        # salva na session e em disco
        st.session_state.saved_analyses[selected] = analysis
        save_current_state({
            "saved_analyses": st.session_state.saved_analyses
        })
        st.success("Análise salva com sucesso.")
        st.experimental_rerun()

# --------------------------
# PARTE 3 (continuação)
# --------------------------

# ---------------------------------------------------------------------
# Definições de Confronto (caso não tenham sido definidas nas partes anteriores)
# ---------------------------------------------------------------------
if 'CONFRONTO_ELEMENTS' not in globals():
    CONFRONTO_ELEMENTS = {
        "NATUREZA_GESTO": "Natureza do gesto gráfico (velocidade/pressão/spontaneidade).",
        "MORFOLOGIA": "Morfologia das letras e dimensão.",
        "VALORES_ANGULARES": "Valores angulares e curvaturas predominantes.",
        "ATAQUES_REMATES_5_2": "Ataques e remates - características de início/fim de traço.",
        "PONTOS_CONEXAO": "Pontos de conexão entre elementos gráficos."
    }

# ---------------------------------------------------------------------
# Etapa 6: Conclusão consolidada
# ---------------------------------------------------------------------
def render_module_conclusao():
    st.header("6. CONCLUSÃO")
    if not st.session_state.get("saved_analyses"):
        st.info("Não há análises salvas para gerar a conclusão.")
        return

    analyses = st.session_state.get("saved_analyses", {})
    all_ids = list(analyses.keys())

    with st.form("form_conclusao"):
        st.markdown("Preencha as conclusões individuais e gere o texto final do laudo.")
        for aid in all_ids:
            a = analyses[aid]
            q_label = a.get("questionado_id", aid)
            st.markdown(f"**Análise - Documento:** {q_label}")
            a["conclusao_status"] = st.selectbox(
                f"Conclusão para {q_label}",
                options=["PENDENTE", "AUTENTICA", "FALSA"],
                index=["PENDENTE", "AUTENTICA", "FALSA"].index(a.get("conclusao_status", "PENDENTE")),
                key=f"concl_{aid}"
            )
            a["justificativa_conclusao"] = st.text_area(
                f"Justificativa ({q_label})",
                value=a.get("justificativa_conclusao", ""),
                key=f"just_{aid}",
                height=100
            )
            st.markdown("---")
        submitted = st.form_submit_button("💾 Salvar Conclusões e Gerar Texto Final")
        if submitted:
            # compõe texto final condensado
            partes = []
            for aid in all_ids:
                a = analyses[aid]
                qid = a.get("questionado_id")
                qdisplay = qid
                status = a.get("conclusao_status", "PENDENTE")
                status_text = "PENDENTE"
                if status == "AUTENTICA":
                    status_text = "Autêntica"
                elif status == "FALSA":
                    status_text = "Falsa"
                justificativa = a.get("justificativa_conclusao", "")
                partes.append(f"Documento {qdisplay}: Conclusão - {status_text}. Justificativa: {justificativa}")
            texto_final = "\n\n".join(partes)
            st.session_state["BLOCO_CONCLUSAO_DINAMICO"] = texto_final
            st.session_state.etapas_concluidas.add(6)
            save_current_state({
                "saved_analyses": st.session_state.saved_analyses,
                "BLOCO_CONCLUSAO_DINAMICO": st.session_state.get("BLOCO_CONCLUSAO_DINAMICO", "")
            })
            st.success("Conclusões salvas e texto gerado.")

# ---------------------------------------------------------------------
# Etapa 7: Resposta a Quesitos (autor / réu)
# ---------------------------------------------------------------------
def render_module_quesitos():
    st.header("7. RESPOSTA AOS QUESITOS")
    st.markdown("Preencha as respostas aos quesitos encaminhados pelas partes.")

    colA, colB = st.columns(2)
    with colA:
        st.subheader("Quesitos da Parte Autora")
        lista_aut = st.session_state.get("LISTA_QS_AUTOR", [])
        for q in lista_aut:
            with st.expander(f"Quesito Autor #{q.get('id')}"):
                q["texto"] = st.text_area("Texto do Quesito", value=q.get("texto", ""), key=f"q_aut_text_{q['id']}", height=80)
                q["resposta"] = st.text_area("Resposta do Perito", value=q.get("resposta", ""), key=f"q_aut_resp_{q['id']}", height=120)
                if st.button("🗑️ Excluir Quesito (Autor)", key=f"del_q_aut_{q['id']}"):
                    st.session_state.LISTA_QS_AUTOR = [item for item in st.session_state.LISTA_QS_AUTOR if item["id"] != q["id"]]
                    st.experimental_rerun()
        if st.button("➕ Adicionar Quesito (Autor)"):
            st.session_state.LISTA_QS_AUTOR.append({"id": gerar_id(), "texto": "", "resposta": ""})
            st.experimental_rerun()

    with colB:
        st.subheader("Quesitos da Parte Ré")
        lista_reu = st.session_state.get("LISTA_QS_REU", [])
        for q in lista_reu:
            with st.expander(f"Quesito Réu #{q.get('id')}"):
                q["texto"] = st.text_area("Texto do Quesito", value=q.get("texto", ""), key=f"q_reu_text_{q['id']}", height=80)
                q["resposta"] = st.text_area("Resposta do Perito", value=q.get("resposta", ""), key=f"q_reu_resp_{q['id']}", height=120)
                if st.button("🗑️ Excluir Quesito (Réu)", key=f"del_q_reu_{q['id']}"):
                    st.session_state.LISTA_QS_REU = [item for item in st.session_state.LISTA_QS_REU if item["id"] != q["id"]]
                    st.experimental_rerun()
        if st.button("➕ Adicionar Quesito (Réu)"):
            st.session_state.LISTA_QS_REU.append({"id": gerar_id(), "texto": "", "resposta": ""})
            st.experimental_rerun()

    if st.button("💾 Salvar Quesitos e Gerar Adendos"):
        process_quesitos_to_adendos()
        save_current_state({
            "LISTA_QS_AUTOR": st.session_state.get("LISTA_QS_AUTOR", []),
            "LISTA_QS_REU": st.session_state.get("LISTA_QS_REU", []),
            "adendos": st.session_state.get("adendos", [])
        })
        st.session_state.etapas_concluidas.add(7)
        st.success("Quesitos e adendos salvos.")

# ---------------------------------------------------------------------
# Etapa 8: Encerramento e geração de .docx final
# ---------------------------------------------------------------------
def render_module_encerramento():
    st.header("8. ENCERRAMENTO E GERAÇÃO DO LAUDO")
    st.markdown("Revise anexos, adendos e gere o documento final (.docx).")

    st.markdown("**Anexos (Arquivos dos Documentos Questionados)**")
    anexos = st.session_state.get("anexos", [])
    if anexos:
        for a in anexos:
            st.markdown(f"- {a.get('filename')} (Origem: {a.get('origem')})")
    else:
        st.info("Nenhum anexo carregado.")

    st.markdown("**Adendos (Imagens de Análise / Quesitos)**")
    adendos = st.session_state.get("adendos", [])
    if adendos:
        for ad in adendos:
            st.markdown(f"- {ad.get('descricao')} — {ad.get('filename')}")
    else:
        st.info("Nenhum adendo gerado.")

    if st.button("🚀 Gerar Laudo (.docx)"):
        st.info("Gerando documento... aguarde.")
        dados_para_word = {
            "numero_processo": st.session_state.get("selected_process_id"),
            "AUTOR": st.session_state.get("AUTOR"),
            "REU": st.session_state.get("REU"),
            "DATA_LAUDO": st.session_state.get("DATA_LAUDO"),
            "questionados": st.session_state.get("questionados_list", []),
            "padroes": st.session_state.get("padroes_list", []),
            "analises": st.session_state.get("saved_analyses", {}),
            "BLOCO_CONCLUSAO_DINAMICO": st.session_state.get("BLOCO_CONCLUSAO_DINAMICO", ""),
            "adendos": st.session_state.get("adendos", []),
            "anexos": st.session_state.get("anexos", [])
        }
        try:
            # função do word_handler (padrão do projeto)
            out_path = generate_report_from_template(dados_para_word)
            st.success(f"Laudo gerado com sucesso em: {out_path}")
            with open(out_path, "rb") as f:
                st.download_button("⬇️ Baixar Laudo .DOCX", data=f, file_name=os.path.basename(out_path))
            st.session_state.etapas_concluidas.add(8)
            save_current_state({"BLOCO_CONCLUSAO_DINAMICO": st.session_state.get("BLOCO_CONCLUSAO_DINAMICO", "")})
        except Exception as e:
            st.error(f"Erro ao gerar o laudo: {e}")

# ---------------------------------------------------------------------
# Funções utilitárias para criar / listar processos
# ---------------------------------------------------------------------
def create_new_process(numero_processo: str, autor: str, reu: str):
    if not numero_processo:
        st.error("Informe um número de processo válido.")
        return False
    # cria estrutura básica
    inicial = {
        "numero_processo": numero_processo,
        "AUTOR": autor,
        "REU": reu,
        "DATA_LAUDO": datetime.date.today().isoformat(),
        "questionados_list": [],
        "padroes_list": [],
        "saved_analyses": {},
        "anexos": [],
        "adendos": [],
        "etapas_concluidas": []
    }
    save_process_data(numero_processo, inicial)
    st.success(f"Processo {numero_processo} criado.")
    return True


def list_all_processes():
    try:
        procs = list_processes()
        return procs
    except Exception:
        # fallback: lista arquivos na pasta PROCESS_DATA_DIR
        try:
            files = os.listdir(PROCESS_DATA_DIR)
            return [f.replace(".json","") for f in files if f.endswith(".json")]
        except Exception:
            return []

# --------------------------
# PARTE 4 (final)
# --------------------------

# ---------------------------------------------------------------------
# Inicialização de defaults e UI principal
# ---------------------------------------------------------------------
ensure_session_defaults()

st.sidebar.title("Controle do Processo")
with st.sidebar.expander("🔎 Processos Existentes", expanded=True):
    processes = list_all_processes()
    if processes:
        sel = st.selectbox("Selecione um processo", options=processes, key="sidebar_select_proc", format_func=lambda x: x)
        if st.button("📂 Carregar processo selecionado"):
            load_process(sel)
    else:
        st.info("Nenhum processo encontrado.")

st.sidebar.markdown("---")
st.sidebar.subheader("Criar novo processo")
new_num = st.sidebar.text_input("Número do Processo", key="sidebar_new_num")
new_aut = st.sidebar.text_input("Nome do Autor", key="sidebar_new_aut")
new_reu = st.sidebar.text_input("Nome do Réu", key="sidebar_new_reu")
if st.sidebar.button("➕ Criar processo"):
    ok = create_new_process(new_num, new_aut, new_reu)
    if ok:
        st.experimental_rerun()

st.sidebar.markdown("---")
if st.sidebar.button("💾 Salvar estado atual (manual)"):
    # salva um conjunto reduzido de chaves; pode ser expandido conforme necessidade
    to_save = {
        "AUTOR": st.session_state.get("AUTOR"),
        "REU": st.session_state.get("REU"),
        "DATA_LAUDO": st.session_state.get("DATA_LAUDO").isoformat() if isinstance(st.session_state.get("DATA_LAUDO"), datetime.date) else st.session_state.get("DATA_LAUDO"),
        "questionados_list": st.session_state.get("questionados_list", []),
        "padroes_list": st.session_state.get("padroes_list", []),
        "saved_analyses": st.session_state.get("saved_analyses", {}),
        "anexos": st.session_state.get("anexos", []),
        "adendos": st.session_state.get("adendos", []),
        "etapas_concluidas": list(st.session_state.get("etapas_concluidas", []))
    }
    try:
        save_current_state(to_save)
        st.success("Estado salvo com sucesso.")
    except Exception as e:
        st.error(f"Erro ao salvar estado: {e}")

st.sidebar.markdown("---")
st.sidebar.caption("Versão revisada — Editor de Imagem e EOG dinâmico integrados.")

# ---------------------------------------------------------------------
# Área principal: fluxo em etapas (1..8)
# ---------------------------------------------------------------------
st.title("Gerar Laudo Pericial — Fluxo de Trabalho")

if not st.session_state.process_loaded:
    st.info("Nenhum processo carregado. Crie ou carregue um processo para iniciar.")
    st.markdown("### Iniciar rapidamente")
    quick_num = st.text_input("Número do processo (rápido)", key="quick_num")
    quick_aut = st.text_input("Autor (rápido)", key="quick_aut")
    quick_reu = st.text_input("Réu (rápido)", key="quick_reu")
    if st.button("Criar e carregar (rápido)"):
        if create_new_process(quick_num, quick_aut, quick_reu):
            load_process(quick_num)
else:
    st.success(f"Processo carregado: {st.session_state.get('selected_process_id')}")
    st.markdown(f"**Autor:** {st.session_state.get('AUTOR', 'N/A')}  |  **Réu:** {st.session_state.get('REU', 'N/A')}")
    st.markdown("---")

    # Save callback wrapper
    def save_cb(data_to_save=None):
        try:
            if data_to_save is None:
                # salva everything minimal
                minimal = {
                    "AUTOR": st.session_state.get("AUTOR"),
                    "REU": st.session_state.get("REU"),
                    "DATA_LAUDO": st.session_state.get("DATA_LAUDO").isoformat() if isinstance(st.session_state.get("DATA_LAUDO"), datetime.date) else st.session_state.get("DATA_LAUDO"),
                    "questionados_list": st.session_state.get("questionados_list", []),
                    "padroes_list": st.session_state.get("padroes_list", []),
                    "saved_analyses": st.session_state.get("saved_analyses", {}),
                    "anexos": st.session_state.get("anexos", []),
                    "adendos": st.session_state.get("adendos", []),
                    "etapas_concluidas": list(st.session_state.get("etapas_concluidas", []))
                }
                save_current_state(minimal)
            else:
                save_current_state(data_to_save)
            return True
        except Exception as e:
            st.error(f"Erro ao salvar: {e}")
            return False

    # Render flow: botão ou navegação por etapas
    st.subheader("Navegação Rápida por Etapas")
    col_a, col_b, col_c = st.columns(3)
    if col_a.button("1. Apresentação / Intro"):
        st.session_state._goto = 1
    if col_b.button("4. Documentos (PQ/PCE)"):
        st.session_state._goto = 4
    if col_c.button("5. Análise (EOG)"):
        st.session_state._goto = 5
    if ' _goto' in st.session_state and st.session_state._goto:
        target = st.session_state._goto
    else:
        target = None

    # Decide qual módulo exibir baseado no progresso
    if target == 1 or target is None:
        # show etapa 1 if not completed
        if 1 not in st.session_state.etapas_concluidas:
            # lightweight form for intro
            with st.form("form_intro"):
                st.markdown("### 1. Apresentação e Introdução")
                st.session_state.AUTOR = st.text_input("Nome do Autor", value=st.session_state.get("AUTOR", ""), key="ui_autor")
                st.session_state.REU = st.text_input("Nome do Réu", value=st.session_state.get("REU", ""), key="ui_reu")
                st.session_state.DATA_LAUDO = st.date_input("Data do Laudo", value=st.session_state.get("DATA_LAUDO", datetime.date.today()), key="ui_data_laudo")
                sub = st.form_submit_button("💾 Salvar Introdução")
                if sub:
                    st.session_state.etapas_concluidas.add(1)
                    save_cb()
                    st.success("Dados salvos. Avance para Documentos (Etapa 4).")
                    st.experimental_rerun()
        else:
            st.info("Etapas 1-3 concluídas. Avance para Etapa 4.")

    # Etapa 4
    if 4 not in st.session_state.etapas_concluidas or target == 4:
        render_questionados_section()
        render_padroes_section()

    # Etapa 5 (Análises)
    if 5 not in st.session_state.etapas_concluidas or target == 5:
        render_module_analise()

    # Etapa 6
    if 6 not in st.session_state.etapas_concluidas:
        render_module_conclusao()

    # Etapa 7
    if 7 not in st.session_state.etapas_concluidas:
        render_module_quesitos()

    # Etapa 8 (Encerramento)
    render_module_encerramento()

# ---------------------------------------------------------------------
# Final: instruções e dependências
# ---------------------------------------------------------------------
st.markdown("---")
st.markdown("#### Observações importantes")
st.markdown("""
- Se estiver usando o Editor de Imagem, instale as dependências:
  `pip install streamlit-cropper streamlit-drawable-canvas Pillow`
- O botão de edição abre um editor web com crop + canvas; o resultado é salvo como adendo.
- Sempre faça backup do arquivo original `01_Gerar_laudo.py` antes de colar as 4 partes.
- Depois de colar todas as partes: Commit + Push via GitHub Desktop (sua pipeline fará o deploy).
""")

st.success("Arquivo `01_Gerar_laudo.py` atualizado localmente. Faça commit/push e teste o fluxo.")



