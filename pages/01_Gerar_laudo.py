import streamlit as st
from word_handler import gerar_laudo
import os
from datetime import date, datetime 
from num2words import num2words
import json
import shutil 
from typing import List, Dict, Any, Union
import gspread # Necessário para a conexão direta

# --- Configuração Inicial e Tema ---
st.set_page_config(page_title="Laudo Grafotécnico", layout="wide")

DATA_FOLDER = "data"

# --- Inicialização do Estado de Sessão ---
# Inicializa estado de sessão, mantendo a coerência entre as etapas e dados
if "etapas_concluidas" not in st.session_state:
    st.session_state.etapas_concluidas = set()
if "theme" not in st.session_state:
    st.session_state.theme = "light" 
if "editing_etapa_1" not in st.session_state:
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
if "anexos" not in st.session_state:
    st.session_state.anexos = []
if "adendos" not in st.session_state:
    st.session_state.adendos = []
    
# Processos salvos (carregados da nuvem)
if "processos_salvos" not in st.session_state:
    st.session_state.processos_salvos = []

# --- NOVAS FUNÇÕES DE PERSISTÊNCIA (Google Sheets) ---

@st.cache_data(ttl=600) # Cache por 10 minutos para evitar chamadas excessivas
def load_all_process_data():
    """
    CARREGA TODOS OS PROCESSOS DA PLANILHA GOOGLE.
    Retorna uma lista de dicionários.
    """
    try:
        # 1. Autenticação
        secrets = st.secrets["gcp_service_account"]
        gc = gspread.service_account_from_dict(secrets)
        
        # 2. Abrir a planilha
        spreadsheet_url = st.secrets["spreadsheet_url"]
        sh = gc.open_by_url(spreadsheet_url)
        worksheet = sh.worksheet("INDEX") # Assumindo que o nome da aba é INDEX
        
        # 3. Ler todos os registros existentes
        # get_all_records() retorna uma lista de dicionários (melhor para Streamlit)
        all_records = worksheet.get_all_records()
        
        # Garante que 'all_records' seja uma lista para ser usada no selectbox
        if not all_records:
            return []
            
        return all_records
        
    except Exception as e:
        # Se falhar, retorna lista vazia e exibe um aviso discreto
        st.sidebar.warning(f"⚠️ Não foi possível carregar o índice de processos (Sheets): {e}")
        return []

def save_process_data():
    """
    SALVA OS DADOS DO PROCESSO ATUAL NO JSON LOCAL E ATUALIZA A PLANILHA GOOGLE.
    Usa gspread nativo, sem DataFrames.
    """
    
    # 1. Salvar o JSON local (como backup e fonte de dados completa)
    os.makedirs(DATA_FOLDER, exist_ok=True)
    json_filename = os.path.join(DATA_FOLDER, f"{st.session_state.numero_processo}.json")
    
    # Prepara o dicionário de dados completos para o JSON
    dados_completos = {key: value for key, value in st.session_state.items() if key not in ["theme", "processos_salvos", "editing_etapa_1"]}
    
    with open(json_filename, 'w', encoding='utf-8') as f:
        json.dump(dados_completos, f, indent=4, ensure_ascii=False, default=str)
    
    # 2. Atualizar o índice na Planilha Google
    try:
        # 2.1. Autenticação
        secrets = st.secrets["gcp_service_account"]
        gc = gspread.service_account_from_dict(secrets)
        
        # 2.2. Abrir a planilha e a aba INDEX
        spreadsheet_url = st.secrets["spreadsheet_url"]
        sh = gc.open_by_url(spreadsheet_url)
        worksheet = sh.worksheet("INDEX") 
        
        # 2.3. Preparar o registro principal (apenas as colunas A:F)
        data_to_save = {
            "NUMERO_PROCESSO": st.session_state.numero_processo,
            "AUTOR": st.session_state.autor,
            "REU": st.session_state.reu,
            "STATUS": st.session_state.status_processo if 'status_processo' in st.session_state else 'Em Edição',
            "ULTIMA_ATUALIZACAO": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "ARQUIVO_JSON": f"{st.session_state.numero_processo}.json"
        }
        
        # 2.4. Ler todos os registros existentes para encontrar a linha
        all_records = worksheet.get_all_records()
        
        found = False
        for i, record in enumerate(all_records):
            if record["NUMERO_PROCESSO"] == st.session_state.numero_processo:
                # Atualiza a linha existente (i+2 pois a API é 1-baseada e a 1ª linha é o cabeçalho)
                row_index = i + 2 
                row_values = list(data_to_save.values())
                # Atualiza o range A:F
                worksheet.update(f'A{row_index}:F{row_index}', [row_values]) 
                found = True
                break
        
        if not found:
            # Adiciona nova linha
            row_values = list(data_to_save.values())
            worksheet.append_row(row_values)
            
        # 3. Limpa o cache e recarrega a lista de processos salvos
        load_all_process_data.clear()
        st.session_state.processos_salvos = load_all_process_data() 
        st.success("💾 Dados salvos na Planilha Google (Cloud)!")
        
    except Exception as e:
        st.error(f"❌ Erro ao conectar/salvar no Google Sheets: {e}")
        st.info("Verifique se o arquivo `.streamlit/secrets.toml` está correto e se o e-mail da Service Account foi adicionado como Editor na sua planilha.")


