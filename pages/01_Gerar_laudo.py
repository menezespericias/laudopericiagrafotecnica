# 01_Gerar_laudo_Consolidado.py (CÓDIGO MONOLÍTICO)

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
# Mantendo a importação dos módulos que fazem o trabalho de I/O (salvar/carregar dados, gerar word)
try:
    # Atenção: Se ocorrer ModuleNotFoundError aqui, certifique-se que o diretório 'src'
    # está na raiz do projeto e contém um arquivo __init__.py vazio, e que os arquivos
    # de backend (word_handler, data_handler, db_handler) estão no src.
    from src.word_handler import gerar_laudo
    from src.data_handler import save_process_data, load_process_data
    from src.db_handler import atualizar_status
except ImportError as e:
    st.error(f"Erro de Importação de Backend: {e}. Certifique-se de que os arquivos 'data_handler.py', 'db_handler.py' e 'word_handler.py' estão na pasta 'src' e que o 'src' está na raiz do projeto.")
    def gerar_laudo(*args, **kwargs): st.error("Erro: word_handler não carregado.")
    def save_process_data(*args, **kwargs): return False
    def load_process_data(*args, **kwargs): return {}
    def atualizar_status(*args, **kwargs): pass

# --- Configurações de Ambiente (Paths) ---
# Se este arquivo (01_Gerar_laudo_Consolidado.py) estiver na pasta 'pages', PROJECT_ROOT deve subir um nível.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.join(SCRIPT_DIR, '..')
CAMINHO_MODELO = os.path.join(PROJECT_ROOT, "template", "LAUDO PERICIAL GRAFOTÉCNICO.docx")
OUTPUT_FOLDER = os.path.join(PROJECT_ROOT, "output")
DATA_FOLDER = os.path.join(PROJECT_ROOT, "data")
os.makedirs(DATA_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# --- Funções de Controle de Estado (Do 01_Gerar_laudo.py) ---

def init_session_state():
    """Inicializa chaves essenciais e corrige o tipo de dados após o carregamento."""
    
    # CRÍTICO: 'etapas_concluidas' deve ser um SET para fácil manipulação
    if 'etapas_concluidas' not in st.session_state:
        st.session_state.etapas_concluidas = set()
    elif isinstance(st.session_state.etapas_concluidas, list):
        # Correção para o caso de carregar de um JSON (que transforma SET em LIST)
        st.session_state.etapas_concluidas = set(st.session_state.etapas_concluidas)

    # Inicialização de listas de documentos e análises
    if 'questionados_list' not in st.session_state: st.session_state.questionados_list = []
    if 'padroes_pce_list' not in st.session_state: st.session_state.padroes_pce_list = []
    if 'analises_eog_list' not in st.session_state: st.session_state.analises_eog_list = []
    if 'anexos' not in st.session_state: st.session_state.anexos = []
    if 'adendos' not in st.session_state: st.session_state.adendos = []
    
    # Inicialização de estados dos quesitos (Dict com chave 'list' e 'nao_enviados')
    if 'quesitos_autora_data' not in st.session_state: 
        st.session_state.quesitos_autora_data = {"list": [], "nao_enviados": False}
    if 'quesitos_reu_data' not in st.session_state: 
        st.session_state.quesitos_reu_data = {"list": [], "nao_enviados": False}
        
    # Inicializa flag de carregamento
    if 'process_loaded' not in st.session_state:
        st.session_state.process_loaded = False
        
    # Variáveis críticas para o word_handler
    if 'CAMINHO_MODELO' not in st.session_state: 
        st.session_state.CAMINHO_MODELO = CAMINHO_MODELO
    
    # Variáveis de texto final (para o word_handler)
    if 'BLOCO_CONCLUSAO_DINAMICO' not in st.session_state: st.session_state.BLOCO_CONCLUSAO_DINAMICO = ""
    if 'BLOCO_QUESITOS_AUTOR' not in st.session_state: st.session_state.BLOCO_QUESITOS_AUTOR = ""
    if 'BLOCO_QUESITOS_REU' not in st.session_state: st.session_state.BLOCO_QUESITOS_REU = ""


def save_current_state() -> bool:
    """
    Salva o estado atual do Streamlit (exceto dados temporários) no arquivo JSON do processo.
    - Converte tipos não-serializáveis (set -> list, date/datetime -> ISO string).
    - Remove objetos binários temporários (ex: 'imagem_bytes', 'imagem_obj') para não inflar o JSON.
    - Usa a assinatura de save_process_data(process_id, session_state_data) do data_handler.
    """
    process_id = st.session_state.get('numero_processo')
    if not process_id:
        st.error("Não foi possível salvar: Número de processo ausente.")
        return False

    # 1. Copia o estado atual (evitar mutações diretas em st.session_state)
    raw = dict(st.session_state)

    # 2. Remove chaves temporárias/controle de widget que não devem ser persistidas
    keys_to_exclude_prefixes = ('input_', 'doc_', 'anexo_', 'quesito_', 'editing_', 'form_')
    keys_to_exclude = {'process_to_load', 'CAMINHO_MODELO', 'BLOCO_CONCLUSAO_DINAMICO',
                       'BLOCO_QUESITOS_AUTOR', 'BLOCO_QUESITOS_REU'}
    # Exclui por prefixo
    for k in list(raw.keys()):
        if any(k.startswith(pref) for pref in keys_to_exclude_prefixes):
            keys_to_exclude.add(k)
    for k in keys_to_exclude:
        raw.pop(k, None)

    # 3. Normaliza tipos para JSON — cria uma cópia serializável
    from datetime import date, datetime
    def make_serializable(obj):
        # Sets -> lists
        if isinstance(obj, set):
            return list(obj)
        # date / datetime -> string no formato DD/MM/YYYY
        if isinstance(obj, datetime):
            return obj.strftime("%d/%m/%Y %H:%M:%S")
        if isinstance(obj, date):
            return obj.strftime("%d/%m/%Y")
        # Lists: processa itens recursivamente (p.ex. listas de dicts)
        if isinstance(obj, list):
            new_list = []
            for item in obj:
                # Se for dict, processa suas chaves (ver abaixo)
                if isinstance(item, dict):
                    # remove possíveis blobs/ UploadedFile objects (campos usados aqui: imagem_obj, imagem_bytes, bytes)
                    item = {kk: vv for kk, vv in item.items() if kk not in ('imagem_obj', 'imagem_bytes', 'bytes', 'file_obj')}
                    # aplica serialização recursiva nos valores restantes
                    new_list.append({kk: make_serializable(vv) for kk, vv in item.items()})
                else:
                    new_list.append(make_serializable(item))
            return new_list
        # Dicts: processa recursivamente (remove blobs também)
        if isinstance(obj, dict):
            new_dict = {}
            for kk, vv in obj.items():
                if kk in ('imagem_obj', 'imagem_bytes', 'bytes', 'file_obj'):
                    # pula campos binários
                    continue
                new_dict[kk] = make_serializable(vv)
            return new_dict
        # Tipos primitivos: ficam como estão
        return obj

    serializable_data = {k: make_serializable(v) for k, v in raw.items()}

    # 4. Garante que 'etapas_concluidas' esteja serializável (set -> list)
    if 'etapas_concluidas' in serializable_data and isinstance(serializable_data['etapas_concluidas'], (set, tuple)):
        serializable_data['etapas_concluidas'] = list(serializable_data['etapas_concluidas'])

    # 5. Assegura chaves que o word_handler espera (evita KeyError ao gerar laudo)
    serializable_data.setdefault('BLOCO_CONCLUSAO_DINAMICO', '')
    serializable_data.setdefault('BLOCO_QUESITOS_AUTOR', '')
    serializable_data.setdefault('BLOCO_QUESITOS_REU', '')
    serializable_data.setdefault('RESUMO_CABECALHO', '')

    # 6. Salva usando a função do data_handler (assinatura: process_id, dados)
    try:
        # Chamada CORRIGIDA: apenas 2 argumentos, conforme data_handler.py.
        save_path = save_process_data(process_id, serializable_data)
        # Se save_process_data retornar caminho, considera sucesso
        return bool(save_path)
    except Exception as e:
        st.error(f"Erro ao salvar o estado do processo: {e}")
        return False


def save_current_state_and_log() -> bool:
    """
    Wrapper que chama save_current_state() e registra mensagens amigáveis para o usuário.
    Mantido para compatibilidade com chamadas no UI.
    """
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
    """Carrega dados de um processo existente para o st.session_state."""
    
    # Garante que o processo existe no banco de dados e está ativo antes de carregar
    # (A verificação do arquivo JSON é feita dentro do data_handler)
    try:
        dados_carregados = load_process_data(process_id, DATA_FOLDER)
        
        if dados_carregados:
            # Limpa o estado atual (para não misturar dados)
            st.session_state.clear()
            
            # Recarrega o estado com os dados do arquivo
            for key, value in dados_carregados.items():
                st.session_state[key] = value
                
            # Garante que o estado seja inicializado (corrige tipos, etc.)
            init_session_state()
            
            # Seta as flags de carregamento
            st.session_state.process_loaded = True
            st.session_state.numero_processo = process_id
            st.success(f"✅ Processo **{process_id}** carregado com sucesso!")
            st.rerun()
        else:
            st.session_state.process_loaded = False
            st.error(f"❌ Não há dados salvos para o processo **{process_id}**.")
    except Exception as e:
        st.error(f"❌ Erro ao carregar dados: {e}")

# --------------------------------------------------------------------------------

# --- Constantes de Etapas e Globais (INTEGRADO) ---
ETAPA_ID_1 = 1
ETAPA_ID_2 = 2 
ETAPA_ID_3 = 3 
ETAPA_ID_4 = 4
ETAPA_ID_5 = 5
ETAPA_ID_6 = 6
ETAPA_ID_7 = 7
ETAPA_ID_8 = 8

# Constantes do Módulo 4: DOCUMENTOS
TIPO_DOCUMENTO_OPCOES = [ 
    "Cédula de Identidade", 
    "Procuração", 
    "Declaração de Residência", 
    "Contrato Social",
    "Outros"
]

# Constantes do Módulo 5: ANÁLISE PERICIAL
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
EOG_OPCOES_RADAR = { # para o gráfico de radar
    "ADEQUADO": 2, # Alto
    "DIVERGENTE": 0, # Baixo
    "LIMITADO": 1, # Médio
    "PENDENTE": 1 # Médio (para não distorcer)
}

# Constantes do Módulo 6: CONCLUSÃO
CONCLUSOES_OPCOES = { 
    "AUTENTICA": "Autêntica (Promanou do punho escritor)",
    "FALSA": "Falsa (Não promanou do punho escritor)",
    "PENDENTE": "PENDENTE / Não Avaliada" # Opção inicial/fallback
}

# Constantes do Módulo 7: QUESITOS
NO_QUESITOS_TEXT = "Não foram encaminhados quesitos para resposta para o Perito nomeado."

# --------------------------------------------------------------------------------

# --- FUNÇÕES AUXILIARES (INTEGRADO) ---

# Auxiliares de Lista (Módulo 4)
def add_item(list_key: str, default_data: Dict[str, Any]):
    """Adiciona um novo item à lista de documentos (Questionados ou Padrões)."""
    if list_key not in st.session_state:
        st.session_state[list_key] = []
        
    new_item = {"id": str(uuid.uuid4()), **default_data}
    st.session_state[list_key].append(new_item)

def remove_item(list_key: str, item_id: str):
    """Remove um item da lista de documentos pelo ID."""
    if list_key in st.session_state:
        st.session_state[list_key] = [item for item in st.session_state[list_key] if item.get('id') != item_id]
        st.rerun()

# Auxiliar de Renderização (Módulo 4)
def render_questionado_form(item: Dict[str, Any], idx: int, save_callback: Callable[[], bool]):
    """Renderiza o formulário para um Documento Questionado (4.1)."""
    item_id = item['id']
    is_saved = item.get('is_saved', False)
    
    with st.container(border=True):
        st.caption(f"Documento Questionado {idx+1}")
        
        col_tipo, col_num, col_desc = st.columns([2, 1, 3])
        
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
        
        col_save, col_delete = st.columns([4, 1])
        if col_save.button("💾 Salvar Item", key=f"save_doc_q_{item_id}", type="primary"):
            item['is_saved'] = True
            if save_callback():
                st.success(f"Documento Questionado {idx+1} salvo!")
            else:
                st.error("Falha ao salvar o estado.")
            st.rerun()
            
        if col_delete.button("🗑️ Excluir", key=f"delete_doc_q_{item_id}", type="secondary"):
            remove_item("questionados_list", item_id)
            # Remove a análise associada também
            st.session_state.analises_eog_list = [a for a in st.session_state.analises_eog_list if a.get('questionado_id') != item_id]
            st.rerun()

def render_padrao_form(item: Dict[str, Any], idx: int, save_callback: Callable[[], bool]):
    """Renderiza o formulário para um Documento Padrão (4.2 B)."""
    item_id = item['id']
    is_saved = item.get('is_saved', False)
    
    with st.container(border=True):
        st.caption(f"Documento Padrão {idx+1} (Tipo: {item.get('TIPO_DOCUMENTO_OPCAO', 'N/A')})")
        
        col_tipo, col_num, col_data = st.columns([2, 1, 2])
        
        tipo_selecionado = col_tipo.selectbox(
            "Tipo do Documento",
            options=TIPO_DOCUMENTO_OPCOES,
            index=TIPO_DOCUMENTO_OPCOES.index(item.get('TIPO_DOCUMENTO_OPCAO', TIPO_DOCUMENTO_OPCOES[0])),
            key=f"doc_p_tipo_select_{item_id}"
        )
        item['TIPO_DOCUMENTO_OPCAO'] = tipo_selecionado
        
        # Permite campo de texto se for 'Outros'
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
        
        # Converte a string de data salva para um objeto date (se for string)
        data_salva = item.get('DATA_DOCUMENTO')
        if isinstance(data_salva, str):
            try:
                data_obj = datetime.strptime(data_salva, "%d/%m/%Y").date()
            except ValueError:
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
        item['DATA_DOCUMENTO'] = data_input.strftime("%d/%m/%Y") # Salva como string

        item['DESCRICAO_IMAGEM'] = st.text_area(
            "Descrição dos Padrões (Ex: Assinaturas no campo 'testemunha')",
            value=item.get('DESCRICAO_IMAGEM', "Assinatura"),
            key=f"doc_p_desc_{item_id}",
            height=80
        )
        
        col_save, col_delete = st.columns([4, 1])
        if col_save.button("💾 Salvar Item", key=f"save_doc_p_{item_id}", type="primary"):
            item['is_saved'] = True
            if save_callback():
                st.success(f"Documento Padrão {idx+1} salvo!")
            else:
                st.error("Falha ao salvar o estado.")
            st.rerun()

        if col_delete.button("🗑️ Excluir", key=f"delete_doc_p_{item_id}", type="secondary"):
            remove_item("padroes_pce_list", item_id)
            st.rerun()

# Auxiliares de Análise (Módulo 5)
def get_analysis_for_questionado(questionado_id: str, session_state: Dict[str, Any]) -> Dict[str, Any]:
    """Busca a análise existente para um questionado ou cria uma nova estrutura."""
    
    analises_list = session_state.get('analises_eog_list', [])
    
    # 1. Tenta encontrar uma análise existente
    for analysis in analises_list:
        if analysis.get('questionado_id') == questionado_id:
            return analysis
    
    # 2. Se não encontrar, cria uma nova estrutura
    new_analysis = {
        "id": str(uuid.uuid4()),
        "questionado_id": questionado_id,
        "is_saved": False,
        "conclusao_status": "PENDENTE", # Usado no Módulo 6
        "eog_elements": {key: "PENDENTE" for key in EOG_ELEMENTS.keys()},
        "confronto_texts": {key: "" for key in CONFRONTO_ELEMENTS.keys()},
        "descricao_analise": "",
        "imagem_analise_bytes": None, # Temporário (não serializado no JSON)
        "tem_imagem_analise": False
    }
    
    # 3. Adiciona na lista principal do session_state
    session_state.analises_eog_list.append(new_analysis)
    
    return new_analysis

def render_radar_chart(eog_data: Dict[str, str]):
    """Gera um gráfico de radar baseado nos resultados dos EOGs."""
    
    # Converte os status em valores numéricos
    data = {
        'group': ['Análise EOG'],
        **{key: [EOG_OPCOES_RADAR.get(status, 1)] for key, status in eog_data.items()}
    }
    
    df = pd.DataFrame(data)
    
    categories = list(EOG_ELEMENTS.values())
    N = len(categories)
    
    # Cria uma lista de ângulos
    angles = [n / float(N) * 2 * 3.14159 for n in range(N)]
    angles += angles[:1]
    
    # Valores numéricos da análise (e fecha o círculo)
    values = [EOG_OPCOES_RADAR.get(eog_data.get(k, "PENDENTE"), 1) for k in EOG_ELEMENTS.keys()]
    values += values[:1]
    categories += categories[:1]
    
    fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True))
    
    # Plotagem
    ax.plot(angles, values, linewidth=2, linestyle='solid', label='Documento Questionado')
    ax.fill(angles, values, 'blue', alpha=0.25)
    
    # Rótulos (Categorias)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories[:-1], fontsize=9)
    
    # Rótulos dos níveis (0, 1, 2)
    ax.set_yticks([0, 1, 2])
    ax.set_yticklabels(["Divergente", "Limitado/Pendente", "Adequado"], color="grey", size=8)
    ax.set_ylim(0, 2)
    
    # Título
    ax.set_title('Resumo dos Elementos de Ordem Gráfica (EOG)', size=10, color='grey', y=1.1)
    
    st.pyplot(fig)

