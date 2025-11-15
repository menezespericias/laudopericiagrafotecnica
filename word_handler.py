from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from num2words import num2words
import os
import re
from typing import List, Dict, Any # Importações para clareza
from io import BytesIO

# --- FUNÇÕES DE UTILIDADE DE WORD DOCX ---

# 2. FUNÇÃO AUXILIAR DE SUBSTITUIÇÃO EM PARÁGRAFOS
def substituir_em_paragrafo(paragrafo, dados: dict):
    """
    Substitui os placeholders em um parágrafo mantendo a formatação original.
    Adaptado para ignorar placeholders de LISTAS.
    """
    
    # Placeholders que serão tratados como LISTAS (não substituição simples)
    LIST_PLACEHOLDERS = ["[AUTORES]", "[REUS]"] 
    
    texto_original = paragrafo.text
    texto_novo = texto_original
    
    # Verifica se o parágrafo contém placeholders de lista. Se sim, ignora a substituição de texto.
    if any(lp in texto_original for lp in LIST_PLACEHOLDERS):
        return

    for chave, valor in dados.items():
        placeholder = f"[{chave.upper()}]"
        
        # Ignora substituição se o valor for uma lista (já é tratado na função principal)
        if isinstance(valor, list):
            continue
            
        # Converte o valor para string, se necessário
        valor_str = str(valor)
        
        if placeholder in texto_novo:
            # O processamento de runs é complexo, a melhor abordagem é a substituição via regex em um texto plano temporário
            # e depois recriar o parágrafo ou usar uma função que preserva a formatação como a abaixo,
            # mas que requer processamento mais pesado.
            
            # Tentativa de substituição com preservação de formatação:
            if placeholder in paragrafo.text:
                inline = paragrafo.runs
                
                # Mapeia as runs para construir o texto completo
                paragrafo_text = "".join(run.text for run in inline)
                
                # Se a substituição for simples, fazemos no nível do run
                if paragrafo_text.count(placeholder) == 1 and not (paragrafo_text.startswith(placeholder) and paragrafo_text.endswith(placeholder)):
                    
                    # Tenta a substituição direta (mais robusta)
                    if not inline:
                        paragrafo.text = paragrafo.text.replace(placeholder, valor_str)
                    else:
                        for run in inline:
                            if placeholder in run.text:
                                run.text = run.text.replace(placeholder, valor_str)
                                break
                    continue # Vai para o próximo dado

    # Se a substituição simples falhar e o placeholder for o único conteúdo do parágrafo:
    if texto_novo != texto_original:
        paragrafo.text = texto_novo

# 3. FUNÇÃO AUXILIAR DE SUBSTITUIÇÃO EM TABELAS
def substituir_em_tabela(tabela, dados: dict):
    """Substitui os placeholders em todas as células de uma tabela."""
    for linha in tabela.rows:
        for celula in linha.cells:
            for paragrafo in celula.paragraphs:
                substituir_em_paragrafo(paragrafo, dados)

# 4. FUNÇÃO PARA INSERIR LISTA (Como Parágrafos Formatados)
def inserir_lista_no_paragrafo(doc, marcador: str, lista: List[str]):
    """
    Localiza o placeholder do marcador no documento e o substitui por itens da lista
    como novos parágrafos formatados com uma lista simples (Bullet Points).
    """
    placeholder = f"[{marcador.upper()}]"
    
    # 1. Tenta padronizar a lista (espera-se uma lista de strings)
    if not isinstance(lista, list):
        if isinstance(lista, str) and "\n" in lista:
            lista = [item.strip() for item in lista.split("\n") if item.strip()]
        else:
            return

    # 2. Itera sobre os parágrafos para encontrar e substituir o placeholder
    for i, paragrafo in enumerate(doc.paragraphs):
        if placeholder in paragrafo.text:
            
            # Se a lista estiver vazia, apenas remove o placeholder
            if not lista:
                paragrafo.text = paragrafo.text.replace(placeholder, "N/A")
                continue

            # Remove o placeholder do parágrafo original
            paragrafo.text = paragrafo.text.replace(placeholder, "")
            
            # Adiciona os novos itens da lista como parágrafos com estilo de lista
            # OBS: Usar insert_paragraph_before é complicado, é melhor adicionar ao final
            # e depois rearranjar, ou usar o run, mas a lista é melhor em novos parágrafos.
            
            # Adiciona os itens ANTES do parágrafo que contém o placeholder
            p_ref = doc.paragraphs[i] # Referência ao parágrafo que contém o placeholder
            
            for item in reversed(lista): # Inserindo em ordem reversa para aparecer na ordem correta
                novo_paragrafo = p_ref.insert_paragraph_before(item)
                
                try:
                    # Tenta aplicar estilo de Lista (Bullet Points)
                    novo_paragrafo.style = 'List Bullet' 
                except KeyError:
                    # Se o estilo não existir no modelo, ignora
                    pass 
    
    # O parágrafo que tinha o placeholder deve ter sido limpo no loop