# --- FUNÇÕES DE CARREGAMENTO E LIMPEZA ---

def load_process_by_number(process_number: str):
    """Carrega os dados de um processo salvo no estado de sessão."""
    try:
        # Tenta carregar do JSON local (se existir)
        json_filename = os.path.join(DATA_FOLDER, f"{process_number}.json")
        if os.path.exists(json_filename):
            with open(json_filename, 'r', encoding='utf-8') as f:
                dados_carregados = json.load(f)
            
            # Atualiza o estado de sessão com os dados carregados
            for key, value in dados_carregados.items():
                st.session_state[key] = value
                
            # Limpa o "process_to_load" após o carregamento
            st.session_state.process_to_load = None
            st.session_state.editing_etapa_1 = False
            
            # Garante que as etapas estejam marcadas como concluídas se os dados existirem
            st.session_state.etapas_concluidas = set(range(1, 9))
            
            st.success(f"📂 Processo {process_number} carregado com sucesso!")
            st.rerun() # Recarrega a página para atualizar o formulário
        else:
            st.error(f"❌ Arquivo JSON para o processo {process_number} não encontrado localmente.")
            
    except Exception as e:
        st.error(f"❌ Erro ao carregar dados do JSON: {e}")

def clear_current_process():
    """Limpa o estado de sessão para iniciar um novo processo."""
    st.session_state.clear()
    st.session_state.etapas_concluidas = set()
    st.session_state.editing_etapa_1 = True
    st.session_state.num_laudas = 10
    st.session_state.num_docs_questionados = 1
    st.session_state.documentos_questionados_list = []
    st.session_state.quesitos_autor = []
    st.session_state.quesitos_reu = []
    st.session_state.anexos = []
    st.session_state.adendos = []
    # Não limpa o processos_salvos
    st.success("Formulário limpo. Pronto para um novo laudo.")
    st.rerun() # Recarrega a página para refletir o estado limpo

# --- FUNÇÕES DE FORMATAÇÃO E UTILIDADE ---

