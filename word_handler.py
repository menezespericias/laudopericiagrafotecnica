from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from num2words import num2words
import os
import re
from typing import List, Dict, Any 
from io import BytesIO

# --- FUNÇÕES DE UTILIDADE (REFINADAS) ---

def substituir_em_paragrafo(paragrafo, dados: dict):
    # Placeholders que serão tratados como LISTAS (não substituição simples)
    LIST_PLACEHOLDERS = ["AUTORES", "REUS"] 
    
    texto_original = paragrafo.text
    
    if any(f"[{lp}]" in texto_original for lp in LIST_PLACEHOLDERS):
        return

    for chave, valor in dados.items():
        # Trata chaves com espaço, convertendo-as para a notação de placeholder do template
        placeholder = f"[{chave.upper().replace(' ', '_')}]" 
        
        if placeholder in texto_original:
            # Substitui placeholders de FLS. com o mesmo texto (Ex: [NUMEROS] em 1. Apresentação)
            if chave.upper() == 'ID_NOMEACAO_FLS':
                texto_original = texto_original.replace("[NUMEROS]", str(valor))
                paragrafo.text = texto_original # Atualiza o parágrafo antes de quebrar para run
                
            valor_str = str(valor) if not isinstance(valor, list) else ""
            
            if valor_str:
                for run in paragrafo.runs:
                    if placeholder in run.text:
                        run.text = run.text.replace(placeholder, valor_str)
                        
def substituir_em_tabela(tabela, dados: dict):
    for row in tabela.rows:
        for cell in row.cells:
            for paragrafo in cell.paragraphs:
                substituir_em_paragrafo(paragrafo, dados)

def inserir_lista_no_paragrafo(doc, marcador, lista: List[str]):
    placeholder = f"[{marcador.upper()}]"
    
    if not isinstance(lista, list) or not lista:
        return

    for paragrafo in doc.paragraphs:
        if placeholder in paragrafo.text:
            
            paragrafo.text = paragrafo.text.replace(placeholder, "")
            
            for item in lista:
                # Insere o item como um novo parágrafo antes do placeholder
                novo_paragrafo = paragrafo.insert_paragraph_before(f"- {item}")
                
            return

def inserir_imagens_em_secao(doc: Document, titulo: str, adendos: List[Dict[str, Any]], prefixo: str):
    """Insere o título da seção e as imagens dos adendos."""
    if not adendos:
        return
        
    doc.add_heading(titulo, level=2)
    
    for i, adendo in enumerate(adendos):
        legenda = adendo.get("legenda", f"{prefixo} {i+1}")
        file_obj = adendo.get("imagem_obj")
        
        if file_obj:
            try:
                # Insere a imagem
                doc.add_picture(file_obj, width=Inches(6))
                
                # Adiciona a legenda
                doc.add_paragraph(legenda, style='Caption') 
                
            except Exception as e:
                # Em caso de erro com a imagem (pode ocorrer se o objeto não for mais válido)
                doc.add_paragraph(f"ERRO: Não foi possível inserir a imagem: {legenda}. {e}")

# --- FUNÇÕES DE GERAÇÃO DE CONTEÚDO DINÂMICO ---

def gerar_bloco_documentos_questionados(doc: Document, dados: dict):
    """Gera a lista de Documentos Questionados (4.1) no corpo do laudo, substituindo os placeholders 0 a 5."""
    docs = dados.get('DOCUMENTOS_QUESTIONADOS', [])
    
    for i in range(6):
        placeholder_tipo = f"[TIPO_DOCUMENTO_{i}]"
        placeholder_num = f"[NÚMERO DO CONTRATO_{i}]"
        placeholder_data = f"[DATA_DOCUMENTO_{i}]" if i == 0 else f"[DATA_{i}]"
        placeholder_fls = f"[FLS_DOCUMENTOS_{i}]" if i == 0 else f"[NÚMEROS DAS FOLHAS_{i}]"
        
        texto_doc = ""
        if i < len(docs):
            d = docs[i]
            texto_doc = f"{d['tipo']}, nº {d['numero']}, datado de {d['data']}, fls. {d['fls']}."
        
        # Procura e substitui todos os placeholders para este documento
        for paragrafo in doc.paragraphs:
            if placeholder_tipo in paragrafo.text:
                if texto_doc:
                    # Tenta substituir o bloco completo (Documento X: [TIPO_DOCUMENTO_X]...)
                    padrao_completo = re.compile(r"Documento\s+" + str(i+1) + r":\s*" + re.escape(placeholder_tipo) + r"(.*)")
                    if padrao_completo.search(paragrafo.text):
                        paragrafo.text = re.sub(padrao_completo, f"Documento {i+1}: {texto_doc}", paragrafo.text)
                    else:
                        paragrafo.text = paragrafo.text.replace(placeholder_tipo, d['tipo'])
                        paragrafo.text = paragrafo.text.replace(placeholder_num, d['numero'])
                        paragrafo.text = paragrafo.text.replace(placeholder_data, d['data'])
                        paragrafo.text = paragrafo.text.replace(placeholder_fls, d['fls'])
                else:
                    # Remove a linha se não houver documento
                    paragrafo.text = "" 