# 5. FUNÇÃO PARA INSERIR IMAGENS EM SESSÃO ESPECÍFICA
def inserir_imagens_em_secao(doc, titulo_secao: str, imagens: List[Dict[str, Any]], tipo: str):
    """
    Adiciona um título de seção e insere as imagens em seguida no final do documento,
    usando o objeto UploadedFile diretamente.
    """
    if not imagens:
        return

    doc.add_heading(titulo_secao, level=2)
    
    for i, item in enumerate(imagens):
        # file_obj é o objeto UploadedFile do Streamlit
        file_obj = item.get("imagem_obj") or item.get("file_obj") 
        descricao = item.get("description") or item.get("descricao") or f"{tipo} {item.get('id', i+1)}"
        
        if file_obj:
            
            # Cria um BytesIO (stream de bytes) a partir do UploadedFile
            image_stream = BytesIO(file_obj.getvalue())
            
            # Adiciona a imagem
            doc.add_paragraph().add_run().add_picture(image_stream, width=Inches(6))
            
            # Adiciona a legenda (caption)
            caption = doc.add_paragraph(descricao)
            caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
            
            doc.add_paragraph("\n") # Espaço entre imagens

# 1. FUNÇÃO PRINCIPAL DE GERAÇÃO (REVISADA)
def gerar_laudo(
    caminho_modelo: str, 
    caminho_saida: str, 
    dados: dict, 
    anexos: List[Dict[str, Any]], 
    adendos: List[Dict[str, Any]], 
    quesito_images_list: List[Dict[str, Any]] # Lista de imagens dos quesitos
):
    doc = Document(caminho_modelo)
    
    # Adicionar versões por extenso dos números para uso automático
    num_exames = dados.get("NUM_EXAMES")
    if num_exames and isinstance(num_exames, str) and num_exames.isdigit():
        num = int(num_exames)
        # Garante que a versão por extenso esteja em maiúsculas
        dados["NUM_EXAMES_EXTENSO"] = num2words(num, lang='pt_BR').upper() 
    
    # 1. Substituição de campos de texto em parágrafos
    for paragrafo in doc.paragraphs:
        # Tenta inserir a lista de Autores/Réus onde o placeholder estiver
        if "[AUTORES]" in paragrafo.text and 'AUTORES' in dados:
            inserir_lista_no_paragrafo(doc, "AUTORES", dados['AUTORES'])
            
        elif "[REUS]" in paragrafo.text and 'REUS' in dados:
            inserir_lista_no_paragrafo(doc, "REUS", dados['REUS'])
            
        else:
            # Para os demais placeholders
            substituir_em_paragrafo(paragrafo, dados)

    # 2. Substituição de campos de texto em tabelas
    for tabela in doc.tables:
        substituir_em_tabela(tabela, dados)
        
    # 3. Inserção de ADENDOS GRÁFICOS (no corpo do laudo, se necessário, ou em anexo)
    # Por padrão, vamos inserir no final, conforme a Etapa 6 sugere.
    inserir_imagens_em_secao(doc, "Adendos Gráficos e Ilustrações", adendos, "Adendo")
    
    # 4. Inserção de IMAGENS DOS QUESITOS (no final do laudo)
    inserir_imagens_em_secao(doc, "Imagens dos Quesitos", quesito_images_list, "Quesito")
    
    # 5. Inserção de DOCUMENTOS ANEXADOS (no final do laudo)
    inserir_imagens_em_secao(doc, "Documentos Anexados (Peças de Exame)", anexos, "Anexo")

    # Salva o documento final
    doc.save(caminho_saida)