# ======================================================================
# 01_Gerar_laudo.py — PARTE 1
# CONFIGURAÇÃO GERAL + IMPORTS COM FALLBACK + SESSÃO + FUNÇÕES BASE
# Sistema de Geração de Laudo Pericial Grafotécnico
# ======================================================================

import streamlit as st
import uuid
import json
import os
import datetime
import matplotlib.pyplot as plt
from io import BytesIO
from PIL import Image

# ======================================================================
# IMPORTAÇÃO DOS MÓDULOS DE BACKEND (COM FALLBACK INTELIGENTE)
# ======================================================================

BACKEND_OK = True
BACKEND_MESSAGE = ""

try:
    # Tenta importar do pacote src (recomendado)
    from src.data_handler import (
        save_process_data,
        load_process_data,
        list_processes,
        PROCESS_DATA_DIR
    )
    from src.word_handler import generate_report_from_template

except Exception as _e_src:
    # Primeiro fallback: tenta importar dos arquivos na raiz
    try:
        from data_handler import (
            save_process_data,
            load_process_data,
            list_processes,
            PROCESS_DATA_DIR
        )
        from word_handler import generate_report_from_template
        BACKEND_OK = True
        BACKEND_MESSAGE = ""
    except Exception as _e_root:
        BACKEND_OK = False
        BACKEND_MESSAGE = f"src error: {_e_src}  |  root error: {_e_root}"

# ======================================================================
# ALERTA AO USUÁRIO SE O BACKEND NÃO FOI IMPORTADO
# ======================================================================

if not BACKEND_OK:
    st.warning(
        "⚠️ Não foi possível carregar os módulos de backend (src/ ou raiz).\n\n"
        "A funcionalidade de salvar processos, carregar dados e gerar laudo pode estar limitada.\n"
        "Verifique a pasta /src e reinicie a aplicação.\n\n"
        f"Erro detectado: {BACKEND_MESSAGE}"
    )

# ======================================================================
# CONFIGURAÇÕES GERAIS DO PROJETO
# ======================================================================

st.set_page_config(
    page_title="Gerar Laudo Pericial Grafotécnico",
    layout="wide",
    page_icon="✒️"
)

# ======================================================================
# DEFINIÇÕES FIXAS DE EOG
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
# FUNÇÕES DE SESSÃO E ESTADO
# ======================================================================


def safe_get(key, default=None):
    """Obtém valor de st.session_state com fallback."""
    return st.session_state.get(key, default)


def ensure_session_defaults():
    """Inicializa todas as variáveis exigidas pelo sistema."""
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
        "active_questionado_id": None,
        "questionados_list": [],
        "padroes_list": [],
        "anexos": [],
        "adendos": [],
        "etapa_atual": 1,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
        else:
            # normaliza formatos simples
            if key == "etapas_concluidas" and isinstance(st.session_state[key], list):
                st.session_state[key] = set(st.session_state[key])


def _make_serializable(obj):
    """Converte recursivamente objetos para formatos serializáveis por JSON."""
    if isinstance(obj, set):
        return list(obj)
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    if isinstance(obj, datetime.date):
        return obj.isoformat()
    if isinstance(obj, dict):
        result = {}
        for k, v in obj.items():
            # evita salvar objetos grandes (como imagens) inline
            if k in ("imagem_obj", "imagem_bytes", "file_obj", "bytes"):
                continue
            result[k] = _make_serializable(v)
        return result
    if isinstance(obj, list):
        return [_make_serializable(i) for i in obj]
    return obj


