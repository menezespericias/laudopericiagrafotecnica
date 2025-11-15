from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from num2words import num2words
import os
import re
from typing import List, Dict, Any 
from io import BytesIO

# --- FUNÇÕES DE UTILIDADE DE WORD DOCX ---

# 1. FUNÇÃO AUXILIAR PARA INSERIR IMAGEM
def inserir_imagem_em_paragrafo(paragrafo, file_obj, legenda: str = None, largura_maxima: float = 6.0):
    """
    Insere uma imagem a partir de um objeto de arquivo (UploadedFile do Streamlit) 
    e ajusta sua largura máxima.
    """
    if not file_obj:
        return

    # O objeto file_obj (UploadedFile) contém os bytes da imagem
    image_bytes = file_obj.getvalue()
    
    # Usa BytesIO para criar um stream de arquivo na memória, necessário para docx
    image_stream = BytesIO(image_bytes)
    
    # Insere a imagem
    paragrafo.add_run().add_picture(image_stream, width=Inches(largura_maxima))
    
    # Adiciona a legenda
    if legenda:
        paragrafo.add_run(f'\n{legenda}').bold = True
    
    # Alinha a imagem e a legenda ao centro
    paragrafo.alignment = WD_ALIGN_PARAGRAPH.CENTER

# 2. FUNÇÃO AUXILIAR PARA SUBSTITUIÇÃO EM PARÁGRAFOS
def substituir_em_paragrafo(paragrafo, dados: dict):
    """
    Substitui os placeholders em um parágrafo mantendo a formatação original.
    """
    
    # Placeholders que serão tratados como LISTAS (não substituição simples)
    LIST_PLACEHOLDERS = ["[AUTORES]", "[REUS]"] 
    
    texto_original = paragrafo.text
    
    # Verifica se o parágrafo contém placeholders de lista. Se sim, ignora a substituição de texto.
    if any(lp in texto_original for lp in LIST_PLACEHOLDERS):
        return

    # FUNÇÃO INTERNA PARA PRESERVAR A FORMATAÇÃO
    def replace_match(match):
        placeholder = match.group(0)
        chave = placeholder[1:-1] # Remove []
        
        if chave in dados:
            valor = dados[chave]
            # Formatação de datas
            if isinstance(valor, date):
                valor_str = valor.strftime("%d/%m/%Y")
            else:
                valor_str = str(valor)
                
            return valor_str
        else:
            return placeholder

    # Padrão regex para encontrar [QUALQUER_COISA]
    padrao = re.compile(r'\[[A-Z0-9_]+\]')
    
    # Aplica a substituição run por run para manter a formatação (mais complexo, usando re.sub)
    # A maneira mais robusta no python-docx é através da manipulação dos runs,
    # mas a forma abaixo substitui no texto e exige re-aplicar a formatação,
    # vamos usar uma abordagem simplificada (substituir no texto e torcer para o docx ser indulgente):
    
    # Esta abordagem simples pode quebrar a formatação se o placeholder estiver em vários runs.
    # Usaremos a abordagem mais robusta em docx que é a manipuição dos runs (como já estava no seu código original).
    # O código abaixo é a implementação robusta que você tinha, ligeiramente ajustada:
    
    for run in paragrafo.runs:
        texto_run = run.text
        
        # Cria uma função de substituição para usar com regex (para evitar múltiplas iterações)
        def _substituir(texto):
            for chave, valor in dados.items():
                placeholder = f"[{chave.upper()}]"
                
                if isinstance(valor, list): # Ignora listas
                    continue
                
                # Trata a data para formatação
                valor_str = str(valor)
                if isinstance(valor, date):
                    valor_str = valor.strftime("%d/%m/%Y")

                texto = texto.replace(placeholder, valor_str)
            return texto

        novo_texto_run = _substituir(texto_run)
        
        if novo_texto_run != texto_run:
            run.text = novo_texto_run