def format_quesitos(quesitos_list: List[Dict[str, Any]]):
    """Formata a lista de quesitos para o bloco de texto do Laudo."""
    if not quesitos_list:
        return ""
    
    # Criar um cabeçalho fixo no formato CSV (usado pelo word_handler)
    output = "Nº,Quesito,Resposta do Perito\r\n"
    
    for item in quesitos_list:
        # A API de substituição do DOCX requer quebras de linha específicas
        # Usamos o 'strip()' para remover espaços extras e garantir que a string esteja limpa.
        numero = item.get("id", "")
        quesito = item.get("quesito", "").replace('\n', ' ').strip()
        resposta = item.get("resposta", "").replace('\n', ' ').strip()
        
        # Garante que as strings não contenham vírgulas que quebrem a estrutura CSV, se possível
        quesito = quesito.replace(',', ';')
        resposta = resposta.replace(',', ';')
        
        output += f"{numero},\"{quesito}\",\"{resposta}\"\r\n"
        
    return output

def list_to_text(data_list: List[Dict[str, Any]], key: str):
    """Converte uma lista de dicionários em texto simples, usando uma chave específica."""
    return "\n".join([item.get(key, '') for item in data_list])

# --- SIDEBAR (CARREGAMENTO DE PROCESSOS) ---

st.sidebar.title("Gerenciar Processos")

# Carregar lista de processos salvos na inicialização
if not st.session_state.processos_salvos:
    st.session_state.processos_salvos = load_all_process_data()

# 1. Carregar Processo Existente
if st.session_state.processos_salvos:
    # Cria uma lista de opções formatadas: "NÚMERO - AUTOR/RÉU"
    options = [""] + [
        f"{p['NUMERO_PROCESSO']} - {p['AUTOR']}/{p['REU']}"
        for p in st.session_state.processos_salvos
    ]
    
    st.session_state.process_to_load = st.sidebar.selectbox(
        "Selecione um processo para carregar:",
        options=options,
        index=0
    )
    
    if st.sidebar.button("Carregar Processo", disabled=(not st.session_state.process_to_load)):
        process_number = st.session_state.process_to_load.split(" - ")[0].strip()
        load_process_by_number(process_number)

# 2. Botão Limpar
st.sidebar.button("Limpar Processo Atual", on_click=clear_current_process)

# --- TÍTULO PRINCIPAL ---
st.title("👨‍🔬 Gerador de Laudo Pericial Grafotécnico")

# --- ETAPA 1: DADOS BÁSICOS DO PROCESSO ---

with st.expander("1. Dados do Processo e Objeto da Perícia", expanded=st.session_state.editing_etapa_1):
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.session_state.numero_processo = st.text_input(
            "Número do Processo", 
            value=st.session_state.get("numero_processo", ""),
            disabled=not st.session_state.editing_etapa_1
        )
    with col2:
        st.session_state.autor = st.text_input(
            "Autor", 
            value=st.session_state.get("autor", ""),
            disabled=not st.session_state.editing_etapa_1
        )
    with col3:
        st.session_state.reu = st.text_input(
            "Réu", 
            value=st.session_state.get("reu", ""),
            disabled=not st.session_state.editing_etapa_1
        )
        
    st.session_state.status_processo = st.selectbox(
        "Status do Processo",
        options=["Em Edição", "Pronto para Conclusão", "Finalizado"],
        index=["Em Edição", "Pronto para Conclusão", "Finalizado"].index(st.session_state.get("status_processo", "Em Edição"))
    )
        
    st.session_state.objeto_pericia = st.text_area(
        "Objeto da Perícia (resumo)",
        value=st.session_state.get("objeto_pericia", "Verificar a autenticidade ou falsidade de assinaturas atribuídas ao(a) [NOME DO AUTOR], aposta no(s) documento(s) [LISTA DE DOCUMENTOS QUESTIONADOS]."),
        height=100
    )
    
    st.session_state.data_laudo = st.date_input(
        "Data de Encerramento/Entrega do Laudo", 
        value=st.session_state.get("data_laudo", date.today())
    )
    
    # ----------------------------------------------------------------------------------------------------------------------------------
    # Botão de Conclusão da Etapa 1
    if st.button("Concluir Etapa 1 e Salvar", disabled=not st.session_state.get("numero_processo")):
        if st.session_state.numero_processo and st.session_state.autor and st.session_state.reu:
            st.session_state.etapas_concluidas.add(1)
            st.session_state.editing_etapa_1 = False
            save_process_data() # Chama a função de salvamento na nuvem
            st.rerun()
        else:
            st.error("Preencha o Número do Processo, Autor e Réu para continuar.")
