import streamlit as st
import os
import json
from datetime import date, datetime
from num2words import num2words
from typing import List, Dict, Any, Union

# --- Configuração Inicial ---
st.set_page_config(page_title="Laudo Grafotécnico", layout="wide")
DATA_FOLDER = "data"

# --- Carregamento automático do processo selecionado ---
if "process_to_load" in st.session_state and st.session_state["process_to_load"]:
    process_id = st.session_state["process_to_load"]
    json_path = os.path.join(DATA_FOLDER, f"{process_id}.json")
    if os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            dados_carregados = json.load(f)
        for key, value in dados_carregados.items():
            if key not in st.session_state:
                st.session_state[key] = value
        st.success(f"📂 Processo {process_id} carregado com sucesso!")
        st.session_state.process_to_load = None
        st.session_state.editing_etapa_1 = False
        st.rerun()
    else:
        st.error(f"❌ Arquivo JSON para o processo {process_id} não encontrado.")
        st.stop()
else:
    st.warning("Nenhum processo selecionado.")
    st.stop()

# --- Inicialização do Estado de Sessão ---
def init_session_state():
    defaults = {
        "etapas_concluidas": set(),
        "theme": "light",
        "editing_etapa_1": True,
        "num_laudas": 10,
        "num_docs_questionados": 1,
        "documentos_questionados_list": [],
        "quesitos_autor": [],
        "quesitos_reu": [],
        "anexos": [],
        "adendos": [],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

init_session_state()

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
        index=["Em Edição", "Pronto para Conclusão", "Finalizado"].index(
            st.session_state.get("status_processo", "Em Edição")
        )
    )

    st.session_state.objeto_pericia = st.text_area(
        "Objeto da Perícia (resumo)",
        value=st.session_state.get(
            "objeto_pericia",
            "Verificar a autenticidade ou falsidade de assinaturas atribuídas ao(a) [NOME DO AUTOR], aposta no(s) documento(s) [LISTA DE DOCUMENTOS QUESTIONADOS]."
        ),
        height=100
    )

    st.session_state.data_laudo = st.date_input(
        "Data de Encerramento/Entrega do Laudo",
        value=st.session_state.get("data_laudo", date.today())
    )

    if st.button("Concluir Etapa 1 e Salvar", disabled=not st.session_state.get("numero_processo")):
        if st.session_state.numero_processo and st.session_state.autor and st.session_state.reu:
            st.session_state.etapas_concluidas.add(1)
            st.session_state.editing_etapa_1 = False
            with open(f"{DATA_FOLDER}/{st.session_state.numero_processo}.json", "w", encoding="utf-8") as f:
                json.dump(dict(st.session_state), f, ensure_ascii=False, indent=2, default=str)
            st.success("✅ Etapa 1 concluída e dados salvos.")
            st.rerun()
        else:
            st.error("Preencha o Número do Processo, Autor e Réu para continuar.")

# --- ETAPA 2: LISTA DE AUTORES E RÉUS ---
enable_next_steps = 1 in st.session_state.etapas_concluidas

with st.expander("2. Partes do Processo (Lista)", expanded=enable_next_steps and 2 not in st.session_state.etapas_concluidas):
    st.session_state.autores_list = st.text_area(
        "Lista de Autores (um por linha)",
        value=st.session_state.get("autores_list", st.session_state.get("autor", "")),
        help="Use uma linha por nome. O primeiro será usado como nome principal."
    )
    st.session_state.reus_list = st.text_area(
        "Lista de Réus (um por linha)",
        value=st.session_state.get("reus_list", st.session_state.get("reu", "")),
        help="Use uma linha por nome. O primeiro será usado como nome principal."
    )

    if st.button("Concluir Etapa 2"):
        st.session_state.etapas_concluidas.add(2)
        with open(f"{DATA_FOLDER}/{st.session_state.numero_processo}.json", "w", encoding="utf-8") as f:
            json.dump(dict(st.session_state), f, ensure_ascii=False, indent=2, default=str)
        st.success("✅ Etapa 2 concluída e dados salvos.")
        st.rerun()

