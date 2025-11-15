import win32com.client
import os
from PIL import ImageGrab
import time

def gerar_imagem_tabela_excel(caminho_arquivo, nome_macro, imagem_saida):
    excel = win32com.client.Dispatch("Excel.Application")
    excel.Visible = False
    wb = excel.Workbooks.Open(os.path.abspath(caminho_arquivo))

    try:
        # Executa a macro (ex: "CopiarTabela")
        excel.Application.Run(f"{wb.Name}!{nome_macro}")
        time.sleep(1)  # Aguarda a cópia para a área de transferência

        # Captura a imagem da área de transferência
        img = ImageGrab.grabclipboard()
        if img:
            img.save(imagem_saida)
            return imagem_saida
        else:
            raise Exception("Nenhuma imagem encontrada na área de transferência.")
    finally:
        wb.Close(False)
        excel.Quit()