# --------------------------------------------------------------------------------------------------------------------------------------


# Variável para habilitar as próximas etapas
enable_next_steps = 1 in st.session_state.etapas_concluidas

# --- ETAPA 2: LISTA DE AUTORES E RÉUS (se houver mais de um) ---

with st.expander("2. Partes do Processo (Lista)", expanded=enable_next_steps and 2 not in st.session_state.etapas_concluidas):
    
    st.session_state.autores_list = st.text_area(
        "Lista de Autores (um por linha)",
        value=st.session_state.get("autores_list", st.session_state.get("autor", "")),
        help="Use uma linha por nome. O primeiro será usado como nome principal. Este campo alimenta o placeholder [AUTORES]."
    )
    st.session_state.reus_list = st.text_area(
        "Lista de Réus (um por linha)",
        value=st.session_state.get("reus_list", st.session_state.get("reu", "")),
        help="Use uma linha por nome. O primeiro será usado como nome principal. Este campo alimenta o placeholder [REUS]."
    )
    
    if st.button("Concluir Etapa 2"):
        st.session_state.etapas_concluidas.add(2)
        save_process_data()
        st.rerun()


# --- ETAPA 3: DOCUMENTOS QUESTIONADOS (PQ) ---

with st.expander("3. Documentos Questionados (PQ)", expanded=enable_next_steps and 3 not in st.session_state.etapas_concluidas):
    
    # Gerencia a lista de documentos questionados no session_state
    
    st.session_state.num_docs_questionados = st.number_input(
        "Quantos documentos questionados (PQ)?",
        min_value=1,
        value=st.session_state.get("num_docs_questionados", 1)
    )
    
    # Garante que a lista tenha o tamanho correto
    while len(st.session_state.documentos_questionados_list) < st.session_state.num_docs_questionados:
        st.session_state.documentos_questionados_list.append({
            "TIPO_DOCUMENTO": "", 
            "FLS_DOCUMENTOS": "", 
            "RESULTADO": "Autêntico" # Valor padrão
        })
    while len(st.session_state.documentos_questionados_list) > st.session_state.num_docs_questionados:
        st.session_state.documentos_questionados_list.pop()
        
    st.session_state.docs_questionados_text = ""
    docs_text_list = []
    
    for i in range(st.session_state.num_docs_questionados):
        st.markdown(f"**Documento Questionado #{i+1}**")
        colA, colB, colC = st.columns([2, 1, 2])
        
        with colA:
            st.session_state.documentos_questionados_list[i]["TIPO_DOCUMENTO"] = st.text_input(
                "Tipo/Nome do Documento",
                value=st.session_state.documentos_questionados_list[i]["TIPO_DOCUMENTO"],
                key=f"pq_tipo_{i}"
            )
        with colB:
            st.session_state.documentos_questionados_list[i]["FLS_DOCUMENTOS"] = st.text_input(
                "Fls.",
                value=st.session_state.documentos_questionados_list[i]["FLS_DOCUMENTOS"],
                key=f"pq_fls_{i}"
            )
        with colC:
            st.session_state.documentos_questionados_list[i]["RESULTADO"] = st.selectbox(
                "Conclusão (para placeholder)",
                options=["Autêntico", "Falso", "Não Conclusivo"],
                index=["Autêntico", "Falso", "Não Conclusivo"].index(st.session_state.documentos_questionados_list[i]["RESULTADO"]),
                key=f"pq_res_{i}"
            )
            
        docs_text_list.append(f"{st.session_state.documentos_questionados_list[i]['TIPO_DOCUMENTO']} - Fls. {st.session_state.documentos_questionados_list[i]['FLS_DOCUMENTOS']}")

    # Cria o texto final para substituição no laudo (placeholder [DOCUMENTOS_QUESTIONADOS_LIST])
    st.session_state.docs_questionados_text = "\n".join(docs_text_list)
    
    if st.button("Concluir Etapa 3"):
        st.session_state.etapas_concluidas.add(3)
        save_process_data()
        st.rerun()


