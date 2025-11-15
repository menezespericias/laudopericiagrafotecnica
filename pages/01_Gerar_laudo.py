import streamlit as st
import os
import json
from datetime import date, datetime
from num2words import num2words
from typing import List, Dict, Any, Union
# Assumindo que word_handler.py, data_handler.py e db_handler.py estão no mesmo nível
# ou foram importados corretamente via PYTHONPATH
from word_handler import gerar_laudo
from data_handler import save_process_data, load_process_data
from db_handler import atualizar_status

# --- Configuração Inicial ---
st.set_page_config(page_title="Laudo Grafotécnico", layout="wide")

# Correção do erro PackageNotFoundError: Garante o caminho absoluto para o modelo
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
    """
    Callback para forçar que a data salva no session_state (key_data)
    seja sempre uma STRING no formato DD/MM/YYYY, usando o valor do widget (key_input).
    """
    try:
        # Pega o objeto date retornado pelo widget st.date_input
        date_object = st.session_state[key_input]
        
        # Converte o objeto date para a string no formato desejado
        if isinstance(date_object, date):
            st.session_state[key_data] = date_object.strftime("%d/%m/%Y")
        elif isinstance(date_object, (list, tuple)) and date_object and isinstance(date_object[0], date):
            st.session_state[key_data] = date_object[0].strftime("%d/%m/%Y")
            
    except KeyError:
        pass

def update_laudo_date():
    """Callback para a data de conclusão do laudo."""
    update_session_date_format("DATA_LAUDO", "input_data_laudo")

def update_vencimento_date():
    """Callback para a data de vencimento dos honorários."""
    update_session_date_format("HONORARIOS_VENCIMENTO", "input_data_vencimento")


# --- Funções Auxiliares (Sanitização Máxima de Data) ---

def get_date_object_from_state(key: str) -> date:
    """
    Sanitização Máxima: Extrai e valida o valor de data do session_state, 
    forçando-o a ser um único objeto date, tratando listas de strings, strings e objetos date.
    """
    data_val = st.session_state.get(key)

    # 1. TRATAMENTO DE LISTA/TUPLA (A causa do TypeError)
    if isinstance(data_val, (list, tuple)) and data_val:
        # Pega o primeiro item, que deve ser a string ou o objeto date
        data_val = data_val[0]

    # 2. Tenta converter STRING ("DD/MM/YYYY" ou "YYYY-MM-DD" do JSON) para objeto date
    if isinstance(data_val, str) and data_val:
        data_str = data_val.strip()
        
        # Tenta formato DD/MM/YYYY
        try:
            return datetime.strptime(data_str, "%d/%m/%Y").date()
        except:
            pass 
        
        # Tenta formato YYYY-MM-DD (Comum em serialização Streamlit)
        try:
            return datetime.strptime(data_str, "%Y-%m-%d").date()
        except:
            pass

    # 3. Se já for um objeto date válido, retorna
    elif isinstance(data_val, date):
        return data_val

    # 4. Fallback (data atual)
    return date.today()

def init_session_state():
    """Inicializa as chaves do session_state que não existem."""
    if 'editing_etapa_1' not in st.session_state:
        st.session_state.editing_etapa_1 = True

    # Garante que etapas_concluidas seja sempre um SET.
    if 'etapas_concluidas' not in st.session_state:
        st.session_state.etapas_concluidas = set()
    elif not isinstance(st.session_state.etapas_concluidas, set):
        try:
            st.session_state.etapas_concluidas = set(st.session_state.etapas_concluidas)
        except:
            st.session_state.etapas_concluidas = set()

    # Outros campos do laudo
    campos_base = [
        "JUIZO", "VARA", "COMARCA", "DATA_LAUDO", "PERITO", "ESPECIALIZACAO",
        "DATA_NOMEACAO", "LIVRO", "FLS_Q_AUTOR", "FLS_Q_REU", 
        "NUM_EXAMES", "NUM_QUESITOS", "NUM_PECA_AUTENTICIDADE", "NUM_PECA_QUESTIONADA",
        "CONCLUSION", "HONORARIOS_VALOR", "HONORARIOS_VENCIMENTO",
        "METODOLOGIA_TEXTO", "CORPUS_CONFRONTO_TEXTO", "ANALISE_TEXTO", "status_db",
        "numero_processo", "autor", "reu", "quesitos_autor", "quesitos_reu", "anexos", "adendos"
    ]
    for campo in campos_base:
        if campo not in st.session_state:
            # Inicialização segura
            if campo in ["DATA_LAUDO", "HONORARIOS_VENCIMENTO"]:
                st.session_state[campo] = date.today().strftime("%d/%m/%Y")
            elif campo in ["quesitos_autor", "quesitos_reu", "anexos", "adendos"]:
                st.session_state[campo] = []
            else:
                st.session_state[campo] = ""