def save_current_state(data_to_save: dict = None) -> bool:
    """
    Salva o estado atual do processo no arquivo JSON.
    Se `data_to_save` for None, salva um conjunto padrão de chaves.
    Retorna True se salvo com sucesso.
    """
    if not BACKEND_OK:
        st.error("Salvar indisponível: backend não carregado.")
        return False

    try:
        process_id = st.session_state.get("selected_process_id")
        if not process_id:
            st.error("Número do processo não informado. Selecione ou crie um processo primeiro.")
            return False

        if data_to_save is None:
            data_to_save = {
                "AUTOR": st.session_state.get("AUTOR"),
                "REU": st.session_state.get("REU"),
                "DATA_LAUDO": st.session_state.get("DATA_LAUDO").isoformat()
                if isinstance(st.session_state.get("DATA_LAUDO"), (datetime.date, datetime.datetime))
                else st.session_state.get("DATA_LAUDO"),
                "questionados_list": st.session_state.get("questionados_list", []),
                "padroes_list": st.session_state.get("padroes_list", []),
                "saved_analyses": st.session_state.get("saved_analyses", {}),
                "anexos": st.session_state.get("anexos", []),
                "adendos": st.session_state.get("adendos", []),
                "etapas_concluidas": list(st.session_state.get("etapas_concluidas", [])),
                "etapa_atual": st.session_state.get("etapa_atual", 1),
            }

        serializable = _make_serializable(data_to_save)
        save_process_data(process_id, serializable)
        return True
    except Exception as e:
        st.error(f"Erro ao salvar estado: {e}")
        return False


def load_process(process_id: str) -> bool:
    """Carrega dados salvos de um processo existente para st.session_state."""
    if not BACKEND_OK:
        st.error("Carregamento indisponível: backend não carregado.")
        return False

    try:
        dados = load_process_data(process_id)
    except Exception as e:
        st.error(f"Erro ao carregar dados do processo: {e}")
        return False

    if not dados:
        st.error("Processo não encontrado ou arquivo corrompido.")
        return False

    # aplicar dados no session_state com cuidados de tipos
    for k, v in dados.items():
        if k == "etapas_concluidas" and isinstance(v, list):
            st.session_state[k] = set(v)
        elif k == "DATA_LAUDO" and isinstance(v, str):
            try:
                st.session_state[k] = datetime.date.fromisoformat(v)
            except Exception:
                st.session_state[k] = datetime.date.today()
        else:
            st.session_state[k] = v

    st.session_state["process_loaded"] = True
    st.session_state["selected_process_id"] = process_id
    return True


# ======================================================================
# GERADOR DE IDs PARA QUESTIONADOS
# ======================================================================


def gerar_id(short: bool = True) -> str:
    uid = str(uuid.uuid4())
    return uid[:8] if short else uid


def format_process_label(process_id: str) -> str:
    """Formata exibição da lista de processos."""
    if not BACKEND_OK:
        return f"{process_id} — backend indisponível"
    try:
        dados = load_process_data(process_id)
        if not dados:
            return f"{process_id} — [Erro ao carregar]"
        autor = dados.get("AUTOR", "N/A")
        reu = dados.get("REU", "N/A")
        return f"{process_id} — Autor: {autor} | Réu: {reu}"
    except Exception:
        return f"{process_id} — [Erro ao acessar dados]"

# ======================================================================
# FIM DA PARTE 1
# A PARTIR DAQUI DEVE VIR A PARTE 2 (Editor de imagem, Plot EOG, etc.)
# ======================================================================


# ======================================================================
# PARTE 2 — EDITOR DE IMAGEM, FUNÇÕES DE ANÁLISE E GRÁFICO EOG
# ======================================================================

from typing import Dict, List, Any, Optional
from PIL import Image
from io import BytesIO
import matplotlib.pyplot as plt
from streamlit_drawable_canvas import st_canvas
from streamlit_cropper import st_cropper
import streamlit as st
import uuid

# ======================================================================
# 2.1 — Funções auxiliares de análise
# ======================================================================

def get_analysis_for_questionado(questionado_id: str) -> Dict[str, Any]:
    """
    Recupera a análise salva do questionado.
    Retorna um dicionário com campos de EOG, imagens, texto, etc.
    """
    saved = st.session_state.get("saved_analyses", {})
    return saved.get(questionado_id, {})


def save_analysis_for_questionado(questionado_id: str, analysis: Dict[str, Any]):
    """
    Salva a análise de um questionado dentro do session_state.
    """
    saved = st.session_state.get("saved_analyses", {})
    saved[questionado_id] = analysis
    st.session_state["saved_analyses"] = saved


# ======================================================================
# 2.2 — EDITOR DE IMAGEM (Mesa Gráfica)
# ======================================================================