# --- ETAPA 4: PADRÕES DE CONFRONTO (PC) ---

with st.expander("4. Padrões de Confronto (PC)", expanded=enable_next_steps and 4 not in st.session_state.etapas_concluidas):
    
    st.session_state.num_especimes = st.text_input(
        "Número de espécimes (documentos) examinados:",
        value=st.session_state.get("num_especimes", "5")
    )
    
    st.session_state.fls_pc_a = st.text_input(
        "Fls. dos Padrões Colhidos no Ato Pericial (PCA)",
        value=st.session_state.get("fls_pc_a", "N/A - Assinaturas padrão colhidas em cartório.")
    )
    
    st.session_state.fls_pc_e = st.text_input(
        "Fls. dos Padrões Encontrados nos Autos (PCE)",
        value=st.session_state.get("fls_pc_e", "Ex: 20-25, 30-35")
    )
    
    st.session_state.analise_paradigmas = st.text_area(
        "5.1. Análise dos Paradigmas (Texto)",
        value=st.session_state.get("analise_paradigmas", "A análise dos padrões (PC) demonstrou que [O QUE FOI OBSERVADO - ex: as assinaturas são coesas, não há vestígios de simulação, etc.]"),
        height=150
    )
    
    if st.button("Concluir Etapa 4"):
        st.session_state.etapas_concluidas.add(4)
        save_process_data()
        st.rerun()


# --- ETAPA 5: ANÁLISE E CONCLUSÃO ---

with st.expander("5. Confronto Grafoscópico e Conclusão", expanded=enable_next_steps and 5 not in st.session_state.etapas_concluidas):
    
    st.session_state.confronto_grafoscopico = st.text_area(
        "5.2. Confronto Grafoscópico (Texto completo da análise)",
        value=st.session_state.get("confronto_grafoscopico", "O exame comparativo entre os espécimes questionados (PQ) e os padrões (PC) revelou [DESCREVER as convergências/divergências encontradas]."),
        height=300
    )
    
    st.session_state.resultado_final = st.selectbox(
        "6. Conclusão Principal",
        options=["AUTÊNTICA", "FALSA", "NÃO CONCLUSIVA"],
        index=["AUTÊNTICA", "FALSA", "NÃO CONCLUSIVA"].index(st.session_state.get("resultado_final", "AUTÊNTICA"))
    )
    
    st.session_state.conclusao_texto = st.text_area(
        "6. Conclusão (Texto completo - ajuste o placeholder)",
        value=st.session_state.get("conclusao_texto", "Com base nos exames realizados, conclui-se que a(s) assinatura(s) atribuída(s) ao(a) [NOME DO AUTOR], aposta(s) no(s) documento(s) questionado(s), é/são [RESULTADO_FINAL]."),
        height=150
    )
    
    if st.button("Concluir Etapa 5"):
        st.session_state.etapas_concluidas.add(5)
        save_process_data()
        st.rerun()


# --- ETAPA 6: QUESITOS (TABELAS) ---