def save_current_state():
    """Chama a função de salvar do data_handler e atualiza o estado."""
    if st.session_state.numero_processo:
        process_id = st.session_state.numero_processo
        
        try:
            # 1. Garante que as datas nos inputs foram salvas no session_state como strings antes de salvar o JSON
            update_laudo_date()
            update_vencimento_date()
            
            # 2. Salva os dados no JSON
            # st.session_state é serializável porque as datas foram forçadas a ser strings.
            # Os objetos de imagem (UploadedFile) são ignorados pelo JSON, mas podem ser 
            # mantidos no state para a função de geração.
            save_process_data(process_id, st.session_state) 
            
            # 3. ATUALIZA o status no banco de dados SQLite
            NOVO_STATUS = "Em andamento"
            atualizar_status(process_id, NOVO_STATUS)
            
            st.session_state.status_db = NOVO_STATUS 
            
            if isinstance(st.session_state.etapas_concluidas, set):
                st.session_state.etapas_concluidas.add(1)
            
            st.toast(f"✅ Dados do Processo {process_id} salvos e status atualizado para '{NOVO_STATUS}'.")
            return True
            
        except Exception as e:
            st.error(f"Erro inesperado ao salvar: {e}")
            return False
    else:
        st.error("Erro: Número do Processo não definido para salvar.")
        return False

def add_list_item(key: str, item_data: dict, list_key: str = None):
    """Adiciona um item a uma lista em st.session_state, garantindo a chave."""
    final_key = list_key if list_key else key
    if final_key not in st.session_state:
        st.session_state[final_key] = []
    
    item_data['id'] = len(st.session_state[final_key]) + 1
    st.session_state[final_key].append(item_data)
    st.rerun()

def remove_list_item(list_key: str, item_id: int):
    """Remove um item da lista em st.session_state pelo ID."""
    if list_key in st.session_state:
        st.session_state[list_key] = [item for item in st.session_state[list_key] if item.get('id') != item_id]
        for i, item in enumerate(st.session_state[list_key]):
            item['id'] = i + 1
        st.rerun()


# --- Carregamento automático do processo selecionado ---
if "process_to_load" in st.session_state and st.session_state["process_to_load"]:
    process_id = st.session_state["process_to_load"]
    
    try:
        dados_carregados = load_process_data(process_id)
        
        # Carrega os dados para o session_state
        for key, value in dados_carregados.items():
            st.session_state[key] = value

        st.success(f"📂 Processo **{process_id}** carregado com sucesso!")
        
        st.session_state.process_to_load = None 
        st.session_state.editing_etapa_1 = True
        
        # Garante a coerção de tipo de 'etapas_concluidas' após o carregamento
        init_session_state() 
        
    except FileNotFoundError:
        st.error(f"❌ Arquivo JSON para o processo {process_id} não encontrado. Por favor, volte e tente recriá-lo.")
        st.session_state.process_to_load = None
        
    except Exception as e:
        st.error(f"❌ Erro ao carregar o arquivo JSON do processo {process_id}: {e}")
        st.session_state.process_to_load = None
        

# --- Inicialização do Estado de Sessão ---
init_session_state()

# --- VERIFICAÇÃO PRINCIPAL DE NAVEGAÇÃO ---
if "numero_processo" not in st.session_state or not st.session_state.numero_processo:
    st.warning("Nenhum processo selecionado ou carregado. Por favor, volte à página inicial para selecionar ou criar um processo.")
    
    if st.button("🏠 Voltar para Home"):
        st.switch_page("home.py")
        
    st.stop()

# --- TÍTULO PRINCIPAL ---
st.title(f"👨‍🔬 Laudo Pericial: {st.session_state.numero_processo}")

if st.button("🏠 Voltar para Home"):
    st.switch_page("home.py")

st.markdown("---")

