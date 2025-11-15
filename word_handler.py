from docx import Document
from docx.shared import Inches
from num2words import num2words
import os
import re
from typing import List, Dict, Any # Importações para clareza

# 1. FUNÇÃO PRINCIPAL DE GERAÇÃO
def gerar_laudo(
    caminho_modelo: str, 
    caminho_saida: str, 
    dados: dict, 
    anexos: List[Dict[str, Any]], 
    adendos: List[Dict[str, Any]], 
    quesito_images_list: List[Dict[str, Any]] # <--- ARGUMENTO FALTANTE CORRIGIDO!
):
    doc = Document(caminho_modelo)
    
    # Adicionar versões por extenso dos números para uso automático
    if "NUM_ESPECIMES" in dados and isinstance(dados["NUM_ESPECIMES"], str) and dados["NUM_ESPECIMES"].isdigit():
        num = int(dados["NUM_ESPECIMES"])
        # Garante que a versão por extenso esteja em maiúsculas
        dados["NUM_ESPECIMES_EXTENSO"] = num2words(num, lang='pt_BR').upper() 

    # Substituição de campos de texto em parágrafos e tabelas (PRESERVANDO FORMATAÇÃO)
    for paragrafo in doc.paragraphs:
        substituir_em_paragrafo(paragrafo, dados)

    for tabela in doc.tables:
        for linha in tabela.rows:
            for celula in linha.cells:
                # Iterar sobre os parágrafos dentro de cada célula
                for paragrafo in celula.paragraphs:
                    substituir_em_paragrafo(paragrafo, dados)

    # Inserção de listas (AUTORES, REUS) - Mantida a função original para compatibilidade
    inserir_lista_no_paragrafo(doc, "AUTORES", dados.get("AUTORES", [])) 
    inserir_lista_no_paragrafo(doc, "REUS", dados.get("REUS", []))

    
    # --- INSERÇÃO DE IMAGENS ---
    # Removida a seção IX. ANÁLISE DAS ASSINATURAS, que parecia ser uma versão antiga.

    # IX. Demonstrações dos Quesitos (FIGURAS)
    if quesito_images_list:
        doc.add_page_break()
        doc.add_heading("IX. DEMONSTRAÇÕES DOS QUESITOS", level=1)
        for i, img_data in enumerate(quesito_images_list):
            if img_data.get("file_obj") is not None:
                try:
                    # O objeto é Streamlit UploadedFile
                    img_data["file_obj"].seek(0)
                    doc.add_picture(img_data["file_obj"], width=Inches(5.5))
                    # Usando img_data["id"] para referenciar o número do quesito
                    doc.add_paragraph(f"Figura {img_data['id']}: {img_data['description']}") 
                    doc.add_paragraph() # Espaçamento
                except Exception as e:
                    doc.add_paragraph(f"[ERRO AO INSERIR IMAGEM {img_data['id']} nos Quesitos: {str(e)}]")


    # X. ANEXOS (Arquivos) - Lista de descrições, insere apenas imagens (se houver)
    if anexos or dados.get("ANEXOS_LIST"):
        doc.add_page_break()
        doc.add_heading("X. ANEXOS", level=1)
        # O bloco de texto já deve ter sido substituído nos placeholders.
        
        for anexo in anexos:
             if anexo.get("ARQUIVO") is not None:
                try:
                    # Tenta inserir a imagem (se não for PDF/DOCX)
                    anexo["ARQUIVO"].seek(0)
                    doc.add_picture(anexo["ARQUIVO"], width=Inches(5.5))
                    doc.add_paragraph(f"Figura: {anexo.get('DESCRICAO', anexo['ARQUIVO'].name)}")
                    doc.add_paragraph()
                except Exception:
                    # Ignora se for PDF/DOCX ou falhar a inserção de imagem
                    pass

    # XI. ADENDOS (Imagens/Gráficos)
    if adendos:
        doc.add_page_break()
        doc.add_heading("XI. ADENDOS", level=1)
        for adendo in adendos:
            if adendo.get("ARQUIVO") is not None:
                try:
                    adendo["ARQUIVO"].seek(0)
                    doc.add_picture(adendo["ARQUIVO"], width=Inches(5.5))
                    doc.add_paragraph(f"Figura: {adendo.get('DESCRICAO', adendo['ARQUIVO'].name)}")
                    doc.add_paragraph()
                except Exception as e:
                    doc.add_paragraph(f"[ERRO AO INSERIR ADENDO: {str(e)}]")
                    
    # Cria diretório de saída se não existir
    os.makedirs(os.path.dirname(caminho_saida), exist_ok=True)
    doc.save(caminho_saida)