with st.expander("6. Resposta aos Quesitos (Autor e Réu)", expanded=enable_next_steps and 6 not in st.session_state.etapas_concluidas):
    
    # ----------------------------------------------------------------------------------------------------------------------------------
    st.subheader("Quesitos da Parte Autora")
    st.session_state.fls_quesitos_autor = st.text_input(
        "Fls. dos Quesitos do Autor",
        value=st.session_state.get("fls_quesitos_autor", "")
    )
    
    num_quesitos_autor = st.number_input("Número de Quesitos do Autor:", min_value=0, value=len(st.session_state.quesitos_autor), key="num_q_autor")
    
    # Ajusta o tamanho da lista
    while len(st.session_state.quesitos_autor) < num_quesitos_autor:
        st.session_state.quesitos_autor.append({"id": len(st.session_state.quesitos_autor) + 1, "quesito": "", "resposta": "", "imagem_obj": None})
    while len(st.session_state.quesitos_autor) > num_quesitos_autor:
        st.session_state.quesitos_autor.pop()
        
    for i, item in enumerate(st.session_state.quesitos_autor):
        st.markdown(f"**Quesito Autor #{i+1}**")
        st.session_state.quesitos_autor[i]["id"] = i + 1
        
        colQ, colR = st.columns([1, 1])
        with colQ:
            st.session_state.quesitos_autor[i]["quesito"] = st.text_area(
                "Quesito (Transcrever)",
                value=item["quesito"],
                key=f"qa_quesito_{i}",
                height=70
            )
        with colR:
            st.session_state.quesitos_autor[i]["resposta"] = st.text_area(
                "Resposta do Perito",
                value=item["resposta"],
                key=f"qa_resposta_{i}",
                height=70
            )
        
        # Campo para upload de imagem
        st.session_state.quesitos_autor[i]["imagem_obj"] = st.file_uploader(
            "Upload de Imagem para a Seção IX (Opcional)",
            type=["png", "jpg", "jpeg"],
            key=f"qa_img_{i}"
        )
        
    # ----------------------------------------------------------------------------------------------------------------------------------
    st.subheader("Quesitos da Parte Ré")
    st.session_state.fls_quesitos_reu = st.text_input(
        "Fls. dos Quesitos do Réu",
        value=st.session_state.get("fls_quesitos_reu", "")
    )
    
    num_quesitos_reu = st.number_input("Número de Quesitos do Réu:", min_value=0, value=len(st.session_state.quesitos_reu), key="num_q_reu")
    
    # Ajusta o tamanho da lista
    while len(st.session_state.quesitos_reu) < num_quesitos_reu:
        st.session_state.quesitos_reu.append({"id": len(st.session_state.quesitos_reu) + 1, "quesito": "", "resposta": "", "imagem_obj": None})
    while len(st.session_state.quesitos_reu) > num_quesitos_reu:
        st.session_state.quesitos_reu.pop()
        
    for i, item in enumerate(st.session_state.quesitos_reu):
        st.markdown(f"**Quesito Réu #{i+1}**")
        st.session_state.quesitos_reu[i]["id"] = i + 1
        
        colQ, colR = st.columns([1, 1])
        with colQ:
            st.session_state.quesitos_reu[i]["quesito"] = st.text_area(
                "Quesito (Transcrever)",
                value=item["quesito"],
                key=f"qr_quesito_{i}",
                height=70
            )
        with colR:
            st.session_state.quesitos_reu[i]["resposta"] = st.text_area(
                "Resposta do Perito",
                value=item["resposta"],
                key=f"qr_resposta_{i}",
                height=70
            )
            
        # Campo para upload de imagem
        st.session_state.quesitos_reu[i]["imagem_obj"] = st.file_uploader(
            "Upload de Imagem para a Seção IX (Opcional)",
            type=["png", "jpg", "jpeg"],
            key=f"qr_img_{i}"
        )

    if st.button("Concluir Etapa 6"):
        st.session_state.etapas_concluidas.add(6)
        save_process_data()
        st.rerun()


# --- ETAPA 7: ANEXOS E ADENDOS (Imagens/Documentos) ---