# --- ETAPA 1: DADOS BÁSICOS DO PROCESSO ---
with st.expander(f"1. Dados Básicos do Processo - {st.session_state.numero_processo}", expanded=st.session_state.editing_etapa_1):
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.session_state.numero_processo = st.text_input("Número do Processo", value=st.session_state.numero_processo, key="input_numero_processo", disabled=True)
        st.session_state.JUIZO = st.text_input("Juízo (Ex: MM. Juiz de Direito da)", value=st.session_state.get("JUIZO", ""))
        st.session_state.COMARCA = st.text_input("Comarca", value=st.session_state.get("COMARCA", ""))
    
    with col2:
        st.session_state.autor = st.text_area("Autor(es) (Um por linha)", value=st.session_state.get("autor", ""))
        st.session_state.reu = st.text_area("Réu(s) (Um por linha)", value=st.session_state.get("reu", ""))

    with col3:
        # PONTO CRÍTICO CORRIGIDO: Usa a função de sanitização máxima para o valor
        data_obj = get_date_object_from_state("DATA_LAUDO")
            
        st.date_input(
            "Data da Conclusão do Laudo", 
            value=data_obj, 
            key="input_data_laudo",
            # Defesa na Escrita: Força o salvamento como string assim que o valor muda.
            on_change=update_laudo_date
        )
        
        st.session_state.PERITO = st.text_input("Nome do Perito", value=st.session_state.get("PERITO", ""))
        st.session_state.ESPECIALIZACAO = st.text_input("Especialização (Ex: Grafotécnico)", value=st.session_state.get("ESPECIALIZACAO", ""))
        
    if st.button("💾 Salvar Dados Básicos (Etapa 1)"):
        if save_current_state():
            st.session_state.editing_etapa_1 = False
            st.rerun()

st.markdown("---")

# --- ETAPA 2: PEÇAS E QUESITOS ---
with st.expander("2. Peças e Quesitos"):
    
    # Formulário para adicionar Quesitos do Autor
    with st.form("form_quesitos_autor"):
        st.subheader("Quesitos do Autor")
        novo_quesito_autor = st.text_area("Texto do Quesito")
        imagem_quesito_autor = st.file_uploader("Imagem do Quesito (Opcional)", type=['png', 'jpg', 'jpeg'], key="upload_quesito_autor")
        
        if st.form_submit_button("➕ Adicionar Quesito do Autor"):
            if novo_quesito_autor:
                item_data = {
                    "texto": novo_quesito_autor,
                    "imagem_obj": imagem_quesito_autor
                }
                add_list_item("quesitos_autor", item_data)
            else:
                st.error("O campo 'Texto do Quesito' é obrigatório.")
    
    # Visualização e remoção de Quesitos do Autor
    if st.session_state.quesitos_autor:
        st.markdown("**Quesitos do Autor Adicionados:**")
        for q in st.session_state.quesitos_autor:
            col_q1, col_q2 = st.columns([4, 1])
            col_q1.write(f"**Quesito {q['id']}:** {q['texto']}")
            # Não exibe a imagem aqui para evitar recargas excessivas, mas garante o botão de remover
            if col_q2.button("🗑️ Remover", key=f"del_quesito_autor_{q['id']}"):
                remove_list_item("quesitos_autor", q['id'])
    
    st.markdown("---")
    
    # Formulário para adicionar Quesitos do Réu
    with st.form("form_quesitos_reu"):
        st.subheader("Quesitos do Réu")
        novo_quesito_reu = st.text_area("Texto do Quesito", key="input_quesito_reu")
        imagem_quesito_reu = st.file_uploader("Imagem do Quesito (Opcional)", type=['png', 'jpg', 'jpeg'], key="upload_quesito_reu")

        if st.form_submit_button("➕ Adicionar Quesito do Réu"):
            if novo_quesito_reu:
                item_data = {
                    "texto": novo_quesito_reu,
                    "imagem_obj": imagem_quesito_reu
                }
                add_list_item("quesitos_reu", item_data)
            else:
                st.error("O campo 'Texto do Quesito' é obrigatório.")

    # Visualização e remoção de Quesitos do Réu
    if st.session_state.quesitos_reu:
        st.markdown("**Quesitos do Réu Adicionados:**")
        for q in st.session_state.quesitos_reu:
            col_q1, col_q2 = st.columns([4, 1])
            col_q1.write(f"**Quesito {q['id']}:** {q['texto']}")
            if col_q2.button("🗑️ Remover", key=f"del_quesito_reu_{q['id']}"):
                remove_list_item("quesitos_reu", q['id'])
    
    if isinstance(st.session_state.etapas_concluidas, set):
        st.session_state.etapas_concluidas.add(2)

st.markdown("---")