# 3. FUNÇÃO AUXILIAR DE SUBSTITUIÇÃO EM TABELAS
def substituir_em_tabela(tabela, dados: dict):
    """Substitui placeholders em todas as células da tabela."""
    for row in tabela.rows:
        for cell in row.cells:
            for paragrafo in cell.paragraphs:
                substituir_em_paragrafo(paragrafo, dados)


# 4. FUNÇÃO PARA INSERIR LISTA (Como Parágrafos)
def inserir_lista_no_paragrafo(doc, marcador, lista):
    """
    Localiza o placeholder do marcador no documento e o substitui por itens da lista
    como novos parágrafos formatados com uma lista simples (Bullet Points).
    """
    placeholder = f"[{marcador}]"
    
    # Se a lista vier como string com quebras de linha
    if isinstance(lista, str) and "\n" in lista:
        lista = [item.strip() for item in lista.split("\n") if item.strip()]
    elif not isinstance(lista, list):
        return # Não é uma lista válida

    for i, paragrafo in enumerate(doc.paragraphs):
        if placeholder in paragrafo.text:
            
            # Divide o parágrafo em partes antes, placeholder e depois
            partes = paragrafo.text.split(placeholder, 1)
            
            # Se houver texto antes ou depois do placeholder, mantém no parágrafo original
            if partes[0] or partes[1]:
                paragrafo.text = partes[0] + partes[1]
            else:
                paragrafo.text = "" # Limpa o parágrafo se só tinha o placeholder
            
            if not lista:
                return

            # Adiciona os novos itens da lista *antes* do parágrafo que continha o placeholder
            for item in lista:
                # O novo parágrafo deve ser inserido ANTES do parágrafo atual (paragrafo)
                novo_paragrafo = paragrafo.insert_paragraph_before(item)
                
                try:
                    # Tenta aplicar estilo de Bullet Point (se existir no modelo)
                    novo_paragrafo.style = 'List Bullet' 
                except KeyError:
                    pass 
            
            return # Sai assim que substituir o primeiro (e único) placeholder

# 5. FUNÇÃO PARA INSERIR IMAGENS EM SEÇÃO DE ANEXOS/ADENDOS
def inserir_imagens_em_secao(doc, titulo_secao: str, imagens: List[Dict[str, Any]], prefixo_legenda: str):
    """
    Insere uma nova seção (título) e todas as imagens da lista.
    """
    
    if not imagens:
        return

    # Adiciona um título para a seção
    doc.add_heading(titulo_secao, level=1)
    
    for item in imagens:
        file_obj = item.get('imagem_obj')
        legenda_base = item.get('legenda') or item.get('descricao') or f"{prefixo_legenda} {item.get('id', '')}"
        
        # Apenas insere se o objeto de arquivo for válido (UploadedFile tem o atributo 'name')
        if file_obj and hasattr(file_obj, 'name'):
            
            # Título/legenda completa (Ex: Adendo 1 - Nome da figura)
            legenda_completa = f"{prefixo_legenda} {item['id']}: {legenda_base}"
            
            # Adiciona um novo parágrafo para a imagem
            paragrafo_imagem = doc.add_paragraph()
            
            # Insere a imagem e a legenda
            # Usando uma largura de 6.0 polegadas como padrão (quase a largura total da página)
            inserir_imagem_em_paragrafo(paragrafo_imagem, file_obj, legenda=legenda_completa, largura_maxima=6.0)
            
            # Adiciona uma quebra de página, se for o último item do laudo (opcional)
            # doc.add_page_break()