def image_editor_tool(image_bytes: bytes) -> Optional[bytes]:
    """
    Editor completo de imagem:
    - Crop
    - Zoom
    - Desenho livre
    - Linhas, setas e anotações
    Retorna a imagem final editada como bytes PNG.
    """

    st.subheader("🖼️ Editor de Imagem — Mesa Gráfica")

    # Carrega imagem original
    img = Image.open(BytesIO(image_bytes))

    # 1) CROPPER --------------------------------------------------------
    st.write("### 1) Recortar imagem")
    cropped = st_cropper(
        img,
        realtime_update=True,
        box_color="#ff0000",
        aspect_ratio=None,
        key=f"crop_{uuid.uuid4()}"
    )

    st.write("Imagem recortada:")
    st.image(cropped, use_column_width=True)

    # 2) CANVAS ---------------------------------------------------------
    st.write("### 2) Anotar imagem")
    canvas_result = st_canvas(
        fill_color="rgba(255, 0, 0, 0.3)",
        stroke_color="#0000ff",
        stroke_width=2,
        background_image=cropped,
        update_streamlit=True,
        height=450,
        width=700,
        drawing_mode="freedraw",
        key=f"canvas_{uuid.uuid4()}"
    )

    # 3) EXPORTAÇÃO -----------------------------------------------------

    if canvas_result.image_data is not None:
        final_img = Image.fromarray(canvas_result.image_data.astype("uint8"))
        st.write("### 3) Resultado final")
        st.image(final_img, use_column_width=True)

        buffer = BytesIO()
        final_img.save(buffer, format="PNG")
        return buffer.getvalue()

    return None


# ======================================================================
# 2.3 — GRÁFICO RADAR PARA EOG
# ======================================================================

def plot_eog_radar(eog_data: Dict[str, str]):
    """
    Gera o gráfico Radar dos Elementos de Ordem Geral (EOG).
    Cada EOG possui um valor numérico definido no dicionário EOG_OPCOES_RADAR.
    """

    ordered_keys = [
        "HABILIDADE_VELOCIDADE",
        "ESPONTANEIDADE_DINAMISMO",
        "CALIBRE",
        "ALINHAMENTO_GRAFICO",
        "ATAQUES_REMATES"
    ]

    # Cria lista de valores convertidos (0,1,2)
    values = [
        EOG_OPCOES_RADAR.get(eog_data.get(k, "PENDENTE"), 1)
        for k in ordered_keys
    ]
    values.append(values[0])

    # Labels
    labels = [EOG_ELEMENTS[k] for k in ordered_keys]
    labels.append(labels[0])

    # Ângulos
    N = len(ordered_keys)
    angles = [(n / float(N)) * 2 * 3.141592 for n in range(N)]
    angles.append(angles[0])

    # Plot
    fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True))

    ax.plot(angles, values, linewidth=2)
    ax.fill(angles, values, alpha=0.3)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, fontsize=9)

    ax.set_yticks([0, 1, 2])
    ax.set_yticklabels(["Divergente", "Limitado", "Adequado"])

    ax.set_ylim(0, 2)

    ax.set_title("Análise dos Elementos de Ordem Geral (EOG)", y=1.1)

    st.pyplot(fig)


# ======================================================================
# FIM DA PARTE 2
# A PARTIR DAQUI ENTRA A PARTE 3 (Etapas do Laudo)
# ======================================================================

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
# Pastas padrão de saída
# ---------------------------------------------------------------------
OUTPUT_FOLDER = "output"
DATA_FOLDER = "data"

if not os.path.exists(OUTPUT_FOLDER):
    os.makedirs(OUTPUT_FOLDER)

if not os.path.exists(DATA_FOLDER):
    os.makedirs(DATA_FOLDER)