# --- ETAPA 3: DOCUMENTOS ANEXADOS ---
with st.expander("3. Peças de Exame e Documentos Anexados"):
    
    col_pecas, col_docs = st.columns([1, 2])
    
    with col_pecas:
        st.subheader("Peças de Exame")
        st.session_state.NUM_PECA_AUTENTICIDADE = st.text_input("Nº de Peças de Autenticidade", value=st.session_state.get("NUM_PECA_AUTENTICIDADE", ""))
        st.session_state.NUM_PECA_QUESTIONADA = st.text_input("Nº de Peças Questionadas", value=st.session_state.get("NUM_PECA_QUESTIONADA", ""))
        st.session_state.NUM_EXAMES = st.text_input("Nº de Exames Realizados", value=st.session_state.get("NUM_EXAMES", ""))

    with col_docs:
        # Formulário para adicionar Anexos
        with st.form("form_anexos"):
            st.subheader("Documentos Anexados (Anexo A)")
            novo_anexo_descricao = st.text_input("Descrição do Documento Anexado")
            imagem_anexo = st.file_uploader("Imagem do Anexo", type=['png', 'jpg', 'jpeg'], key="upload_anexo")
            
            if st.form_submit_button("➕ Adicionar Anexo"):
                if novo_anexo_descricao and imagem_anexo:
                    item_data = {
                        "descricao": novo_anexo_descricao,
                        "imagem_obj": imagem_anexo
                    }
                    add_list_item("anexos", item_data)
                else:
                    st.error("A descrição e a imagem são obrigatórias para o Anexo.")

        # Visualização e remoção de Anexos
        if st.session_state.anexos:
            st.markdown("**Anexos Adicionados:**")
            for a in st.session_state.anexos:
                col_a1, col_a2 = st.columns([4, 1])
                col_a1.write(f"**Anexo {a['id']}:** {a['descricao']}")
                if col_a2.button("🗑️ Remover", key=f"del_anexo_{a['id']}"):
                    remove_list_item("anexos", a['id'])

    if isinstance(st.session_state.etapas_concluidas, set):
        st.session_state.etapas_concluidas.add(3)

st.markdown("---")

# --- ETAPA 4: CONSIDERAÇÕES TÉCNICAS E METODOLOGIA ---
with st.expander("4. Considerações Técnicas, Metodologia e Corpus de Confronto"):
    st.session_state.METODOLOGIA_TEXTO = st.text_area("Texto Detalhado sobre a Metodologia e Técnicas Aplicadas", 
                                                      value=st.session_state.get("METODOLOGIA_TEXTO", ""), height=300)
    
    st.session_state.CORPUS_CONFRONTO_TEXTO = st.text_area("Descrição do Corpus de Confronto (Peças de Autenticidade)", 
                                                           value=st.session_state.get("CORPUS_CONFRONTO_TEXTO", ""), height=150)
    if isinstance(st.session_state.etapas_concluidas, set):
        st.session_state.etapas_concluidas.add(4)

st.markdown("---")

# --- ETAPA 5: ANÁLISE COMPARATIVA ---
with st.expander("5. Análise Comparativa e Resultados (Desenvolvimento do Laudo)"):
    st.session_state.ANALISE_TEXTO = st.text_area("Descrição Detalhada da Análise e dos Elementos Gráficos Confrontados", 
                                                  value=st.session_state.get("ANALISE_TEXTO", ""), height=500)
    if isinstance(st.session_state.etapas_concluidas, set):
        st.session_state.etapas_concluidas.add(5)

st.markdown("---")

# --- ETAPA 6: ADENDOS GRÁFICOS (TABELAS E IMAGENS) ---
with st.expander("6. Adendos Gráficos (Tabelas e Imagens no Corpo do Laudo)"):
    
    # Formulário para adicionar Adendos/Ilustrações no corpo do laudo
    with st.form("form_adendos"):
        st.subheader("Adendos/Ilustrações")
        novo_adendo_legenda = st.text_input("Legenda do Adendo (Ex: Figura 1: Comparativo de Assinaturas)")
        imagem_adendo = st.file_uploader("Imagem do Adendo", type=['png', 'jpg', 'jpeg'], key="upload_adendo")
        
        if st.form_submit_button("➕ Adicionar Adendo Gráfico"):
            if novo_adendo_legenda and imagem_adendo:
                item_data = {
                    "legenda": novo_adendo_legenda,
                    "imagem_obj": imagem_adendo
                }
                add_list_item("adendos", item_data)
            else:
                st.error("A legenda e a imagem são obrigatórias para o Adendo.")

    # Visualização e remoção de Adendos
    if st.session_state.adendos:
        st.markdown("**Adendos Adicionados:**")
        for d in st.session_state.adendos:
            col_d1, col_d2 = st.columns([4, 1])
            col_d1.write(f"**Adendo {d['id']}:** {d['legenda']}")
            if col_d2.button("🗑️ Remover", key=f"del_adendo_{d['id']}"):
                remove_list_item("adendos", d['id'])
    
    if isinstance(st.session_state.etapas_concluidas, set):
        st.session_state.etapas_concluidas.add(6)