# 6. FUNÇÃO PRINCIPAL DE GERAÇÃO
def gerar_laudo(
    caminho_modelo: str, 
    caminho_saida: str, 
    dados: dict, 
    anexos: List[Dict[str, Any]], 
    adendos: List[Dict[str, Any]], 
    quesito_images_list: List[Dict[str, Any]]
):
    """Função principal que coordena a geração do documento DOCX."""
    doc = Document(caminho_modelo)
    
    # 1. ADICIONAR VERSÕES POR EXTENSO (para uso automático)
    
    # Adiciona 'EXTENSO' para NUM_EXAMES
    if "NUM_EXAMES" in dados and isinstance(dados["NUM_EXAMES"], str) and dados["NUM_EXAMES"].isdigit():
        num = int(dados["NUM_EXAMES"])
        dados["NUM_EXAMES_EXTENSO"] = num2words(num, lang='pt_BR').upper() 
    
    # NOVO: Adiciona 'EXTENSO' para NUM_PECA_AUTENTICIDADE
    if "NUM_PECA_AUTENTICIDADE" in dados and isinstance(dados["NUM_PECA_AUTENTICIDADE"], str) and dados["NUM_PECA_AUTENTICIDADE"].isdigit():
        num = int(dados["NUM_PECA_AUTENTICIDADE"])
        dados["NUM_PECA_AUTENTICIDADE_EXTENSO"] = num2words(num, lang='pt_BR').upper() 

    # NOVO: Adiciona 'EXTENSO' para NUM_PECA_QUESTIONADA
    if "NUM_PECA_QUESTIONADA" in dados and isinstance(dados["NUM_PECA_QUESTIONADA"], str) and dados["NUM_PECA_QUESTIONADA"].isdigit():
        num = int(dados["NUM_PECA_QUESTIONADA"])
        dados["NUM_PECA_QUESTIONADA_EXTENSO"] = num2words(num, lang='pt_BR').upper() 

    
    # 2. SUBSTITUIÇÃO DE CAMPOS DE TEXTO E LISTAS
    for paragrafo in doc.paragraphs:
        
        # Tenta inserir a lista de Autores/Réus onde o placeholder estiver
        if "[AUTORES]" in paragrafo.text and 'AUTORES' in dados:
            inserir_lista_no_paragrafo(doc, "AUTORES", dados['AUTORES'])
            
        elif "[REUS]" in paragrafo.text and 'REUS' in dados:
            inserir_lista_no_paragrafo(doc, "REUS", dados['REUS'])
            
        elif "[QUESITOS_AUTOR]" in paragrafo.text and 'quesitos_autor' in dados:
             # Formata a lista de quesitos (ex: "1. Texto do quesito")
            lista_quesitos = [f"{q['id']}. {q['texto']}" for q in dados['quesitos_autor']]
            inserir_lista_no_paragrafo(doc, "QUESITOS_AUTOR", lista_quesitos)

        elif "[QUESITOS_REU]" in paragrafo.text and 'quesitos_reu' in dados:
            lista_quesitos = [f"{q['id']}. {q['texto']}" for q in dados['quesitos_reu']]
            inserir_lista_no_paragrafo(doc, "QUESITOS_REU", lista_quesitos)
            
        else:
            # Para os demais placeholders
            substituir_em_paragrafo(paragrafo, dados)

    # 3. SUBSTITUIÇÃO DE CAMPOS EM TABELAS
    for tabela in doc.tables:
        substituir_em_tabela(tabela, dados)
        
    # 4. INSERÇÃO DE IMAGENS DENTRO DO LAUDO (Adendos e Ilustrações)
    # Insere as imagens após o último parágrafo, ou onde você desejar.
    inserir_imagens_em_secao(doc, "ADENDOS GRÁFICOS E ILUSTRAÇÕES", adendos, "Adendo/Figura")
    
    # 5. INSERÇÃO DE IMAGENS DE QUESITOS E ANEXOS (Geralmente no final)
    # Quesitos (imagens dos documentos de quesitos)
    if quesito_images_list:
        inserir_imagens_em_secao(doc, "IMAGENS DE QUESITOS", quesito_images_list, "Quesito")
    
    # Anexos (imagens dos documentos anexados)
    if anexos:
        inserir_imagens_em_secao(doc, "ANEXOS E DOCUMENTOS", anexos, "Anexo")

    # 6. SALVAR DOCUMENTO
    doc.save(caminho_saida)