# --- ETAPA 3: DOCUMENTOS QUESTIONADOS ---
with st.expander("3. Documentos Questionados (PQ)", expanded=enable_next_steps and 3 not in st.session_state.etapas_concluidas):
    st.session_state.num_docs_questionados = st.number_input(
        "Quantos documentos questionados (PQ)?",
        min_value=1,
        value=st.session_state.get("num_docs_questionados", 1)
    )

    while len(st.session_state.documentos_questionados_list) < st.session_state.num_docs_questionados:
        st.session_state.documentos_questionados_list.append({
            "TIPO_DOCUMENTO": "",
            "FLS_DOCUMENTOS": "",
            "RESULTADO": "Autêntico"
        })
    while len(st.session_state.documentos_questionados_list) > st.session_state.num_docs_questionados:
        st.session_state.documentos_questionados_list.pop()

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
                "Conclusão",
                options=["Autêntico", "Falso", "Não Conclusivo"],
                index=["Autêntico", "Falso", "Não Conclusivo"].index(
                    st.session_state.documentos_questionados_list[i]["RESULTADO"]
                ),
                key=f"pq_res_{i}"
            )
        docs_text_list.append(
            f"{st.session_state.documentos_questionados_list[i]['TIPO_DOCUMENTO']} - Fls. {st.session_state.documentos_questionados_list[i]['FLS_DOCUMENTOS']}"
        )

    st.session_state.docs_questionados_text = "\n".join(docs_text_list)

    if st.button("Concluir Etapa 3"):
        st.session_state.etapas_concluidas.add(3)
        with open(f"{DATA_FOLDER}/{st.session_state.numero_processo}.json", "w", encoding="utf-8") as f:
            json.dump(dict(st.session_state), f, ensure_ascii=False, indent=2, default=str)
        st.success("✅ Etapa 3 concluída e dados salvos.")
        st.rerun()

# --- ETAPA 4: PADRÕES DE CONFRONTO (PC) ---
with st.expander("4. Padrões de Confronto (PC)", expanded=enable_next_steps and 4 not in st.session_state.etapas_concluidas):
    st.session_state.num_especimes = st.text_input(
        "Número de espécimes examinados:",
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
        "Análise dos Paradigmas",
        value=st.session_state.get("analise_paradigmas", ""),
        height=150
    )

    if st.button("Concluir Etapa 4"):
        st.session_state.etapas_concluidas.add(4)
        with open(f"{DATA_FOLDER}/{st.session_state.numero_processo}.json", "w", encoding="utf-8") as f:
            json.dump(dict(st.session_state), f, ensure_ascii=False, indent=2, default=str)
        st.success("✅ Etapa 4 concluída e dados salvos.")
        st.rerun()

# --- ETAPA 5: CONFRONTO E CONCLUSÃO ---
with st.expander("5. Confronto Grafoscópico e Conclusão", expanded=enable_next_steps and 5 not in st.session_state.etapas_concluidas):
    st.session_state.confronto_grafoscopico = st.text_area(
        "Confronto Grafoscópico",
        value=st.session_state.get("confronto_grafoscopico", ""),
        height=300
    )

    st.session_state.resultado_final = st.selectbox(
        "Conclusão Principal",
        options=["AUTÊNTICA", "FALSA", "NÃO CONCLUSIVA"],
        index=["AUTÊNTICA", "FALSA", "NÃO CONCLUSIVA"].index(st.session_state.get("resultado_final", "AUTÊNTICA"))
    )

    st.session_state.conclusao_texto = st.text_area(
        "Texto da Conclusão",
        value=st.session_state.get("conclusao_texto", ""),
        height=150
    )

    if st.button("Concluir Etapa 5"):
        st.session_state.etapas_concluidas.add(5)
        with open(f"{DATA_FOLDER}/{st.session_state.numero_processo}.json", "w", encoding="utf-8") as f:
            json.dump(dict(st.session_state), f, ensure_ascii=False, indent=2, default=str)
        st.success("✅ Etapa 5 concluída e dados salvos.")
        st.rerun()