st.markdown("---")

# --- ETAPA 7: CONCLUSÃO E HONORÁRIOS ---
with st.expander("7. Conclusão e Informações Finais"):
    st.subheader("Conclusão do Laudo")
    st.session_state.CONCLUSION = st.text_area("Conclusão Final do Laudo Pericial", 
                                                value=st.session_state.get("CONCLUSION", ""), height=200)

    st.subheader("Informações Financeiras")
    col_h1, col_h2 = st.columns(2)
    with col_h1:
        st.session_state.HONORARIOS_VALOR = st.text_input("Valor dos Honorários (R$)", 
                                                          value=st.session_state.get("HONORARIOS_VALOR", ""))
    with col_h2:
        # PONTO CRÍTICO CORRIGIDO: Usa a função de sanitização máxima para o valor
        data_obj_v = get_date_object_from_state("HONORARIOS_VENCIMENTO")
            
        st.date_input(
            "Data de Vencimento do Pagamento", 
            value=data_obj_v, 
            key="input_data_vencimento",
            # Defesa na Escrita: Força o salvamento como string assim que o valor muda.
            on_change=update_vencimento_date
        )
        
    if isinstance(st.session_state.etapas_concluidas, set):
        st.session_state.etapas_concluidas.add(7)

st.markdown("---")

# --- ETAPA 8: GERAÇÃO DO LAUDO ---
with st.expander("8. Gerar Laudo Final", expanded=(8 in st.session_state.etapas_concluidas if isinstance(st.session_state.etapas_concluidas, set) else False)):
    st.subheader("Configurações de Geração")
    
    caminho_saida = os.path.join(OUTPUT_FOLDER, f"Laudo_{st.session_state.numero_processo}.docx")
    
    st.write(f"Modelo a ser usado: **{os.path.basename(CAMINHO_MODELO)}**")
    st.write(f"Arquivo de saída: **{os.path.basename(caminho_saida)}** (salvo em `{os.path.basename(OUTPUT_FOLDER)}/`)")

    # Verifica se pelo menos 7 etapas estão concluídas para habilitar o botão
    is_disabled = not(isinstance(st.session_state.etapas_concluidas, set) and len(st.session_state.etapas_concluidas) >= 7)

    if st.button("🚀 Gerar Documento .DOCX", type="primary", disabled=is_disabled):
        
        # Garante que os valores de data estejam atualizados no session_state antes de usar os dados
        update_laudo_date()
        update_vencimento_date()
        
        # Filtra apenas os dados simples para passar ao gerador de Word
        dados_simples = {k: v for k, v in st.session_state.items() if not k.startswith("editing_") and k not in ["process_to_load", "etapas_concluidas"]}
        
        # Trata os campos de lista que precisam ir ao Word Handler
        dados_simples['AUTORES'] = dados_simples.get('autor', '').split('\n')
        dados_simples['REUS'] = dados_simples.get('reu', '').split('\n')
        
        quesito_images_list = []
        
        # Prepara as imagens dos quesitos
        for q in st.session_state.quesitos_autor:
            if q.get("imagem_obj"):
                quesito_images_list.append({
                    "id": f"Autor {q['id']}",
                    "file_obj": q["imagem_obj"],
                    "description": f"Quesito {q['id']} do Autor"
                })
        
        for q in st.session_state.quesitos_reu:
            if q.get("imagem_obj"):
                quesito_images_list.append({
                    "id": f"Réu {q['id']}",
                    "file_obj": q["imagem_obj"],
                    "description": f"Quesito {q['id']} do Réu"
                })

        try:
            gerar_laudo(
                caminho_modelo=CAMINHO_MODELO,
                caminho_saida=caminho_saida,
                dados=dados_simples,
                anexos=st.session_state.anexos,
                adendos=st.session_state.adendos,
                quesito_images_list=quesito_images_list
            )
            
            if isinstance(st.session_state.etapas_concluidas, set):
                st.session_state.etapas_concluidas.add(8) 
            
            if save_current_state():
                 st.success(f"Laudo **{st.session_state.numero_processo}** gerado com sucesso!")
            
            # Adiciona botão de download
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