def gerar_bloco_padroes_encontrados(doc: Document, dados: dict):
    """Gera a lista de Padrões Encontrados nos Autos (4.2.B)."""
    placeholder_base = "[TIPO_DOCUMENTO] – Fls. [NÚMEROS], datado de [DATA]."
    padroes = dados.get('PADROES_ENCONTRADOS', [])
    
    # Encontra o parágrafo que contém o placeholder do Documento 1 em 4.2.B
    paragrafo_encontrado = None
    paragrafos_a_remover = []
    
    for p in doc.paragraphs:
        if "Documento 1:" in p.text and placeholder_base in p.text:
            paragrafo_encontrado = p
            paragrafos_a_remover.append(p)
        elif "Documento 2:" in p.text and placeholder_base in p.text:
            paragrafos_a_remover.append(p)

    if not paragrafo_encontrado:
        return

    # Remove os parágrafos de Documento 2 e 3 (se existirem)
    for p_rem in paragrafos_a_remover[1:]:
        p_rem.text = ""

    for i, p in enumerate(padroes):
        texto_padrao = f"Documento {i+1}: {p['tipo']} – Fls. {p['fls']}, datado de {p['data']}."
        
        if i == 0:
            paragrafo_encontrado.text = texto_padrao
        else:
            paragrafo_encontrado.insert_paragraph_before(texto_padrao)


# --- FUNÇÃO PRINCIPAL DE GERAÇÃO ---

def gerar_laudo(
    caminho_modelo: str, 
    caminho_saida: str, 
    dados: dict, 
    adendos: List[Dict[str, Any]] # Para o Bloco 6
):
    
    doc = Document(caminho_modelo)
        
    # --- 1. Pré-Cálculos e Extensos ---
    
    # Cálculos para campos por extenso
    for campo in ["NUM_ESPECIMES", "NUM_LAUDAS"]:
        if dados.get(campo) and isinstance(dados[campo], str) and dados[campo].isdigit():
            num = int(dados[campo])
            dados[f"{campo}_EXTENSO"] = num2words(num, lang='pt_BR').upper() 
        else:
            dados[f"{campo}_EXTENSO"] = ""

    # Campos de texto livre que viram lista
    dados['AUTORES'] = [a.strip() for a in dados.get('autor', '').split('\n') if a.strip()]
    dados['REUS'] = [r.strip() for r in dados.get('reu', '').split('\n') if r.strip()]
    
    # Define os primeiros nomes e substitui placeholders de nome no dicionário para substituição simples
    dados['PRIMEIRO_AUTOR'] = dados['AUTORES'][0] if dados['AUTORES'] else "Autor(a) Não Informado(a)"
    dados['NOME COMPLETO DO RÉU'] = dados['REUS'][0] if dados['REUS'] else "Réu Não Informado"
    dados['NOME DO AUTOR'] = dados['PRIMEIRO_AUTOR']
    dados['NOME COMPLETO DO PERITO'] = dados.get('PERITO', '')
    dados['NÚMERO DE REGISTRO'] = dados.get('NUMERO_REGISTRO', '')

    # --- 2. Geração de Blocos Dinâmicos de Texto ---
    
    # Conclusão Dinâmica
    dados['BLOCO_CONCLUSAO_DINAMICO'] = gerar_bloco_conclusao_dinamico(dados)
    
    # Respostas aos Quesitos
    dados['BLOCO_QUESITOS_AUTOR'] = gerar_bloco_respostas_quesitos(dados, 'Autor')
    dados['BLOCO_QUESITOS_REU'] = gerar_bloco_respostas_quesitos(dados, 'Réu')
    
    # --- 3. Substituição em Parágrafos e Tabelas (Geral) ---
    
    for paragrafo in doc.paragraphs:
        
        # 3.1. Substituição do cabeçalho (Resumo)
        if "[NUMERO DO PROCESSO]Autor: [nome do autor]Réu: [nome do réu]" in paragrafo.text:
            texto_resumo = f"{dados.get('numero_processo', '')} Autor: {dados.get('PRIMEIRO_AUTOR', '')} Réu: {dados.get('NOME COMPLETO DO RÉU', '')}"
            paragrafo.text = paragrafo.text.replace(f"Processo: [NUMERO DO PROCESSO]Autor: [nome do autor]Réu: [nome do réu]", f"Processo: {texto_resumo}")
        
        # 3.2. Substituição de campos simples (inclui os novos: VARA, NUMERO_REGISTRO, NUM_ESPECIMES, etc.)
        substituir_em_paragrafo(paragrafo, dados)

    for tabela in doc.tables:
        substituir_em_tabela(tabela, dados)

    # --- 4. Inserção de Listas e Conteúdo Estruturado ---
    
    # 4.1. Inserção dos Documentos Questionados (4.1)
    gerar_bloco_documentos_questionados(doc, dados)
    
    # 4.2. Inserção dos Padrões Encontrados (4.2.B)
    gerar_bloco_padroes_encontrados(doc, dados)

    # 4.3. Inserção de Adendos Gráficos (Bloco 6)
    inserir_imagens_em_secao(doc, "6. ADENDOS GRÁFICOS", adendos, "Adendo")

    doc.save(caminho_saida)