with st.expander("7. Anexos e Adendos (Imagens e Documentos)", expanded=enable_next_steps and 7 not in st.session_state.etapas_concluidas):
    
    st.session_state.anexos_list = st.text_area(
        "X. ANEXOS (Descreva documentos/arquivos de texto que não são imagens)",
        value=st.session_state.get("anexos_list", "Certidão de Nascimento, RG, CPF."),
        help="Esta lista alimenta o placeholder [ANEXOS_LIST] no laudo. Anexos de imagem são adicionados abaixo."
    )
    
    st.subheader("X. ANEXOS (Imagens/Arquivos para inclusão)")
    uploaded_anexos = st.file_uploader("Upload de arquivos para Anexos (Imagens/Arquivos)", type=["png", "jpg", "jpeg", "pdf", "docx"], accept_multiple_files=True)

    # Lógica de atualização de anexos com persistência de descrição
    if uploaded_anexos:
        st.session_state.anexos = []
        for i, uploaded_file in enumerate(uploaded_anexos):
            # Tenta encontrar a descrição existente para o arquivo
            existing_desc = next((item["DESCRICAO"] for item in st.session_state.anexos if item.get("NOME") == uploaded_file.name), f"Descrição do Anexo {i+1}")
            
            # Adiciona o arquivo com placeholder para a descrição
            st.session_state.anexos.append({
                "NOME": uploaded_file.name,
                "ARQUIVO": uploaded_file,
                "DESCRICAO": st.text_input(f"Descrição para {uploaded_file.name}", value=existing_desc, key=f"anexo_desc_{i}")
            })
    else:
        st.session_state.anexos = []

    st.subheader("XI. ADENDOS (Imagens/Gráficos)")
    uploaded_adendos = st.file_uploader("Upload de Imagens/Gráficos para Adendos", type=["png", "jpg", "jpeg"], accept_multiple_files=True)
    
    # Lógica de atualização de adendos com persistência de descrição
    if uploaded_adendos:
        st.session_state.adendos = []
        for i, uploaded_file in enumerate(uploaded_adendos):
            existing_desc = next((item["DESCRICAO"] for item in st.session_state.adendos if item.get("NOME") == uploaded_file.name), f"Descrição do Adendo {i+1}")
            
            st.session_state.adendos.append({
                "NOME": uploaded_file.name,
                "ARQUIVO": uploaded_file,
                "DESCRICAO": st.text_input(f"Descrição para {uploaded_file.name}", value=existing_desc, key=f"adendo_desc_{i}")
            })
    else:
        st.session_state.adendos = []
        
    if st.button("Concluir Etapa 7"):
        st.session_state.etapas_concluidas.add(7)
        save_process_data()
        st.rerun()


# --- ETAPA 8: GERAÇÃO E ENCERRAMENTO ---