# Auxiliares de Conclusão (Módulo 6)
def get_questionado_item(questionado_id: str, questionados_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Busca o item de documento questionado pelo ID."""
    return next((item for item in questionados_list if item['id'] == questionado_id), {})

def get_final_conclusion_text(session_state: Dict[str, Any]) -> str:
    """Gera o texto final da conclusão (BLOCO_CONCLUSAO_DINAMICO) baseado nas conclusões individuais salvas."""
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
        
        # Texto de conclusão:
        # Ex: Em relação ao Documento Questionado 1 (Assinatura contestada, Fls. 10), o signatário é levado a CONCLUIR que: Falsa (Não promanou do punho escritor).
        conclusao_formatada = (
            f"Em relação ao **{q_item.get('TIPO_DOCUMENTO', 'Documento Questionado')}** "
            f"(Grafismo: {q_item.get('DESCRICAO_IMAGEM', 'N/A')}, Fls. {q_item.get('FLS_DOCUMENTOS', 'N/A')}), "
            f"o signatário é levado a CONCLUIR que: **{status_text}**."
        )
        conclusoes_text.append(conclusao_formatada)
        
    # Junta todas as conclusões em um bloco de texto com quebras de linha
    return "\n\n".join(conclusoes_text)

# Auxiliares de Quesitos (Módulo 7)
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
    for idx, item in enumerate(session_state.get('padroes_pce_list', [])):
        tipo = item.get('TIPO_DOCUMENTO_OPCAO', 'S/N')
        if tipo == "Outros":
            tipo = item.get('TIPO_DOCUMENTO_CUSTOM', 'Outros')
        references.append(f"Doc. Padrão {idx+1}: {tipo} (Fls. {item.get('NUMEROS', 'S/N')})")
        
    # 3. Análises EOG (5.1)
    for idx, item in enumerate(session_state.get('analises_eog_list', [])):
        q_item = get_questionado_item(item['questionado_id'], session_state.get('questionados_list', []))
        if q_item:
            references.append(f"Análise Gráfica ({idx+1}): {q_item.get('TIPO_DOCUMENTO', 'N/A')} (Fls. {q_item.get('FLS_DOCUMENTOS', 'N/A')})")
            
    # 4. Blocos de texto de conclusão (6)
    references.append("6. CONCLUSÃO (Bloco de texto final)")

    return references

def process_quesitos_for_adendos(quesitos_list: List[Dict[str, Any]], party_name: str):
    """Processa quesitos com imagem para gerar adendos."""
    
    session_state = st.session_state
    
    # Cria um set de IDs de adendos existentes para esta parte para facilitar a limpeza
    existing_adendo_ids = {a['id_adendo'] for a in session_state.adendos if a.get('origem') == f'quesito_{party_name.lower()}'}
    new_adendo_ids = set()

    for idx, quesito in enumerate(quesitos_list):
        quesito_id = quesito['id']
        
        # Se tem bytes e não é um adendo existente, adiciona como novo adendo
        if quesito.get('imagem_bytes') is not None and quesito_id not in new_adendo_ids:
            
            adendo_id = str(uuid.uuid4())
            new_adendo_ids.add(quesito_id) # Marca que já processou a imagem deste quesito
            
            # Remove o adendo antigo (se existir) e adiciona o novo (limpa/re-cria)
            session_state.adendos = [a for a in session_state.adendos if a.get('id_referencia') != quesito_id]
            
            # Adiciona o novo adendo
            session_state.adendos.append({
                "id_adendo": adendo_id,
                "origem": f"quesito_{party_name.lower()}",
                "id_referencia": quesito_id,
                "descricao": f"{get_quesito_id_text(party_name, idx)} (Imagem de Adendo)",
                "bytes": quesito['imagem_bytes'],
                "filename": f"quesito_{party_name.lower()}_{idx+1}.png" 
            })
            
            # Limpa o campo de bytes para não salvar no JSON (será salvo na lista de Adendos)
            quesito.pop('imagem_bytes', None) 
            quesito['tem_imagem'] = True # Mantém a flag para renderização
        
        # Se não tem imagem, mas a flag diz que tinha, limpa o adendo anterior
        elif quesito.get('imagem_bytes') is None and not quesito.get('tem_imagem', False):
             session_state.adendos = [a for a in session_state.adendos if a.get('id_referencia') != quesito_id]


def generate_quesito_block_text(party_name: str, quesitos_data: Dict[str, Any]) -> str:
    """Gera o bloco de texto final para uma parte (Autor ou Réu)."""
    
    if quesitos_data.get('nao_enviados', False):
        return NO_QUESITOS_TEXT
        
    quesitos_list = quesitos_data.get('list', [])
    if not quesitos_list:
        return NO_QUESITOS_TEXT

    # Título/Identificação (será formatado pelo word_handler no bloco [BLOCO_QUESITOS_XXX])
    block_text = f"Quesitos da Parte {party_name}"
    
    for idx, quesito in enumerate(quesitos_list):
        # 1. Título do Quesito
        block_text += f"\n\n**{get_quesito_id_text(party_name, idx)}:**"
        
        # 2. Resposta
        resposta = quesito.get('resposta', 'Resposta Pendente.')
        block_text += f"\n{resposta}"
        
        # 3. Referências (se houver)
        if quesito.get('referencias'):
            referencias = "\n".join([f"- {ref}" for ref in quesito['referencias']])
            block_text += f"\n\nReferências do Perito:\n{referencias}"
            
        # 4. Adendo de imagem (se houver)
        if quesito.get('tem_imagem', False):
             block_text += f"\n\n(A resposta a este quesito faz referência à Imagem de Adendo de Quesito {idx+1} ao final do Laudo.)"
             
    return block_text

def render_quesito_form(quesito: Dict[str, Any], idx: int, party_name: str, fls_text: str, references: List[str]):
    """Renderiza o formulário para um quesito individual."""
    
    quesito_id = quesito['id']
    st.markdown(f"**{get_quesito_id_text(party_name, idx)}**")
    
    col_fls, col_save_state = st.columns([4, 1])
    
    # Campo de Folhas (Fls.)
    quesito['fls'] = col_fls.text_input(
        "Fls. (Onde o quesito está no processo)",
        value=quesito.get('fls', fls_text),
        key=f'quesito_{party_name.lower()}_fls_{quesito_id}'
    )
    
    # Campo de Texto do Quesito (para referência, mas não vai para o laudo)
    quesito['texto'] = st.text_area(
        "Texto do Quesito (Referência)",
        value=quesito.get('texto', f"Quesito {idx+1}"),
        key=f'quesito_{party_name.lower()}_texto_{quesito_id}',
        height=70
    )
    
    # Campo de Resposta (Vai para o laudo)
    quesito['resposta'] = st.text_area(
        "Resposta do Perito (Texto que irá para o Laudo)",
        value=quesito.get('resposta', 'Com base nos exames realizados, o Perito responde:'),
        key=f'quesito_{party_name.lower()}_resposta_{quesito_id}',
        height=150
    )
    
    # Campo de Referências (Opcional)
    st.markdown("##### Referências Adicionais do Perito (Opcional)")
    
    # Multiselect de referências
    referencias_selecionadas = st.multiselect(
        "Selecione as referências que sustentam a resposta (Serão adicionadas no bloco do quesito)",
        options=references,
        default=quesito.get('referencias', []),
        key=f'quesito_{party_name.lower()}_refs_{quesito_id}'
    )
    quesito['referencias'] = referencias_selecionadas
    
    # Upload de Imagem/Adendo
    col_img, col_info = st.columns([1, 4])
    
    # Verifica se já tem uma imagem salva
    tem_imagem_previa = quesito.get('tem_imagem', False)
    
    uploaded_file = col_img.file_uploader(
        "Adicionar Imagem (Adendo de Quesito)",
        type=['png', 'jpg', 'jpeg'],
        key=f'quesito_{party_name.lower()}_upload_{quesito_id}'
    )
    
    if uploaded_file is not None:
        file_bytes = uploaded_file.read()
        quesito['imagem_bytes'] = file_bytes # Salva o objeto binário temporariamente
        quesito['tem_imagem'] = True
        col_img.image(file_bytes, caption="Imagem Carregada", use_column_width=True)
    elif tem_imagem_previa:
        col_img.info("Adendo de imagem já salvo para este quesito.")
        
    if col_save_state.button("🗑️ Excluir Quesito", key=f'delete_quesito_{party_name.lower()}_{quesito_id}', use_container_width=True):
        remove_item(f'quesitos_{party_name.lower()}_data', quesito_id) # Não funciona remove_item, precisa de ajuste no M7
        # Remove o quesito manualmente (MÓDULO 7 não usa a função add/remove padrão)
        quesito_list_key = f'quesitos_{party_name.lower()}_data'
        if quesito_list_key in st.session_state:
             st.session_state[quesito_list_key]['list'] = [
                item for item in st.session_state[quesito_list_key]['list'] if item.get('id') != quesito_id
            ]
        st.rerun()

def render_quesitos_party(session_state: Dict[str, Any], party_name: str, fls_text: str, save_callback: Callable[[], bool], references: List[str]):
    """Renderiza a interface de quesitos para uma parte (Autor/Réu)."""
    
    state_key = f'quesitos_{party_name.lower()}_data'
    
    # Inicializa o estado se for a primeira vez
    if state_key not in session_state:
        session_state[state_key] = {"list": [], "nao_enviados": False}
        
    # Coloca o checkbox para 'Não Enviados'
    nao_enviados = st.checkbox(
        f"A Parte **{party_name}** não encaminhou quesitos (utilizar o texto padrão: '{NO_QUESITOS_TEXT}')",
        value=session_state[state_key]['nao_enviados'],
        key=f'{state_key}_nao_enviados_checkbox'
    )
    session_state[state_key]['nao_enviados'] = nao_enviados
    
    if nao_enviados:
        st.info(f"O bloco de resposta para a Parte {party_name} será o texto padrão.")
        session_state[state_key]['list'] = [] # Limpa a lista
        return # Fim da renderização para esta parte
        
    # Renderiza a lista de quesitos existentes
    for idx, quesito in enumerate(session_state[state_key]['list']):
        with st.expander(get_quesito_id_text(party_name, idx), expanded=False):
            render_quesito_form(quesito, idx, party_name, fls_text, references)
        
    # Botão para adicionar novo quesito
    if st.button(f"➕ Adicionar Quesito da Parte {party_name}", key=f'add_quesito_{party_name.lower()}', type="secondary"):
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


# Auxiliares de Encerramento (Módulo 8)
def find_anexo_for_questionado(q_id: str, anexos: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    """Encontra o anexo correspondente a um documento questionado pelo ID de referência."""
    # Anexos de documentos questionados devem ter a 'origem' como 'documento_questionado'
    return next((a for a in anexos if a.get('origem') == 'documento_questionado' and a.get('id_referencia') == q_id), None)

def render_anexo_upload_form(q_item: Dict[str, Any], anexos: List[Dict[str, Any]], session_state: Dict[str, Any], save_callback: Callable[[], bool]):
    """Renderiza o uploader de anexo para um documento questionado específico."""
    
    q_id = q_item['id']
    anexo_existente = find_anexo_for_questionado(q_id, anexos)
    
    descricao = f"ANEXO para {q_item.get('TIPO_DOCUMENTO', 'Documento')} (Fls. {q_item.get('FLS_DOCUMENTOS', 'N/A')})"
    
    with st.container(border=True):
        st.caption(descricao)
        col1, col2 = st.columns([4, 1])

        # Se já existe, mostra o botão de exclusão
        if anexo_existente:
            col1.info("Anexo de documento questionado já carregado. Você pode excluí-lo abaixo se necessário.")
            
            if col2.button("🗑️ Excluir Anexo", key=f'delete_anexo_{q_id}', type="secondary", use_container_width=True):
                # Remove o anexo da lista
                session_state.anexos = [a for a in session_state.anexos if a.get('id_referencia') != q_id]
                if save_callback():
                    st.success(f"Anexo de {q_item.get('TIPO_DOCUMENTO')} excluído.")
                st.rerun()
                
        # Se não existe, mostra o uploader
        else:
            uploaded_file = col1.file_uploader(
                f"Upload do Arquivo ({'ANEXO'} - PDF/Imagem)",
                type=['pdf', 'png', 'jpg', 'jpeg'],
                key=f'anexo_upload_{q_id}'
            )

            if uploaded_file is not None:
                file_bytes = uploaded_file.read()
                file_name = uploaded_file.name

                # Adiciona o novo anexo
                session_state.anexos.append({
                    "id": str(uuid.uuid4()),
                    "origem": "documento_questionado",
                    "id_referencia": q_id, # ID do documento questionado
                    "descricao": descricao,
                    "bytes": file_bytes,
                    "filename": file_name,
                    "mime_type": uploaded_file.type
                })
                
                if save_callback():
                    st.success(f"Anexo de {q_item.get('TIPO_DOCUMENTO')} carregado com sucesso!")
                st.rerun()
            else:
                col2.empty() # Não mostra nada na coluna de exclusão
# --------------------------------------------------------------------------------

# --- FUNÇÕES DE RENDERIZAÇÃO DE ETAPAS (INTEGRADO) ---

# RENDERIZAÇÃO 1: APRESENTAÇÃO/OBJETIVOS/INTRODUÇÃO (Blocos 1, 2 e 3)
def render_etapa_1(session_state: Dict[str, Any], save_callback: Callable[[], bool]):
    """Renderiza a interface da Etapa 1, englobando o preenchimento de dados fixos dos Blocos 1, 2 e 3."""
    
    ETAPA_TITULO = "1. APRESENTAÇÃO, 2. OBJETIVOS e 3. INTRODUÇÃO"
    
    # Verifica se TODAS as etapas estão concluídas para marcar o módulo visualmente
    is_completed = ETAPA_ID_1 in session_state.etapas_concluidas and \
                   ETAPA_ID_2 in session_state.etapas_concluidas and \
                   ETAPA_ID_3 in session_state.etapas_concluidas
    
    with st.expander(f"✅ {ETAPA_TITULO}" if is_completed else f"➡️ {ETAPA_TITULO}", expanded=not is_completed):
        
        st.markdown("##### 1. APRESENTAÇÃO E 2. OBJETIVOS")
        
        # Inicia o formulário para salvar todos os campos de uma vez
        with st.form("bloco_1_e_2_form"):
            
            # Campos de Dados Essenciais (Processo, Partes) - Preenchidos no home.py, apenas exibidos
            st.info(f"Processo: **{session_state.get('numero_processo', 'N/A')}** | Autor: **{session_state.get('AUTOR', 'N/A')}** | Réu: **{session_state.get('REU', 'N/A')}**")
            
            col1, col2 = st.columns(2)
            
            # Campo Juízo de Direito (necessário para os Blocos 1 e 2)
            session_state.JUIZO_DE_DIREITO = col1.text_input(
                "Juízo de Direito / Autoridade Solicitante",
                value=session_state.get('JUIZO_DE_DIREITO', 'Excelentíssimo(a) Senhor(a) Doutor(a) Juiz(a) de Direito'),
                key='input_JUIZO_DE_DIREITO'
            )
            
            # Campo ID_NOMEACAO (necessário para os Blocos 1 e 2)
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
            
            st.markdown("---")
            st.markdown("##### 3. INTRODUÇÃO (Contexto da Perícia)")
            
            # Campo ID_PADROES (para o Bloco 3, item 4.2 B)
            session_state.ID_PADROES = st.text_input(
                "ID Padrões (Fls. dos Padrões Encontrados nos Autos)", 
                value=session_state.get('ID_PADROES', '100-110'),
                key='input_ID_PADROES'
            )

            # Campo ID_AUTORIDADE_COLETORA (para o Bloco 3, item 4.2 A)
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
            
            submitted = st.form_submit_button("💾 Salvar Blocos 1, 2 e 3", type="primary")
            
            if submitted:
                # 1. Marca TODOS os módulos de texto fixo/endereçamento como concluídos
                session_state.etapas_concluidas.add(ETAPA_ID_1) 
                session_state.etapas_concluidas.add(ETAPA_ID_2)
                session_state.etapas_concluidas.add(ETAPA_ID_3)
                
                # 2. Salva o estado completo
                if save_callback():
                    st.success("Dados de Apresentação, Objetivos e Introdução salvos com sucesso!")
                    st.rerun()
                else:
                    st.error("Falha ao salvar o estado do processo.")


# RENDERIZAÇÃO 4: DOCUMENTOS SUBMETIDOS A EXAME (Bloco 4)
def render_etapa_4(session_state: Dict[str, Any], save_callback: Callable[[], bool]):
    """Renderiza a interface da Etapa 4 (Documentos Submetidos a Exame)."""
    
    ETAPA_TITULO = "4. DOCUMENTOS SUBMETIDOS A EXAME"
    is_completed = ETAPA_ID_4 in session_state.etapas_concluidas
    
    with st.expander(f"✅ {ETAPA_TITULO}" if is_completed else f"➡️ {ETAPA_TITULO}", expanded=not is_completed):
        
        st.markdown("#### 4.1 Documentos Questionados (PQ)")
        st.info("Cadastre os documentos que contêm o grafismo contestado (Questionados).")
        
        # --- 4.1 Documentos Questionados (PQ) ---
        with st.container(border=True):
            
            # Renderiza os itens existentes
            for idx, item in enumerate(session_state.questionados_list):
                render_questionado_form(item, idx, save_callback)

            if not session_state.questionados_list:
                st.info("Nenhum documento questionado adicionado.")
            
            # Botões de Ação para 4.1
            col_add_pq, col_save_pq = st.columns([1, 4])
            
            if col_add_pq.button("➕ Adicionar Questionado (PQ)", key="add_questionado", type="secondary", use_container_width=True):
                # Adiciona o item e faz um rerun para renderizar o novo campo
                add_item("questionados_list", {
                    "TIPO_DOCUMENTO": "Doc. Questionado",
                    "FLS_DOCUMENTOS": "Fls. X",
                    "DESCRICAO_IMAGEM": "Assinatura contestada"
                })
                st.rerun()
                
            if col_save_pq.button("💾 Concluir Etapa 4 (Verificar e Salvar)", key="save_docs_q", type="primary", use_container_width=True):
                
                # 1. Verifica se há pelo menos um documento questionado
                if not session_state.questionados_list:
                    st.warning("É obrigatório cadastrar pelo menos um **Documento Questionado**.")
                    return
                
                # 2. Verifica se pelo menos um documento padrão (PCE ou PCA) foi cadastrado/marcado
                is_pca_active = session_state.get('ID_AUTORIDADE_COLETORA', 'este Perito') != '' and session_state.get('COLETA_DE_PADROES_ATIVA', True)
                is_pce_active = len(session_state.padroes_pce_list) > 0
                
                if not is_pca_active and not is_pce_active:
                    st.warning("É obrigatório cadastrar pelo menos um **Documento Padrão** (PCA ou PCE).")
                    return
                
                # 3. Garante que todos os itens estão salvos individualmente
                all_q_saved = all(item.get('is_saved', False) for item in session_state.questionados_list)
                all_p_saved = all(item.get('is_saved', False) for item in session_state.padroes_pce_list)
                
                if not all_q_saved or (is_pce_active and not all_p_saved):
                    st.warning("Salve todos os documentos (Questionados e Padrões) antes de concluir a etapa.")
                    return
                
                # 4. Se tudo OK, salva a etapa
                session_state.etapas_concluidas.add(ETAPA_ID_4)
                
                if save_callback():
                    st.success("Etapa 4 (Documentos) concluída e salva!")
                    st.rerun()
                else:
                    st.error("Falha ao salvar o estado do processo.")
                    
        
        st.markdown("#### 4.2 Documentos Padrão (PC)")
        
        # --- 4.2 A. Padrões Colhidos no Ato Pericial (PCA) ---
        st.markdown("##### ➡️ A. Padrões Colhidos no Ato Pericial (PCA)")
        st.info("Se não houve coleta de padrões no ato pericial, desmarque o checkbox.")
        
        session_state.COLETA_DE_PADROES_ATIVA = st.checkbox(
            "Houve Coleta de Padrões no Ato Pericial (PCA)",
            value=session_state.get('COLETA_DE_PADROES_ATIVA', True),
            key='pca_checkbox'
        )

        if session_state.COLETA_DE_PADROES_ATIVA:
            st.markdown(f"O Perito utilizará o Bloco 4.2 A no laudo, referenciando a autoridade coletora como: **{session_state.get('ID_AUTORIDADE_COLETORA', 'este Perito')}**.")
        else:
            st.warning("O Bloco 4.2 A não será incluído no laudo.")
        
        st.markdown("---")
        
        # --- 4.2 B. Padrões Encontrados nos Autos (PCE) ---
        st.markdown("##### ➡️ B. Padrões Encontrados nos Autos (PCE)")
        st.info("Cadastre os documentos que contêm grafismos autênticos do autor (Padrões).")
        
        with st.container(border=True):
            
            # Renderiza os itens existentes
            for idx, item in enumerate(session_state.padroes_pce_list):
                render_padrao_form(item, idx, save_callback)

            if not session_state.padroes_pce_list:
                st.info("Nenhum documento padrão (PCE) adicionado.")

            # Botões de Ação para 4.2 B
            col_add_pce, col_save_pce = st.columns([1, 4])
            
            if col_add_pce.button("➕ Adicionar Padrão (PCE)", key="add_padrao", type="secondary", use_container_width=True):
                # Adiciona o item e faz um rerun para renderizar o novo campo
                add_item("padroes_pce_list", {
                    "TIPO_DOCUMENTO_OPCAO": TIPO_DOCUMENTO_OPCOES[0],
                    "NUMEROS": "Fls. X",
                    "DATA_DOCUMENTO": date.today().strftime("%d/%m/%Y"),
                    "DESCRICAO_IMAGEM": "Assinatura"
                })
                st.rerun()
                
            if col_save_pce.button("💾 Salvar Documentos Padrão (PCE)", key="save_docs_p", type="primary", use_container_width=True):
                # Garante que todos os itens estão salvos individualmente
                all_p_saved = all(item.get('is_saved', False) for item in session_state.padroes_pce_list)
                
                if not all_p_saved:
                    st.warning("Salve todos os Documentos Padrão antes de salvar.")
                    return

                if save_callback():
                    st.success("Documentos Padrão (PCE) salvos!")
                    st.rerun()
                else:
                    st.error("Falha ao salvar o estado do processo.")


# RENDERIZAÇÃO 5: EXAMES PERICIAIS E METODOLOGIA (Bloco 5)
def render_etapa_5(session_state: Dict[str, Any], save_callback: Callable[[], bool]):
    """Renderiza a interface da Etapa 5 (Exames Periciais e Metodologia)."""
    
    ETAPA_TITULO = "5. EXAMES PERICIAIS E METODOLOGIA"
    is_completed = ETAPA_ID_5 in session_state.etapas_concluidas
    
    # 1. Checa pré-requisito (Etapa 4 concluída)
    if ETAPA_ID_4 not in session_state.get('etapas_concluidas', set()):
        st.warning("⚠️ **Etapa 4 Incompleta:** Conclua o cadastro de Documentos (Etapa 4) para iniciar a Análise Pericial.")
        return

    questionados_list = session_state.get('questionados_list', [])
    if not questionados_list:
        st.warning("⚠️ **Documentos Ausentes:** Não há documentos questionados cadastrados para realizar a análise.")
        return
        
    # 2. Cria as opções de Documento Questionado para o SelectBox
    questionados_options = {
        item['id']: f"Doc. {idx + 1}: {item.get('TIPO_DOCUMENTO', 'S/N')} (Fls. {item.get('FLS_DOCUMENTOS', 'S/N')})"
        for idx, item in enumerate(questionados_list)
    }
    
    # 3. Garante que cada Documento Questionado tenha uma entrada em 'analises_eog_list'
    existing_q_ids = {a['questionado_id'] for a in session_state.analises_eog_list}
    for q_id in questionados_options.keys():
        if q_id not in existing_q_ids:
            get_analysis_for_questionado(q_id, session_state) # Cria a estrutura se não existir

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
        
        # 4. Renderiza a análise para o documento selecionado
        with st.form(f"analise_form_{selected_id}"):
            
            st.markdown("---")
            st.markdown("##### 5.1 Análise dos Paradigmas (EOG - Elementos de Ordem Geral)")
            
            # --- Tabela/Inputs para EOG ---
            eog_data = current_analysis['eog_elements']
            
            col_eog1, col_eog2 = st.columns(2)
            
            # Coluna 1
            eog_data["HABILIDADE_VELOCIDADE"] = col_eog1.selectbox(
                f"1. {EOG_ELEMENTS['HABILIDADE_VELOCIDADE']}",
                options=list(EOG_OPCOES.keys()),
                format_func=lambda x: EOG_OPCOES[x],
                index=list(EOG_OPCOES.keys()).index(eog_data.get("HABILIDADE_VELOCIDADE", "PENDENTE")),
                key=f'eog_hab_{selected_id}'
            )
            eog_data["CALIBRE"] = col_eog1.selectbox(
                f"3. {EOG_ELEMENTS['CALIBRE']}",
                options=list(EOG_OPCOES.keys()),
                format_func=lambda x: EOG_OPCOES[x],
                index=list(EOG_OPCOES.keys()).index(eog_data.get("CALIBRE", "PENDENTE")),
                key=f'eog_calibre_{selected_id}'
            )
            eog_data["ATAQUES_REMATES"] = col_eog1.selectbox(
                f"5. {EOG_ELEMENTS['ATAQUES_REMATES']}",
                options=list(EOG_OPCOES.keys()),
                format_func=lambda x: EOG_OPCOES[x],
                index=list(EOG_OPCOES.keys()).index(eog_data.get("ATAQUES_REMATES", "PENDENTE")),
                key=f'eog_ataques_{selected_id}'
            )

            # Coluna 2
            eog_data["ESPONTANEIDADE_DINAMISMO"] = col_eog2.selectbox(
                f"2. {EOG_ELEMENTS['ESPONTANEIDADE_DINAMISMO']}",
                options=list(EOG_OPCOES.keys()),
                format_func=lambda x: EOG_OPCOES[x],
                index=list(EOG_OPCOES.keys()).index(eog_data.get("ESPONTANEIDADE_DINAMISMO", "PENDENTE")),
                key=f'eog_esp_{selected_id}'
            )
            eog_data["ALINHAMENTO_GRAFICO"] = col_eog2.selectbox(
                f"4. {EOG_ELEMENTS['ALINHAMENTO_GRAFICO']}",
                options=list(EOG_OPCOES.keys()),
                format_func=lambda x: EOG_OPCOES[x],
                index=list(EOG_OPCOES.keys()).index(eog_data.get("ALINHAMENTO_GRAFICO", "PENDENTE")),
                key=f'eog_alin_{selected_id}'
            )
            
            # --- Radar Chart de EOG ---
            st.markdown("##### ➡️ Visualização da Análise de EOG")
            render_radar_chart(eog_data)
            
            st.markdown("---")
            st.markdown("##### 5.2 Confronto Grafoscópico (Elementos de Ordem Genética/Individual)")
            
            # --- Tabela/Inputs para Confronto ---
            confronto_texts = current_analysis['confronto_texts']
            
            # Cria 5 campos de texto para os elementos do confronto
            for key, description in CONFRONTO_ELEMENTS.items():
                confronto_texts[key] = st.text_area(
                    description,
                    value=confronto_texts.get(key, f"Descrição do Confronto para {description}"),
                    key=f'confronto_text_{key}_{selected_id}',
                    height=100
                )
                
            st.markdown("---")
            st.markdown("##### 5.3 Descrição da Análise Detalhada (Opcional - Adendo de Imagem)")
            
            # Campo de Descrição de Adendo/Imagem
            current_analysis['descricao_analise'] = st.text_area(
                "Descrição Detalhada do Exame (Texto livre, não vai para o laudo, apenas para referência e descrição do adendo)",
                value=current_analysis.get('descricao_analise', 'Análise detalhada do grafismo...'),
                key=f'desc_analise_{selected_id}',
                height=150
            )

            # Upload de Imagem de Adendo de Análise
            col_img_up, col_img_info = st.columns([1, 4])
            uploaded_file = col_img_up.file_uploader(
                "Adicionar Imagem de Análise (Adendo)",
                type=['png', 'jpg', 'jpeg'],
                key=f'analise_upload_adendo_{selected_id}'
            )

            if uploaded_file is not None:
                file_bytes = uploaded_file.read()
                # Salva o objeto binário temporariamente no item de análise
                current_analysis['imagem_analise_bytes'] = file_bytes
                current_analysis['tem_imagem_analise'] = True
                col_img_up.image(file_bytes, caption="Imagem para Adendo Carregada", use_column_width=True)
            elif current_analysis.get('tem_imagem_analise', False):
                col_img_info.info("Adendo de imagem de análise já salvo.")
            
            # Botão de Salvar
            submitted = st.form_submit_button("💾 Salvar Análise (5.1 e 5.2)", type="primary")

            if submitted:
                # 1. Processa a imagem de adendo (se houver)
                image_bytes = current_analysis.get('imagem_analise_bytes')
                if image_bytes:
                    adendo_id = str(uuid.uuid4())
                    
                    # Limpa o adendo antigo (se existir)
                    session_state.adendos = [a for a in session_state.adendos if a.get('origem') != 'analise_eog' or a.get('id_referencia') != selected_id]
                    
                    # Adiciona o novo adendo
                    session_state.adendos.append({
                        "id_adendo": adendo_id,
                        "origem": "analise_eog",
                        "id_referencia": selected_id,
                        "descricao": f"Análise Gráfica Detalhada (5.0) para {questionados_options[selected_id]}",
                        "bytes": image_bytes,
                        "filename": f"analise_{selected_id}.png"
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
                    st.success(f"Análise para **{questionados_options[selected_id]}** salva com sucesso!")
                    if all_saved:
                         st.info("✅ Todas as análises de EOG/Confronto foram salvas. Você pode prosseguir para a próxima etapa.")
                    st.rerun()
                else:
                    st.error("Falha ao salvar o estado do processo.")


# RENDERIZAÇÃO 6: CONCLUSÃO (Bloco 6)
def render_etapa_6(session_state: Dict[str, Any], save_callback: Callable[[], bool]):
    """Renderiza a interface da Etapa 6 (Conclusão)."""
    
    ETAPA_TITULO = "6. CONCLUSÃO"
    is_completed = ETAPA_ID_6 in session_state.etapas_concluidas
    
    # Pré-requisito: Etapa 5 concluída
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
        st.info("Para cada documento analisado, defina a conclusão final.")
        
        with st.form("conclusao_form"):
            
            for idx, analise in enumerate(analises):
                q_id = analise['questionado_id']
                q_item = get_questionado_item(q_id, questionados)
                
                if not q_item:
                    st.warning(f"Documento questionado de ID {q_id} não encontrado. Ignorando.")
                    continue
                
                st.markdown(f"**Documento Questionado {idx+1}:** {q_item.get('TIPO_DOCUMENTO', 'N/A')} (Fls. {q_item.get('FLS_DOCUMENTOS', 'N/A')})")
                
                # Input de Status
                analise['conclusao_status'] = st.selectbox(
                    "Resultado da Perícia:",
                    options=list(CONCLUSOES_OPCOES.keys()),
                    format_func=lambda x: CONCLUSOES_OPCOES[x],
                    index=list(CONCLUSOES_OPCOES.keys()).index(analise.get('conclusao_status', "PENDENTE")),
                    key=f'conclusao_status_{q_id}'
                )
                
                # Input de Justificativa
                analise['justificativa_conclusao'] = st.text_area(
                    "Justificativa para a Conclusão (Texto Opcional, para consulta interna)",
                    value=analise.get('justificativa_conclusao', 'Justificar se a conclusão é Autêntica ou Falsa.'),
                    key=f'justificativa_conclusao_{q_id}',
                    height=100
                )
                
                # Mensagens de alerta específicas
                if analise['conclusao_status'] == "FALSA":
                    analise['is_simulacao'] = st.checkbox(
                        "Adicionar texto sobre 'Esforço e simulação por terceiro' no bloco de justificativa (Texto que vai para o laudo)",
                        value=analise.get('is_simulacao', False),
                        key=f'simulacao_checkbox_{q_id}'
                    )
                else:
                    # Garante que a chave não existe se o status não for FALSA
                    analise.pop('is_simulacao', None) 
                
                st.markdown("---")
                
            submitted = st.form_submit_button("💾 Gerar e Salvar Conclusão Final", type="primary")

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
            st.markdown(session_state.get('BLOCO_CONCLUSAO_DINAMICO', 'N/A'))


# RENDERIZAÇÃO 7: RESPOSTA AOS QUESITOS (Bloco 7)
def render_etapa_7(session_state: Dict[str, Any], save_callback: Callable[[], bool]):
    """Renderiza a interface da Etapa 7 (Resposta aos Quesitos)."""

    ETAPA_TITULO = "7. RESPOSTA AOS QUESITOS"
    is_completed = ETAPA_ID_7 in session_state.etapas_concluidas
    
    # Pré-requisito: Etapa 6 concluída
    if ETAPA_ID_6 not in session_state.get('etapas_concluidas', set()):
        st.warning("⚠️ **Etapa 6 Incompleta:** Conclua a Conclusão (Etapa 6) para iniciar a Resposta aos Quesitos.")
        return
    
    # Coleta todas as referências possíveis
    references = gather_all_references(session_state)

    with st.expander(f"✅ {ETAPA_TITULO}" if is_completed else f"➡️ {ETAPA_TITULO}", expanded=not is_completed):
        
        with st.form("quesitos_form"):
            
            # --- 7.1 Quesitos da Parte Autora ---
            st.markdown("#### 7.1 Quesitos da Parte Autora")
            render_quesitos_party(
                session_state=session_state,
                party_name="Autora",
                fls_text=f"Fls. {session_state.get('ID_NOMEACAO', '1-2')}", # Usa Fls. da Nomeação como padrão
                save_callback=save_callback,
                references=references
            )
            
            st.markdown("---")

            # --- 7.2 Quesitos da Parte Ré ---
            st.markdown("#### 7.2 Quesitos da Parte Ré")
            render_quesitos_party(
                session_state=session_state,
                party_name="Réu",
                fls_text="Fls. 50-60", # Placeholder para Fls. do Réu
                save_callback=save_callback,
                references=references
            )
            
            st.markdown("---")
            
            submitted = st.form_submit_button("💾 Salvar Respostas aos Quesitos", type="primary")

            if submitted:
                
                # 1. Processa as imagens de quesitos para gerar adendos
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
            st.markdown(session_state.get('BLOCO_QUESITOS_AUTOR', 'N/A'))
            
            st.markdown("---")
            st.markdown("###### Bloco Quesitos Réu (`[BLOCO_QUESITOS_REU]`)")
            st.markdown(session_state.get('BLOCO_QUESITOS_REU', 'N/A'))


# RENDERIZAÇÃO 8: ENCERRAMENTO E GERAÇÃO DO LAUDO (Bloco 8)
def render_etapa_8(session_state: Dict[str, Any], save_callback: Callable[[], bool], project_root: str):
    """Renderiza a interface da Etapa 8 (Encerramento)."""
    
    ETAPA_TITULO = "8. ENCERRAMENTO E GERAÇÃO DO LAUDO"
    is_completed = ETAPA_ID_8 in session_state.etapas_concluidas
    
    # Pré-requisito: Etapa 7 concluída
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

        st.markdown("##### ➡️ Geração Final")
        
        # Última chance de salvar os anexos (se tiver)
        if st.button("💾 Salvar Anexos e Adendos (Pré-Geração)", key="save_anexos", type="secondary"):
            if save_callback():
                st.success("Dados de encerramento salvos!")
                st.rerun()
            else:
                st.error("Falha ao salvar o estado do processo.")
                
        st.markdown("---")
        
        if st.button("🚀 GERAR LAUDO FINAL (.DOCX)", key="generate_laudo", type="primary"):
            
            # 1. Prepara os dados para o word_handler
            dados_para_word = {
                'NUMERO_PROCESSO': session_state.get('numero_processo', 'N/A'),
                'AUTOR': session_state.get('AUTOR', 'N/A'),
                'REU': session_state.get('REU', 'N/A'),
                'JUIZO_DE_DIREITO': session_state.get('JUIZO_DE_DIREITO', 'N/A'),
                'ID_NOMEACAO': session_state.get('ID_NOMEACAO', 'N/A'),
                'DATA_LAUDO': session_state.get('DATA_LAUDO', date.today()).strftime("%d/%m/%Y"),
                'ID_PADROES': session_state.get('ID_PADROES', 'N/A'),
                'ID_AUTORIDADE_COLETORA': session_state.get('ID_AUTORIDADE_COLETORA', 'N/A'),
                'AUTOR_ASSINATURA': session_state.get('AUTOR_ASSINATURA', 'N/A'),
                'COLETA_DE_PADROES_ATIVA': session_state.get('COLETA_DE_PADROES_ATIVA', True),
                
                # Listas
                'questionados_list': session_state.get('questionados_list', []),
                'padroes_pce_list': session_state.get('padroes_pce_list', []),
                'analises_eog_list': session_state.get('analises_eog_list', []),
                
                # Blocos de texto finais
                'BLOCO_CONCLUSAO_DINAMICO': session_state.get('BLOCO_CONCLUSAO_DINAMICO', ''),
                'BLOCO_QUESITOS_AUTOR': session_state.get('BLOCO_QUESITOS_AUTOR', ''),
                'BLOCO_QUESITOS_REU': session_state.get('BLOCO_QUESITOS_REU', '')
            }
            
            # 2. Define caminhos
            now = datetime.now().strftime("%Y%m%d_%H%M%S")
            caminho_saida = os.path.join(OUTPUT_FOLDER, f"{session_state.numero_processo}_LAUDO_{now}.docx")
            caminho_modelo = session_state.get('CAMINHO_MODELO', f"{project_root}/template/LAUDO PERICIAL GRAFOTÉCNICO.docx")
            
            # 3. Executa a geração
            try:
                gerar_laudo(
                    caminho_modelo=caminho_modelo,
                    caminho_saida=caminho_saida,
                    dados=dados_para_word,
                    anexos=session_state.anexos,
                    adendos=session_state.adendos
                )
                
                # 4. Finaliza
                session_state.etapas_concluidas.add(ETAPA_ID_8)
                
                if save_callback():
                    st.success(f"Laudo **{session_state.numero_processo}** gerado e salvo com sucesso! Baixe o arquivo abaixo.")
                
                # Adiciona botão de download
                with open(caminho_saida, "rb") as file:
                    st.download_button(
                        label="⬇️ Baixar Laudo .DOCX",
                        data=file,
                        file_name=caminho_saida.split('/')[-1],
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    )
                # st.rerun() # Não é estritamente necessário se o download for o último passo
                st.balloons()

            except FileNotFoundError:
                st.error(f"❌ Erro de Arquivo: O arquivo de modelo não foi encontrado. Caminho esperado: `{caminho_modelo}`.")
            except Exception as e:
                st.error(f"❌ Erro na Geração do Laudo: {e}")

# --------------------------------------------------------------------------------
# --- DASHBOARD PRINCIPAL (EXECUÇÃO) ---
# --------------------------------------------------------------------------------

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
    st.caption(f"Autor: {st.session_state.get('AUTOR', 'N/A')} | Réu: {st.session_state.get('REU', 'N/A')}")
    st.caption(f"Juízo: {st.session_state.get('JUIZO_DE_DIREITO', 'N/A')}")
    
    # Função auxiliar para o fluxo sequencial
    def save_current_state_and_log():
        """Função wrapper para salvar e garantir a exibição de logs."""
        return save_current_state()

    # RENDERIZAÇÃO 1, 2, 3: APRESENTAÇÃO/OBJETIVOS/INTRODUÇÃO (Blocos 1, 2 e 3 - Etapas 1, 2, 3)
    if ETAPA_ID_1 not in st.session_state.etapas_concluidas:
        st.info("Inicie preenchendo as informações de Apresentação/Objetivos/Introdução (Etapas 1, 2 e 3).")
        render_etapa_1(st.session_state, save_current_state_and_log)
    
    # MÓDULO 4: DOCUMENTOS (Bloco 4 - Etapa 4)
    elif ETAPA_ID_4 not in st.session_state.etapas_concluidas:
        st.info("✅ Dados iniciais concluídos. Avance para a Etapa 4.")
        render_etapa_4(st.session_state, save_current_state_and_log)

    # MÓDULO 5: ANÁLISE PERICIAL (Bloco 5 - Etapa 5)
    elif ETAPA_ID_5 not in st.session_state.etapas_concluidas:
        st.info("✅ Documentos cadastrados. Avance para a Etapa 5.")
        render_etapa_5(st.session_state, save_current_state_and_log)

    # MÓDULO 6: CONCLUSÃO (Bloco 6 - Etapa 6)
    elif ETAPA_ID_6 not in st.session_state.etapas_concluidas:
        st.info("✅ Análise EOG/Confronto concluída. Avance para a Etapa 6.")
        render_etapa_6(st.session_state, save_current_state_and_log)
        
    # MÓDULO 7: RESPOSTA AOS QUESITOS (Bloco 7 - Etapa 7)
    elif ETAPA_ID_7 not in st.session_state.etapas_concluidas:
        st.info("✅ Conclusão finalizada. Avance para a Etapa 7.")
        render_etapa_7(st.session_state, save_current_state_and_log)
        
    # MÓDULO 8: ENCERRAMENTO (Bloco 8 - Etapa 8)
    elif ETAPA_ID_8 not in st.session_state.etapas_concluidas:
        st.info("✅ Respostas aos Quesitos finalizada. Avance para a Etapa 8.")
        # Passa o caminho da raiz do projeto para o m08
        render_etapa_8(st.session_state, save_current_state_and_log, PROJECT_ROOT) 
    
    else:
        # Se todas as etapas foram concluídas, re-renderiza o módulo de encerramento
        st.success("🎉 Todas as etapas concluídas! Você pode baixar o laudo na Etapa 8.")
        render_etapa_8(st.session_state, save_current_state_and_log, PROJECT_ROOT)
        
    st.markdown("---")

    # 3. Área de Geração Final (para salvar a qualquer momento)
    if st.button("💾 Salvar Estado Atual do Processo", key="force_save"):
        if save_current_state():
            st.success("Estado do processo salvo manualmente com sucesso!")
        else:
            st.error("Falha ao salvar o estado do processo.")