# ---------------------------------------------------------------------
# Etapas 1, 2 e 3 (simples e funcionais)
# ---------------------------------------------------------------------
def render_etapa_1():
    st.header("1. APRESENTAÇÃO / IDENTIFICAÇÃO")

    st.session_state.AUTOR = st.text_input(
        "Nome do Autor",
        value=st.session_state.get("AUTOR", ""),
        key="etp1_autor"
    )
    st.session_state.REU = st.text_input(
        "Nome do Réu",
        value=st.session_state.get("REU", ""),
        key="etp1_reu"
    )
    st.session_state.DATA_LAUDO = st.date_input(
        "Data do Laudo",
        value=st.session_state.get("DATA_LAUDO", date.today()),
        key="etp1_data"
    )

    if st.button("💾 Salvar Etapa 1", key="save_etp1"):
        save_current_state()
        marcar_etapa_concluida(1)
        st.success("Etapa 1 salva!")


def render_etapa_2():
    st.header("2. NOMEAÇÃO E DOCUMENTOS INICIAIS")

    st.session_state.ID_NOMEACAO = st.text_input(
        "ID Nomeação (Fls.)",
        value=st.session_state.get("ID_NOMEACAO", ""),
        key="etp2_id_nomeacao"
    )

    if st.button("💾 Salvar Etapa 2", key="save_etp2"):
        save_current_state()
        marcar_etapa_concluida(2)
        st.success("Etapa 2 salva!")


def render_etapa_3():
    st.header("3. RECEBIMENTO DOS AUTOS / INTRODUÇÃO")

    st.session_state.ID_PADROES = st.text_input(
        "Fls. dos Padrões",
        value=st.session_state.get("ID_PADROES", ""),
        key="etp3_id_padroes"
    )

    st.session_state.ID_AUTORIDADE_COLETORA = st.text_input(
        "Autoridade Coletora",
        value=st.session_state.get("ID_AUTORIDADE_COLETORA", ""),
        key="etp3_aut_coletora"
    )

    if st.button("💾 Salvar Etapa 3", key="save_etp3"):
        save_current_state()
        marcar_etapa_concluida(3)
        st.success("Etapa 3 salva!")


# ---------------------------------------------------------------------
# Criar novo processo
# ---------------------------------------------------------------------
def create_and_load_new_process(numero_processo, autor, reu):
    if not numero_processo:
        st.error("Informe um número de processo válido.")
        return False

    payload = {
        "AUTOR": autor,
        "REU": reu,
        "DATA_LAUDO": date.today().isoformat(),
        "questionados_list": [],
        "padroes_list": [],
        "saved_analyses": {},
        "anexos": [],
        "adendos": [],
        "etapas_concluidas": [],
        "etapa_atual": 1,
    }

    save_process_data(numero_processo, payload)

    ok = load_process(numero_processo)
    if ok:
        st.success(f"Processo {numero_processo} criado e carregado!")
    return ok


# ---------------------------------------------------------------------
# Geração do DOCX final
# ---------------------------------------------------------------------
def gerar_laudo_docx():
    try:
        dados = {
            "numero_processo": st.session_state.get("selected_process_id"),
            "AUTOR": st.session_state.get("AUTOR"),
            "REU": st.session_state.get("REU"),
            "DATA_LAUDO": st.session_state.get("DATA_LAUDO"),
            "questionados": st.session_state.get("questionados_list", []),
            "padroes": st.session_state.get("padroes_list", []),
            "analises": st.session_state.get("saved_analyses", {}),
            "conclusao_final": st.session_state.get("conclusao_final", ""),
            "LISTA_QS_AUTOR": st.session_state.get("LISTA_QS_AUTOR", []),
            "LISTA_QS_REU": st.session_state.get("LISTA_QS_REU", []),
            "anexos": st.session_state.get("anexos", []),
            "adendos": st.session_state.get("adendos", []),
        }

        try:
            output = generate_report_from_template(dados)
            st.success("Laudo gerado com sucesso!")
            with open(output, "rb") as f:
                st.download_button(
                    "⬇️ Baixar Laudo (.docx)",
                    data=f,
                    file_name=os.path.basename(output)
                )
        except Exception:
            fallback = os.path.join(
                OUTPUT_FOLDER,
                f"{st.session_state.get('selected_process_id')}_LAUDO_DEBUG.json"
            )
            with open(fallback, "w", encoding="utf-8") as fp:
                json.dump(dados, fp, indent=2, ensure_ascii=False)

            st.warning("Erro no template. Gerado arquivo JSON para verificação.")
            with open(fallback, "rb") as f:
                st.download_button(
                    "⬇️ Baixar JSON de Debug",
                    data=f,
                    file_name=os.path.basename(fallback)
                )

    except Exception as e:
        st.error(f"Erro ao gerar o laudo: {e}")


