import streamlit as st
import os
import json
from datetime import date, datetime
from num2words import num2words
from typing import List, Dict, Any, Union
import pandas as pd
import matplotlib.pyplot as plt
import io # ADICIONADO: Import para io.BytesIO
import base64 

from word_handler import gerar_laudo
from data_handler import save_process_data, load_process_data
from db_handler import atualizar_status

# --- Configuração Inicial ---
st.set_page_config(page_title="Laudo Grafotécnico", layout="wide")

# CORREÇÃO CRÍTICA DO PATH: Garante o caminho absoluto para o modelo
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Ajuste conforme a estrutura do seu projeto (assumindo 01_Gerar_laudo.py está em 'pages')
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR) 

# --- Variáveis Globais ---
# Reajustado para usar o PROJECT_ROOT
CAMINHO_MODELO = os.path.join(PROJECT_ROOT, "template", "LAUDO PERICIAL GRAFOTÉCNICO.docx") 
OUTPUT_FOLDER = os.path.join(PROJECT_ROOT, "output")
DATA_FOLDER = os.path.join(PROJECT_ROOT, "data")

os.makedirs(DATA_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Lista de Elementos de Ordem Gráfica (EOG) para análise e preenchimento
EOG_ELEMENTS = [
    "Calibre (Dimensão)", "Alinhamento Gráfico", "Angulares e Curvilíneos", "Ataques e Remates", 
    "Comportamento da Linha Base", "Dinamismo", "Espaçamento", "Velocidade", "Inclinação Axial", 
    "Morfologia", "Pressão e Profundidade", "Proporção Gráfica"
]

# --- Funções de Manipulação de Estado ---

def init_session_state():
    """Inicializa as chaves necessárias no st.session_state."""
    if 'process_id' not in st.session_state:
        st.session_state.process_id = None
    if 'numero_processo' not in st.session_state:
        st.session_state.numero_processo = ""
    if 'autores' not in st.session_state:
        st.session_state.autores = []
    if 'reus' not in st.session_state:
        st.session_state.reus = []
    # Correção Crítica 1.1: Inicializa como SET
    if 'etapas_concluidas' not in st.session_state:
        st.session_state.etapas_concluidas = set() 
    
    # Etapa 2
    if 'documentos_questionados' not in st.session_state:
        st.session_state.documentos_questionados = []
    if 'padroes_encontrados' not in st.session_state:
        st.session_state.padroes_encontrados = []
        
    # Etapa 3
    if 'quesitos_autor' not in st.session_state:
        st.session_state.quesitos_autor = []
    if 'quesitos_reu' not in st.session_state:
        st.session_state.quesitos_reu = []

    # Etapa 4
    if 'eog_analise' not in st.session_state:
        st.session_state.eog_analise = {e: 'Não analisado' for e in EOG_ELEMENTS}
    if 'analise_texto' not in st.session_state:
        st.session_state.analise_texto = ""
        
    # Etapa 5
    if 'conclusion_tipo' not in st.session_state:
        st.session_state.conclusion_tipo = "Selecione a Conclusão"
    if 'conclusion' not in st.session_state:
        st.session_state.conclusion = ""
        
    # Etapa 6
    if 'adendos' not in st.session_state:
        st.session_state.adendos = []
    if 'anexos' not in st.session_state:
        st.session_state.anexos = []
        
    # Etapa 7
    if 'local_encerramento' not in st.session_state:
        st.session_state.local_encerramento = "São Paulo, SP"
    if 'data_encerramento' not in st.session_state:
        st.session_state.data_encerramento = date.today()
    if 'perito' not in st.session_state:
        st.session_state.perito = ""
    if 'numero_registro' not in st.session_state:
        st.session_state.numero_registro = ""
        
def load_process_if_requested():
    """Carrega o processo se o parâmetro 'process_to_load' estiver presente na URL."""
    query_params = st.query_params
    process_id = query_params.get("process_to_load")

    if process_id:
        try:
            # 1. Carrega dados do JSON
            dados_carregados = load_process_data(process_id)
            
            # 2. Limpa o estado atual e popula com dados carregados
            # Mantém apenas as chaves Streamlit internas se for o caso.
            for key in list(st.session_state.keys()):
                if not key.startswith(('st.', 'query_params')):
                    del st.session_state[key]
                    
            for key, value in dados_carregados.items():
                st.session_state[key] = value
                
            st.session_state.process_id = process_id # Garante que o ID está no estado

            # 3. Correção: Garante que etapas_concluidas é um SET
            if isinstance(st.session_state.get('etapas_concluidas'), list):
                 st.session_state.etapas_concluidas = set(st.session_state.etapas_concluidas)

            st.success(f"Processo **{process_id}** carregado com sucesso!")
            # Remove o parâmetro para evitar recarregar em loop
            st.query_params.clear() 

        except FileNotFoundError:
            st.error(f"Erro: Arquivo de dados para o processo {process_id} não encontrado.")
        except Exception as e:
            st.error(f"Erro ao carregar o processo {process_id}: {e}")

def save_current_state() -> bool:
    """Consolida o salvamento em JSON e a atualização do status no DB."""
    process_id = st.session_state.get('numero_processo')
    if not process_id:
        st.error("Erro: O número do processo não está definido. Não é possível salvar.")
        return False

    try:
        # Salva em JSON
        save_process_data(process_id, dict(st.session_state))
        
        # Atualiza status no DB
        autor_str = ", ".join(st.session_state.autores) if st.session_state.autores else "N/A"
        reu_str = ", ".join(st.session_state.reus) if st.session_state.reus else "N/A"
        
        status = "Concluído" if 7 in st.session_state.etapas_concluidas else "Em andamento"
        
        # O db_handler.py foi corrigido para usar datetime.now() e formatar
        atualizar_status(process_id, status) 
        
        return True
    except Exception as e:
        st.error(f"Erro ao salvar o estado do processo: {e}")
        return False

# --- Inicialização ---
init_session_state()
load_process_if_requested() # Tenta carregar se a URL indicar

# --- Funções Auxiliares de UI ---

def add_new_item(container, item_list_key, item_template: Dict[str, Any]):
    """Adiciona um novo item à lista na session_state."""
    if st.button("➕ Adicionar Novo Item", key=f"add_{item_list_key}"):
        new_id = len(st.session_state[item_list_key]) + 1
        new_item = item_template.copy()
        new_item['id'] = new_id
        st.session_state[item_list_key].append(new_item)
        st.rerun()

def edit_and_display_list(list_key, display_fields: List[str], edit_fields: List[Dict[str, str]], title: str, 
                         has_file_upload: bool = False, file_field_key: str = None):
    """Renderiza a lista de itens e permite edição/exclusão."""
    
    st.subheader(title)
    
    # Itera sobre uma cópia para evitar problemas de re-renderização durante o delete
    for i, item in enumerate(st.session_state[list_key]):
        unique_key = f"{list_key}_{item['id']}"
        
        # Exibe o item em um container expansível
        with st.expander(f"**{title.replace('Lista de ', '').replace('s', '')} {item['id']}**"):
            
            # --- Campos de Exibição ---
            for field in display_fields:
                st.markdown(f"**{field.capitalize()}:** {item.get(field, 'N/A')}")
            
            # --- Formulário de Edição ---
            with st.form(f"edit_form_{unique_key}"):
                st.markdown("##### Editar Dados")
                
                # Campos para edição
                new_values = {}
                for field_data in edit_fields:
                    field_key = field_data['key']
                    field_label = field_data['label']
                    field_type = field_data.get('type', 'text')

                    if field_type == 'text':
                        new_values[field_key] = st.text_area(field_label, value=item.get(field_key, ""), key=f"edit_{field_key}_{unique_key}")
                    elif field_type == 'date':
                        # As datas são salvas como date object, mas o Streamlit aceita o date object
                        new_values[field_key] = st.date_input(field_label, value=item.get(field_key, date.today()), key=f"edit_{field_key}_{unique_key}")
                
                # Upload de Arquivo (se aplicável)
                if has_file_upload and file_field_key:
                    current_file_name = item.get('file_obj_name', 'Nenhum arquivo anexado.')
                    st.caption(f"Arquivo Atual: `{current_file_name}`")
                    
                    uploaded_file = st.file_uploader("Substituir Imagem", type=['png', 'jpg', 'jpeg'], key=f"upload_{unique_key}")
                    
                    # Usa o file_obj já existente ou o novo upload
                    file_to_save = uploaded_file if uploaded_file is not None else item.get('file_obj')
                    
                    # Trata o nome do arquivo, se um novo foi carregado
                    if uploaded_file is not None:
                        new_values['file_obj_name'] = uploaded_file.name
                        new_values[file_field_key] = uploaded_file # Salva o UploadedFile (temporário)
                    else:
                        new_values[file_field_key] = file_to_save
                        new_values['file_obj_name'] = current_file_name


                col_save, col_delete = st.columns([1, 1])
                
                with col_save:
                    if st.form_submit_button("💾 Salvar Alterações", type="primary"):
                        # Atualiza o item na session_state
                        st.session_state[list_key][i].update(new_values)
                        save_current_state()
                        st.success("Item salvo com sucesso! Clique em 'Salvar Progresso' no menu lateral.")
                        st.rerun()

                with col_delete:
                    # Botão de Excluir fora do form, precisa de callback
                    if st.button("🗑️ Excluir Item", key=f"delete_{unique_key}"):
                        st.session_state[list_key].pop(i)
                        
                        # Re-indexa os IDs após a exclusão
                        for idx, item_reindex in enumerate(st.session_state[list_key]):
                            item_reindex['id'] = idx + 1
                            
                        save_current_state()
                        st.warning(f"Item {item['id']} excluído.")
                        st.rerun()
            st.markdown("---")
            

# --- Renderização do Menu Lateral e Botões Principais ---

st.sidebar.title("Opções")

if st.sidebar.button("💾 Salvar Progresso", key="save_button", type="primary"):
    if save_current_state():
        st.sidebar.success("Progresso salvo!")
    else:
        st.sidebar.error("Erro ao salvar o progresso.")

if st.sidebar.button("Novo Laudo", key="new_laudo_button"):
    for key in list(st.session_state.keys()):
        if not key.startswith(('st.', 'query_params')):
            del st.session_state[key]
    init_session_state()
    st.rerun()

# --- Renderização da Aplicação Principal ---

st.title("Gerador de Laudo Grafotécnico")

# --- Etapa 1: Dados do Processo ---
with st.container(border=True):
    st.header("1. Dados do Processo e Partes")
    
    col_id, col_perito, col_registro = st.columns([3, 2, 1])
    
    with col_id:
        st.session_state.numero_processo = st.text_input(
            "Número do Processo (ID Único)", 
            value=st.session_state.numero_processo,
            help="Este número será o identificador único para salvar e carregar o laudo."
        )
    
    with col_perito:
        st.session_state.perito = st.text_input(
            "Nome Completo do Perito", 
            value=st.session_state.perito,
        )
        
    with col_registro:
        st.session_state.numero_registro = st.text_input(
            "Nº do Registro", 
            value=st.session_state.numero_registro,
        )

    st.markdown("---")
    
    col_autor, col_reu = st.columns(2)
    
    with col_autor:
        autores_text = st.text_area("Autor(es) (Um por linha)", value="\n".join(st.session_state.autores))
        st.session_state.autores = [a.strip() for a in autores_text.split('\n') if a.strip()]
        
    with col_reu:
        reus_text = st.text_area("Réu(s) (Um por linha)", value="\n".join(st.session_state.reus))
        st.session_state.reus = [r.strip() for r in reus_text.split('\n') if r.strip()]

    if st.session_state.numero_processo and st.session_state.autores and st.session_state.reus:
        st.session_state.etapas_concluidas.add(1) # CORREÇÃO: Usa .add()
        st.success("Etapa 1 concluída.")
    else:
        if 1 in st.session_state.etapas_concluidas:
            st.session_state.etapas_concluidas.remove(1)
        st.warning("Preencha o Número do Processo, Autor e Réu para avançar.")

# --- Etapa 2: Documentos ---
if 1 in st.session_state.etapas_concluidas:
    with st.container(border=True):
        st.header("2. Documentos Questionados e Padrão")
        
        # 2.1. Documentos Questionados
        doc_q_template = {'tipo': 'Contrato', 'numero': 'N/A', 'data': date.today(), 'fls': 'N/A'}
        
        edit_and_display_list(
            list_key='documentos_questionados',
            display_fields=['tipo', 'numero', 'data', 'fls'],
            edit_fields=[
                {'key': 'tipo', 'label': 'Tipo de Documento'},
                {'key': 'numero', 'label': 'Número/ID'},
                {'key': 'data', 'label': 'Data', 'type': 'date'},
                {'key': 'fls', 'label': 'Fls.'},
            ],
            title="Lista de Documentos Questionados (4.1)",
        )
        
        add_new_item(st.container(), 'documentos_questionados', doc_q_template)
        
        st.markdown("---")
        
        # 2.2. Padrões Encontrados (PCE)
        padrao_e_template = {'tipo': 'Cópia de RG', 'data': date.today(), 'fls': 'N/A'}
        
        edit_and_display_list(
            list_key='padroes_encontrados',
            display_fields=['tipo', 'data', 'fls'],
            edit_fields=[
                {'key': 'tipo', 'label': 'Tipo de Padrão'},
                {'key': 'data', 'label': 'Data', 'type': 'date'},
                {'key': 'fls', 'label': 'Fls.'},
            ],
            title="Lista de Padrões Encontrados nos Autos (4.2.B)",
        )
        
        add_new_item(st.container(), 'padroes_encontrados', padrao_e_template)
        
        if st.session_state.documentos_questionados or st.session_state.padroes_encontrados:
            st.session_state.etapas_concluidas.add(2)
            st.success("Etapa 2 concluída.")
        else:
            if 2 in st.session_state.etapas_concluidas:
                st.session_state.etapas_concluidas.remove(2)

# --- Etapa 3: Quesitos ---
if 2 in st.session_state.etapas_concluidas:
    with st.container(border=True):
        st.header("3. Quesitos e Imagens para Anexos")
        
        col_autor_quesito, col_reu_quesito = st.columns(2)
        
        # 3.1. Quesitos Autor
        with col_autor_quesito:
            quesito_autor_template = {'quesito': 'O documento é autêntico?', 'resposta': 'Sim.', 'file_obj': None, 'file_obj_name': ''}
            
            edit_and_display_list(
                list_key='quesitos_autor',
                display_fields=['quesito', 'resposta'],
                edit_fields=[
                    {'key': 'quesito', 'label': 'Texto do Quesito', 'type': 'text'},
                    {'key': 'resposta', 'label': 'Resposta do Perito', 'type': 'text'},
                ],
                title="Lista de Quesitos do Autor",
                has_file_upload=True,
                file_field_key='file_obj'
            )
            add_new_item(st.container(), 'quesitos_autor', quesito_autor_template)
            
        # 3.2. Quesitos Réu
        with col_reu_quesito:
            quesito_reu_template = {'quesito': 'A assinatura é falsa?', 'resposta': 'Sim, é falsa.', 'file_obj': None, 'file_obj_name': ''}
            
            edit_and_display_list(
                list_key='quesitos_reu',
                display_fields=['quesito', 'resposta'],
                edit_fields=[
                    {'key': 'quesito', 'label': 'Texto do Quesito', 'type': 'text'},
                    {'key': 'resposta', 'label': 'Resposta do Perito', 'type': 'text'},
                ],
                title="Lista de Quesitos do Réu",
                has_file_upload=True,
                file_field_key='file_obj'
            )
            add_new_item(st.container(), 'quesitos_reu', quesito_reu_template)
            
        if st.session_state.quesitos_autor or st.session_state.quesitos_reu:
            st.session_state.etapas_concluidas.add(3)
            st.success("Etapa 3 concluída.")
        else:
            if 3 in st.session_state.etapas_concluidas:
                st.session_state.etapas_concluidas.remove(3)

# --- Etapa 4: Análise de EOG ---
if 3 in st.session_state.etapas_concluidas:
    with st.container(border=True):
        st.header("4. Análise dos Elementos de Ordem Gráfica (EOG)")
        
        st.subheader("Seleção dos Resultados")
        
        # Colunas para organizar a seleção
        cols = st.columns(3)
        
        for i, element in enumerate(EOG_ELEMENTS):
            col = cols[i % 3]
            
            # Opções de conclusão
            options = ["Não analisado", "Convergente", "Divergente", "Não aplicável"]
            
            # Atualiza o session_state diretamente
            st.session_state.eog_analise[element] = col.selectbox(
                element, 
                options,
                index=options.index(st.session_state.eog_analise.get(element, "Não analisado")),
                key=f"eog_{element.replace(' ', '_')}"
            )
            
        st.markdown("---")
        
        st.subheader("Texto de Análise (5.2. Confronto Grafoscópico)")
        st.session_state.analise_texto = st.text_area(
            "Detalhe a análise grafoscópica e o confronto (Este texto aparecerá abaixo da lista de EOGs no laudo):",
            value=st.session_state.analise_texto,
            height=200
        )
        
        # Verifica se pelo menos 3 EOGs foram analisados (Convergente/Divergente)
        analisados_count = sum(1 for status in st.session_state.eog_analise.values() if status in ["Convergente", "Divergente"])
        
        if analisados_count >= 1:
            st.session_state.etapas_concluidas.add(4)
            st.success(f"Etapa 4 concluída. ({analisados_count} Elementos analisados).")
        else:
            if 4 in st.session_state.etapas_concluidas:
                st.session_state.etapas_concluidas.remove(4)
            st.warning("Selecione pelo menos um EOG como 'Convergente' ou 'Divergente'.")

# --- Etapa 5: Conclusão ---
if 4 in st.session_state.etapas_concluidas:
    with st.container(border=True):
        st.header("5. Conclusão do Laudo")
        
        st.session_state.conclusion_tipo = st.selectbox(
            "Tipo de Conclusão (Em negrito/Caixa Alta)",
            ["Selecione a Conclusão", "Conclusiva Positiva", "Conclusiva Negativa", "Inconclusiva"],
            index=["Selecione a Conclusão", "Conclusiva Positiva", "Conclusiva Negativa", "Inconclusiva"].index(st.session_state.conclusion_tipo)
        )
        
        st.session_state.conclusion = st.text_area(
            "Texto da Conclusão (detalhamento do tipo selecionado):",
            value=st.session_state.conclusion,
            height=250
        )
        
        if st.session_state.conclusion_tipo != "Selecione a Conclusão" and st.session_state.conclusion:
            st.session_state.etapas_concluidas.add(5)
            st.success("Etapa 5 concluída.")
        else:
            if 5 in st.session_state.etapas_concluidas:
                st.session_state.etapas_concluidas.remove(5)
            st.warning("Selecione o Tipo e preencha o Texto da Conclusão.")

# --- Etapa 6: Adendos e Anexos ---
if 5 in st.session_state.etapas_concluidas:
    with st.container(border=True):
        st.header("6. Adendos Gráficos e Anexos")
        
        st.info("As imagens dos quesitos (Etapa 3) serão automaticamente incluídas como Anexos no laudo.")
        st.markdown("---")
        
        # 6.1. Adendos Gráficos
        adendo_template = {'legenda': 'Adendo Gráfico 1 - Detalhe da convergência', 'file_obj': None, 'file_obj_name': ''}
        
        edit_and_display_list(
            list_key='adendos',
            display_fields=['legenda'],
            edit_fields=[
                {'key': 'legenda', 'label': 'Legenda do Adendo', 'type': 'text'},
            ],
            title="Lista de Adendos Gráficos (Bloco 7 do Laudo)",
            has_file_upload=True,
            file_field_key='file_obj'
        )
        add_new_item(st.container(), 'adendos', adendo_template)
        
        # 6.2. Anexos (se necessário, para outros documentos)
        # Manter a estrutura para anexos não visuais se necessário.
        st.session_state.etapas_concluidas.add(6)
        st.success("Etapa 6 concluída.")

# --- Etapa 7: Geração do Laudo ---
if 6 in st.session_state.etapas_concluidas:
    with st.container(border=True):
        st.header("7. Encerramento e Geração")
        
        col_local, col_data, col_exames = st.columns(3)
        
        with col_local:
            st.session_state.local_encerramento = st.text_input(
                "Local de Encerramento (Ex: São Paulo, SP)", 
                value=st.session_state.local_encerramento
            )
            
        with col_data:
            st.session_state.data_encerramento = st.date_input(
                "Data de Encerramento", 
                value=st.session_state.data_encerramento
            )

        with col_exames:
            st.session_state.num_exames = st.number_input(
                "Nº de Exames Realizados (para campos por extenso)",
                value=st.session_state.get('num_exames', 0),
                min_value=0
            )
        
        data_extenso = num2words(st.session_state.data_encerramento.day, lang='pt_BR')
        data_extenso += f" de {st.session_state.data_encerramento.strftime('%B')} de {st.session_state.data_encerramento.year}"

        st.markdown(f"**Data Completa (Bloco 8):** {st.session_state.local_encerramento}, {data_extenso}")
        
        st.markdown("---")
        st.subheader("Gerar Documento Final")
        
        if st.button("🚀 Gerar Laudo .DOCX", key="generate_docx", type="primary"):
            
            if not st.session_state.numero_processo or not st.session_state.autores or not st.session_state.reus:
                st.error("Preencha a Etapa 1 (Número do Processo e Partes) antes de gerar.")
            else:
                
                # 1. Prepara os dados para o word_handler
                dados_simples = {
                    k.upper().replace(' ', '_'): v for k, v in dict(st.session_state).items() 
                    if not isinstance(v, (list, set, io.BytesIO))
                }
                dados_simples['LOCAL_ENCERRAMENTO'] = st.session_state.get('LOCAL_ENCERRAMENTO', 'São Paulo, SP')
                dados_simples['DATA_LAUDO_COMPLETA'] = f"{st.session_state.LOCAL_ENCERRAMENTO}, {data_extenso}"
                dados_simples['NUM_EXAMES'] = st.session_state.num_exames
                
                # Adiciona listas de Autores/Réus para substituição em bloco
                dados_simples['AUTORES'] = st.session_state.autores
                dados_simples['REUS'] = st.session_state.reus
                
                # NOVO: Adiciona as listas de quesitos para o gerador de bloco de texto
                # A chave é QUESITOS_AUTOR/REU (em maiúsculas) para ser consistente com word_handler.py
                dados_simples['QUESITOS_AUTOR'] = st.session_state.quesitos_autor
                dados_simples['QUESITOS_REU'] = st.session_state.quesitos_reu
                
                # Campos de data (convertidos para string no save_process_data, mas aqui usamos o date object)
                dados_simples['DATA_ENCERRAMENTO'] = st.session_state.data_encerramento.strftime('%d/%m/%Y')
                
                # Caminhos
                nome_arquivo_saida = f"LAUDO GRAFOTECNICO - {st.session_state.numero_processo}.docx"
                caminho_saida = os.path.join(OUTPUT_FOLDER, nome_arquivo_saida)
                
                # --- PREPARAÇÃO DAS IMAGENS ---
                quesito_images_list = []
                adendos_para_gerar = []
                
                def prepare_image_for_word(item_list: List[Dict[str, Any]], item_type: str) -> List[Dict[str, Any]]:
                    """Converte UploadedFile em io.BytesIO para uso no python-docx."""
                    prepared_list = []
                    for item in item_list:
                        # item['file_obj'] pode ser UploadedFile (novo) ou None (carregado do JSON)
                        if item.get("file_obj"):
                            try:
                                uploaded_file = item["file_obj"]
                                
                                # Verifica se é um UploadedFile ou já um BytesIO (o que não deve acontecer se o data_handler.py estiver funcionando)
                                if hasattr(uploaded_file, 'read'): 
                                    uploaded_file.seek(0) # Volta o ponteiro para o início
                                    binary_content = uploaded_file.read()
                                    
                                    if binary_content:
                                        file_buffer = io.BytesIO(binary_content)
                                        # Usa o nome do item/quesito como descrição/legenda
                                        legenda = item.get('legenda', item.get('quesito', f"{item_type} {item['id']}"))
                                        
                                        prepared_list.append({
                                            "id": item["id"],
                                            "file_obj": file_buffer, 
                                            "description": legenda,
                                            "legenda": legenda # Mantém a chave 'legenda' para o word_handler
                                        })
                                    
                            except Exception as e:
                                st.warning(f"Aviso: Não foi possível ler a imagem do {item_type} {item['id']}. Erro: {e}")
                    return prepared_list

                # 2. Processa as imagens de Quesitos
                quesito_images_list.extend(prepare_image_for_word(st.session_state.quesitos_autor, "Quesito Autor"))
                quesito_images_list.extend(prepare_image_for_word(st.session_state.quesitos_reu, "Quesito Réu"))
                
                # 3. Processa os Adendos
                adendos_para_gerar = prepare_image_for_word(st.session_state.adendos, "Adendo")

                
                try:
                    # 4. Gera o Laudo
                    gerar_laudo(
                        caminho_modelo=CAMINHO_MODELO,
                        caminho_saida=caminho_saida,
                        dados=dados_simples,
                        anexos=st.session_state.anexos, # Lista de anexos (outros) - Mantida para compatibilidade
                        adendos=adendos_para_gerar, # Usa lista processada de Adendos
                        quesito_images_list=quesito_images_list # Passa lista processada de Imagens de Quesitos
                    )
                    
                    # 5. Finaliza
                    st.session_state.etapas_concluidas.add(7) # CORREÇÃO: Usa .add()
                    
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
                    st.error(f"❌ Erro de Arquivo: O arquivo de modelo não foi encontrado. Verifique se o arquivo 'LAUDO PERICIAL GRAFOTÉCNICO.docx' está na pasta 'template' na raiz do projeto.")
                except Exception as e:
                    st.error(f"❌ Erro na Geração do Laudo: {e}")

if 7 in st.session_state.etapas_concluidas:
    st.success("Etapa 7 concluída. Laudo gerado com sucesso!")

# Correção Crítica 1.2: Linha solta que causava o SyntaxError foi removida.