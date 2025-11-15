import os
from PIL import Image

def salvar_imagens_temporarias(imagens):
    caminhos = []
    os.makedirs("assets", exist_ok=True)
    for i, img in enumerate(imagens):
        caminho = f"assets/temp_img_{i}.png"
        image = Image.open(img)
        image.save(caminho)
        caminhos.append(caminho)
    return caminhos