# ---------------------------------------------------------------------
# Sidebar (lista processos, criar, salvar, etc.)
# ---------------------------------------------------------------------
def render_sidebar_controls():
    st.sidebar.markdown("## ⚙️ Controle do Projeto")

    # Lista processos
    try:
        processos = list_processes()
    except Exception:
        processos = []

    if processos:
        choice = st.sidebar.selectbox("Processos encontrados:", processos)

        if st.sidebar.button("📂 Carregar Processo"):
            load_process(choice)
            st.session_state.process_loaded = True
            st.session_state.selected_process_id = choice
            st.session_state.etapa_atual = 1
            st.experimental_rerun()

    else:
        st.sidebar.info("Nenhum processo salvo encontrado.")

    st.sidebar.markdown("---")

    # Criar novo
    st.sidebar.subheader("Criar novo processo")
    new_num = st.sidebar.text_input("Número do Processo", key="new_num")
    new_aut = st.sidebar.text_input("Autor", key="new_aut")
    new_reu = st.sidebar.text_input("Réu", key="new_reu")

    if st.sidebar.button("➕ Criar Processo"):
        if create_and_load_new_process(new_num, new_aut, new_reu):
            st.experimental_rerun()

    st.sidebar.markdown("---")

    if st.sidebar.button("💾 Salvar Estado Manualmente"):
        if save_current_state():
            st.sidebar.success("Estado salvo.")

    st.sidebar.markdown("---")
    st.sidebar.caption("Tema claro/escuro pode ser alternado no topo da tela.")


# ---------------------------------------------------------------------
# UI Principal do Aplicativo
# ---------------------------------------------------------------------
def main_app_ui():
    ensure_session_defaults()

    st.title("Geração de Laudo Pericial — Painel de Trabalho")

    # ============================================================
    # Tema claro/escuro + papel de parede
    # ============================================================
    if "theme_mode" not in st.session_state:
        st.session_state.theme_mode = "dark"

    colA, colB = st.columns([1, 2])

    if colA.button("🌓 Alternar Tema"):
        st.session_state.theme_mode = "light" if st.session_state.theme_mode == "dark" else "dark"

    wallpapers = {
        "Nenhum": "",
        "Linhas discretas": "background: repeating-linear-gradient(0deg,#333,#333 1px,#222 1px,#222 20px);",
        "Grade clara": "background: repeating-linear-gradient(0deg,#eee,#eee 1px,#ccc 1px,#ccc 20px);",
        "Grade escura": "background: repeating-linear-gradient(0deg,#111,#111 1px,#000 1px,#000 20px);",
    }

    wall_sel = colB.selectbox("🎨 Papel de Parede", wallpapers.keys())

    css = "<style> body {"
    css += "color:#000;background:#fff;" if st.session_state.theme_mode == "light" else "color:#fff;background:#1e1e1e;"
    css += wallpapers[wall_sel]
    css += "} </style>"

    st.markdown(css, unsafe_allow_html=True)

    # Painéis laterais
    render_sidebar_etapas()
    render_sidebar_controls()

    # ------------------------------------------------------------------
    # Carregamento do fluxo
    # ------------------------------------------------------------------
    if st.session_state.get("process_loaded", False):

        st.markdown(
            f"### Processo: **{st.session_state.get('selected_process_id')}**<br>"
            f"Autor: **{st.session_state.get('AUTOR','N/A')}** &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"Réu: **{st.session_state.get('REU','N/A')}**",
            unsafe_allow_html=True
        )

        st.markdown("---")

        render_etapas_do_laudo()

        st.markdown("---")
        st.header("Finalização do Laudo")

        if st.button("🚀 Gerar Laudo Final (.docx ou JSON fallback)"):
            gerar_laudo_docx()

    else:
        st.info("Carregue ou crie um processo utilizando o menu lateral.")


# ---------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------
if __name__ == "__main__":
    main_app_ui()
else:
    main_app_ui()