# 2. FUNÇÃO CRÍTICA DE SUBSTITUIÇÃO (PRESERVA FORMATAÇÃO)
def substituir_em_paragrafo(paragrafo, dados):
    """Substitui placeholders em um parágrafo, preservando a formatação (runs)."""
    
    # 1. Agrega o texto de todos os runs do parágrafo
    texto_completo = "".join(run.text for run in paragrafo.runs)
    
    # 2. Executa a substituição em todo o texto
    texto_substituido = substituir_placeholders(texto_completo, dados)
    
    # 3. Se o texto não mudou, retorna
    if texto_completo == texto_substituido:
        return
    
    # 4. Limpa o parágrafo existente (deleta runs antigos)
    if not paragrafo.runs:
        paragrafo.add_run(texto_substituido)
        return

    primeiro_run = paragrafo.runs[0]
    primeiro_run.text = texto_substituido
    
    # Remove todos os runs a partir do segundo
    for i in range(len(paragrafo.runs) - 1, 0, -1):
        p = paragrafo._element
        p.remove(paragrafo.runs[i]._element)

# 3. FUNÇÃO AUXILIAR DE SUBSTITUIÇÃO DE TEXTO
def substituir_placeholders(texto, dados):
    """Substitui placeholders (ex: [CHAVE]) pelo valor em dados."""
    
    # Padrões para placeholders: [CHAVE], {CHAVE}, <<CHAVE>>
    padrao = r"(\[\s*([^\]]+?)\s*\]|\{\s*([^}]+?)\s*\}|<<\s*([^>]+?)\s*>>)"
    
    def replace_match(match):
        # O grupo que não for None contém a CHAVE
        chave = match.group(2) or match.group(3) or match.group(4)
        chave_limpa = chave.strip()

        # Tratamento para versão por extenso
        if chave_limpa.endswith("_EXTENSO"):
            base_chave = chave_limpa[:-8] # Remove '_EXTENSO'
            base_valor = dados.get(base_chave)
            if base_valor is not None and isinstance(base_valor, str) and base_valor.isdigit():
                try:
                    num = int(base_valor)
                    return num2words(num, lang='pt_BR').upper() 
                except ValueError:
                    pass
        
        # Tratamento padrão
        if chave_limpa in dados:
            valor = dados[chave_limpa]
            if isinstance(valor, str):
                return valor
            # Se for uma lista, retorna a união dos itens com quebra de linha
            elif isinstance(valor, list):
                 return "\n".join(valor)
            elif valor is not None:
                return str(valor)
        
        # Se não encontrou valor ou o valor é None, retorna o placeholder original
        return match.group(0)

    # Realiza a substituição usando a função interna (callback)
    return re.sub(padrao, replace_match, texto)


# 4. FUNÇÃO PARA INSERIR LISTA (Como Parágrafos)
def inserir_lista_no_paragrafo(doc, marcador, lista):
    """
    Localiza o placeholder do marcador no documento e o substitui por itens da lista
    como novos parágrafos formatados com uma lista simples (Bullet Points).
    """
    placeholder = f"[{marcador}]"
    
    if not isinstance(lista, list):
        # Tenta converter a string em lista (se contiver quebras de linha)
        if isinstance(lista, str) and "\n" in lista:
            lista = lista.split("\n")
        else:
            return

    for paragrafo in doc.paragraphs:
        if placeholder in paragrafo.text:
            
            # Remove o placeholder do parágrafo original
            paragrafo.text = paragrafo.text.replace(placeholder, "")
            
            if not lista:
                return

            # Adiciona os novos itens da lista como parágrafos com estilo de lista
            for item in lista:
                novo_paragrafo = paragrafo.insert_paragraph_before(item)
                
                try:
                    # Tenta aplicar estilo de Bullet Point
                    novo_paragrafo.style = 'List Bullet' 
                except KeyError:
                    pass # Continua sem estilo se não encontrar no modelo
            
            break

# 5. FUNÇÃO PARA CARREGAR ÍNDICE DE PROCESSOS DO GOOGLE SHEETS
def carregar_indice_processos():
    import streamlit as st
    import gspread
    from google.oauth2.service_account import Credentials

    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    try:
        credentials = Credentials.from_service_account_info(
            dict(st.secrets["gcp_service_account"]),
            scopes=SCOPES
        )
        client = gspread.authorize(credentials)
        spreadsheet = client.open_by_url(st.secrets["spreadsheet_url"])
        worksheet = spreadsheet.sheet1  # ou .worksheet("Índice") se for o nome da aba
        dados = worksheet.get_all_records()
        return dados

    except Exception as e:
        st.error(f"Não foi possível carregar o índice de processos (Sheets): {e}")
        return None