# --- ETAPA 6: QUESITOS (AUTOR E RÉU) ---
with st.expander("6. Resposta aos Quesitos (Autor e Réu)", expanded=enable_next_steps and 6 not in st.session_state.etapas_concluidas):
    st.subheader("Quesitos da Parte Autora")
    st.session_state.fls_quesitos_autor = st.text_input(
        "Fls. dos Quesitos do Autor",
        value=st.session_state.get("fls_quesitos_autor", "")
    )

    num_quesitos_autor = st.number_input("Número de Quesitos do Autor:", min_value=0, value=len(st.session_state.quesitos_autor), key="num_q_autor")

    while len(st.session_state.quesitos_autor) < num_quesitos_autor:
        st.session_state.quesitos_autor.append({"id": len(st.session_state.quesitos_autor) + 1, "quesito": "", "resposta": "", "imagem_obj": None})
    while len(st.session_state.quesitos_autor) > num_quesitos_autor:
        st.session_state.quesitos_autor.pop()

    for i, item in enumerate(st.session_state.quesitos_autor):
        st.markdown(f"**Quesito Autor #{i+1}**")
        colQ, colR = st.columns([1, 1])
        with colQ:
            st.session_state.quesitos_autor[i]["quesito"] = st.text_area(
                "Quesito",
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
        st.session_state.quesitos_autor[i]["imagem_obj"] = st.file_uploader(
            "Imagem (opcional)",
            type=["png", "jpg", "jpeg"],
            key=f"qa_img_{i}"
        )

    st.subheader("Quesitos da Parte Ré")
    st.session_state.fls_quesitos_reu = st.text_input(
        "Fls. dos Quesitos do Réu",
        value=st.session_state.get("fls_quesitos_reu", "")
    )

    num_quesitos_reu = st.number_input("Número de Quesitos do Réu:", min_value=0, value=len(st.session_state.quesitos_reu), key="num_q_reu")

    while len(st.session_state.quesitos_reu) < num_quesitos_reu:
        st.session_state.quesitos_reu.append({"id": len(st.session_state.quesitos_reu) + 1, "quesito": "", "resposta": "", "imagem_obj": None})
    while len(st.session_state.quesitos_reu) > num_quesitos_reu:
        st.session_state.quesitos_reu.pop()

    for i, item in enumerate(st.session_state.quesitos_reu):
        st.markdown(f"**Quesito Réu #{i+1}**")
        colQ, colR = st.columns([1, 1])
        with colQ:
            st.session_state.quesitos_reu[i]["quesito"] = st.text_area(
                "Quesito",
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
        st.session_state.quesitos_reu[i]["imagem_obj"] = st.file_uploader(
            "Imagem (opcional)",
            type=["png", "jpg", "jpeg"],
            key=f"qr_img_{i}"
        )

    if st.button("Concluir Etapa 6"):
        st.session_state.etapas_concluidas.add(6)
        with open(f"{DATA_FOLDER}/{st.session_state.numero_processo}.json", "w", encoding="utf-8") as f:
            json.dump(dict(st.session_state), f, ensure_ascii=False, indent=2, default=str)
        st.success("✅ Etapa 6 concluída e dados salvos.")
        st.rerun()

# --- ETAPA 7: ANEXOS E ADENDOS ---
with st.expander("7. Anexos e Adendos", expanded=enable_next_steps and 7 not in st.session_state.etapas_concluidas):
    st.session_state.anexos_list = st.text_area(
        "Lista de Anexos (texto descritivo)",
        value=st.session_state.get("anexos_list", ""),
        help="Descreva os documentos anexos que não são imagens."
    )

    st.subheader("Upload de Anexos (Imagens ou Arquivos)")
    uploaded_anexos = st.file_uploader(
        "Selecione arquivos para anexar",
        type=["png", "jpg", "jpeg", "pdf", "docx"],
        accept_multiple_files=True
    )

    if uploaded_anexos:
        st.session_state.anexos = []
        for i, file in enumerate(uploaded_anexos):
            st.session_state.anexos.append({
                "NOME": file.name,
                "ARQUIVO": file,
                "DESCRICAO": st.text_input(f"Descrição para {file.name}", key=f"desc_anexo_{i}")
            })

    st.subheader("Upload de Adendos (Somente Imagens)")
    uploaded_adendos = st.file_uploader(
        "Selecione imagens para adendos",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True
    )

    if uploaded_adendos:
        st.session_state.adendos = []
        for i, file in enumerate(uploaded_adendos):
            st.session_state.adendos.append({
                "NOME": file.name,
                "ARQUIVO": file,
                "DESCRICAO": st.text_input(f"Descrição para {file.name}", key=f"desc_adendo_{i}")
            })

    if st.button("Concluir Etapa 7"):
        st.session_state.etapas_concluidas.add(7)
        with open(f"{DATA_FOLDER}/{st.session_state.numero_processo}.json", "w", encoding="utf-8") as f:
            json.dump(dict(st.session_state), f, ensure_ascii=False, indent=2, default=str)
        st.success("✅ Etapa 7 concluída e dados salvos.")
        st.rerun()

# --- ETAPA 8: GERAÇÃO DO LAUDO FINAL ---
with st.expander("8. Encerramento e Geração do Laudo", expanded=enable_next_steps and 8 not in st.session_state.etapas_concluidas):
    st.session_state.num_laudas = st.number_input(
        "Número final de laudas:",
        min_value=1,
        value=st.session_state.get("num_laudas", 10),
        help="Este valor será usado para os placeholders [NUM_LAUDAS] e [NUM_LAUDAS_EXTENSO]."
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
        from word_handler import gerar_laudo

        # Define caminhos
        caminho_modelo = st.session_state.caminho_modelo
        caminho_saida = f"output/Laudo_{st.session_state.numero_processo}.docx"
        os.makedirs("output", exist_ok=True)

        # Prepara dados para substituição
        dados = {
            "NUMERO_DO_PROCESSO": st.session_state.numero_processo,
            "NOME_DO_AUTOR": st.session_state.autor,
            "NOME_DO_REU": st.session_state.reu,
            "OBJETO_DA_PERICIA": st.session_state.objeto_pericia,
            "DATA_LAUDO": st.session_state.data_laudo.strftime("%d de %B de %Y"),
            "AUTORES": st.session_state.autores_list,
            "REUS": st.session_state.reus_list,
            "DOCUMENTOS_QUESTIONADOS_LIST": st.session_state.docs_questionados_text,
            "NUM_ESPECIMES": st.session_state.num_especimes,
            "FLS_PC_A": st.session_state.fls_pc_a,
            "FLS_PC_E": st.session_state.fls_pc_e,
            "ANALISE_PARADIGMAS": st.session_state.analise_paradigmas,
            "CONFRONTO_GRAFOSCOPICO": st.session_state.confronto_grafoscopico,
            "RESULTADO_FINAL": st.session_state.resultado_final,
            "CONCLUSAO_TEXTO": st.session_state.conclusao_texto,
            "FLS_Q_AUTOR": st.session_state.fls_quesitos_autor,
            "FLS_Q_REU": st.session_state.fls_quesitos_reu,
            "ANEXOS_LIST": st.session_state.anexos_list,
            "ASSINATURAS": st.session_state.assinaturas,
            "NUM_LAUDAS": str(st.session_state.num_laudas),
        }

        # Prepara imagens dos quesitos
        quesito_images_list = []
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
                caminho_modelo=caminho_modelo,
                caminho_saida=caminho_saida,
                dados=dados,
                anexos=st.session_state.anexos,
                adendos=st.session_state.adendos,
                quesito_images_list=quesito_images_list
            )
            st.session_state.etapas_concluidas.add(8)
            with open(f"{DATA_FOLDER}/{st.session_state.numero_processo}.json", "w", encoding="utf-8") as f:
                json.dump(dict(st.session_state), f, ensure_ascii=False, indent=2, default=str)
            st.success("✅ Laudo gerado com sucesso!")
            st.markdown(f"📄 [Clique aqui para baixar o laudo gerado]({caminho_saida})")
        except Exception as e:
            st.error(f"❌ Erro ao gerar o laudo: {e}")