with st.expander("8. Encerramento e Geração do Laudo", expanded=enable_next_steps and 8 not in st.session_state.etapas_concluidas):
    
    st.session_state.num_laudas = st.number_input(
        "Número final de laudas:",
        min_value=1,
        value=st.session_state.get("num_laudas", 10),
        help="Este valor será usado para o placeholder [NUM_LAUDAS] e [NUM_LAUDAS_EXTENSO]."
    )
    
    st.session_state.assinaturas = st.text_area(
        "Assinaturas/Perito (Placeholder [ASSINATURAS])",
        value=st.session_state.get("assinaturas", "Carlos Menezes\nPerito Grafotécnico"),
        height=100
    )
    
    st.session_state.caminho_modelo = st.text_input(
        "Caminho do Arquivo Modelo (.docx):",
        value=st.session_state.get("caminho_modelo", "LAUDO PERICIAL GRAFOTÉCNICO.docx"),
        help="Deve ser o nome do arquivo DOCX que está na raiz do seu repositório."
    )
    
    if st.button("Gerar Laudo e Baixar Documento", disabled=not st.session_state.get("numero_processo")):
        
        # 1. Agrega todos os dados
        
        # Prepara a lista de anexos e adendos para os placeholders de texto
        anexos_text_list = [f"{i+1}. {a['DESCRICAO']}" for i, a in enumerate(st.session_state.anexos)]
        adendos_text_list = [f"{i+1}. {a['DESCRICAO']}" for i, a in enumerate(st.session_state.adendos)]
        
        # Formata o texto dos quesitos para a tabela
        bloco_quesitos_autor_final = format_quesitos(st.session_state.quesitos_autor)
        bloco_quesitos_reu_final = format_quesitos(st.session_state.quesitos_reu)
        
        # Prepara a lista de imagens para a seção IX (quesitos)
        quesito_images_list = []
        for q_autor in st.session_state.quesitos_autor:
            if q_autor["imagem_obj"]:
                quesito_images_list.append({
                    "id": f"Autor {q_autor['id']}", 
                    "file_obj": q_autor["imagem_obj"], 
                    "description": f"Demonstração do Quesito nº {q_autor['id']} do Autor."
                })
        for q_reu in st.session_state.quesitos_reu:
            if q_reu["imagem_obj"]:
                quesito_images_list.append({
                    "id": f"Réu {q_reu['id']}", 
                    "file_obj": q_reu["imagem_obj"], 
                    "description": f"Demonstração do Quesito nº {q_reu['id']} do Réu."
                })
                
        # Dicionário final para substituição no DOCX
        dados = dict(
            # Etapa 1
            NUMERO_DO_PROCESSO=st.session_state.numero_processo,
            NOME_DO_AUTOR=st.session_state.autor,
            NOME_DO_REU=st.session_state.reu,
            OBJETO_DA_PERICIA=st.session_state.objeto_pericia,
            DATA_LAUDO=st.session_state.data_laudo.strftime("%d de %B de %Y").replace(" 0", " "),
            
            # Etapa 2
            AUTORES=st.session_state.autores_list,
            REUS=st.session_state.reus_list,
            
            # Etapa 3
            DOCUMENTOS_QUESTIONADOS_LIST=st.session_state.docs_questionados_text,
            
            # Etapa 4
            NUM_ESPECIMES=st.session_state.num_especimes,
            NUM_ESPECIMES_EXTENSO=num2words(int(st.session_state.num_especimes), lang='pt_BR').upper(), # Requer que seja dígito
            FLS_PCA=st.session_state.fls_pc_a,
            FLS_PCE=st.session_state.fls_pc_e,
            ANALISE_PARADIGMAS=st.session_state.analise_paradigmas,
            
            # Etapa 5
            CONFRONTO_GRAFOSCOPICO=st.session_state.confronto_grafoscopico,
            RESULTADO_FINAL=st.session_state.resultado_final,
            CONCLUSAO_TEXTO=st.session_state.conclusao_texto,
            
            # Etapa 6
            FLS_QUESITOS_AUTOR=st.session_state.fls_quesitos_autor,
            FLS_QUESITOS_REU=st.session_state.fls_quesitos_reu,
            BLOCO_QUESITOS_AUTOR=bloco_quesitos_autor_final,
            BLOCO_QUESITOS_REU=bloco_quesitos_reu_final,
            
            # Etapa 7
            ANEXOS_LIST=st.session_state.anexos_list,
            ADENDOS_LIST="\n".join(adendos_text_list),
            
            # Etapa 8 (Encerramento)
            NUM_LAUDAS=str(st.session_state.num_laudas),
            NUM_LAUDAS_EXTENSO=num2words(st.session_state.num_laudas, lang='pt_BR').upper(),
            ASSINATURAS=st.session_state.assinaturas
        )
        
        # 2. Geração do Laudo
        caminho_modelo = st.session_state.caminho_modelo
        nome_arquivo_saida = os.path.join("output", f"LAUDO_{st.session_state.numero_processo}.docx")
        
        try:
            os.makedirs("output", exist_ok=True)
            
            # Garante que os dados mais recentes estejam no JSON (também salva na nuvem)
            save_process_data()
            
            # Chamada da função gerar_laudo com os 6 argumentos
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
            st.error(f"❌ Erro ao gerar o laudo: {e}")
            st.warning("Verifique se o arquivo modelo DOCX existe e se o código `utils/word_handler.py` está atualizado para receber 6 argumentos.")