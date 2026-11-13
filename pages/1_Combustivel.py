import pandas as pd
import streamlit as st
from streamlit.components.v1 import html

from economiza.api import DIAS_MAXIMO, TIPOS_COMBUSTIVEL, EconomizaAPIError, filtrar_bairro
from economiza.mapa import criar_mapa, para_geojson
from economiza.municipios import codigo_ibge
from economiza.ui import aviso_modo_demo, buscar_combustivel, rodape, seletor_municipio

# Streamlit roda este arquivo de cima para baixo A CADA interação do usuário.
# Guia didático com os conceitos usados aqui: docs/GUIA_STREAMLIT.md

# Título da aba do navegador, ícone e largura da página (sempre o primeiro comando st.*).
st.set_page_config(page_title="Combustível · Pechincha Pronta", page_icon="⛽", layout="wide")
st.title("⛽ Preço de combustível")
aviso_modo_demo()

# st.form agrupa os campos: o script só roda de novo quando o botão de envio é clicado,
# e não a cada letra digitada no bairro.
with st.form("consulta_combustivel"):
    c1, c2, c3 = st.columns([2, 2, 1])
    with c1:
        cidade = seletor_municipio("cidade_combustivel")
    with c2:
        bairro = st.text_input("Bairro (opcional)")
    with c3:
        dias = st.number_input("Últimos dias", 1, DIAS_MAXIMO, 7)
    tipo_nome = st.radio("Combustível", list(TIPOS_COMBUSTIVEL), horizontal=True)
    consultar = st.form_submit_button("Consultar", type="primary")

# `consultar` é True apenas na execução disparada pelo clique no botão.
if consultar:
    try:
        with st.spinner("Consultando a API…"):
            # st.session_state guarda o resultado entre execuções; sem ele, a tabela
            # sumiria ao trocar de aba. buscar_combustivel usa cache (economiza/ui.py).
            st.session_state["postos"] = buscar_combustivel(
                TIPOS_COMBUSTIVEL[tipo_nome], codigo_ibge(cidade), int(dias)
            )
        st.session_state["postos_filtro"] = (cidade, bairro, tipo_nome)
    except EconomizaAPIError as erro:
        st.error(f"Não foi possível consultar a API. {erro}")
        st.session_state.pop("postos", None)

if "postos" in st.session_state:
    cidade, bairro, tipo_nome = st.session_state["postos_filtro"]
    postos = filtrar_bairro(st.session_state["postos"], bairro)
    if postos.empty:
        st.info("Nenhuma nota fiscal encontrada para essa combinação de município, bairro e combustível.")
    else:
        # Um registro por posto: o da nota mais recente.
        postos = (
            postos.sort_values("data_venda", ascending=False)
            .drop_duplicates("cnpj")
            .sort_values("valor_declarado")
            .reset_index(drop=True)
        )
        preco = postos["valor_declarado"]
        st.subheader(f"{tipo_nome} em {cidade.title()}" + (f" · bairro {bairro}" if bairro else ""))
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Postos", len(postos))
        m2.metric("Menor preço", f"R$ {preco.min():.2f}")
        m3.metric("Mediana", f"R$ {preco.median():.2f}")
        m4.metric("Maior preço", f"R$ {preco.max():.2f}",
                  delta=f"+R$ {preco.max() - preco.min():.2f} vs. menor", delta_color="inverse")

        # st.tabs cria abas; o conteúdo de cada uma vai dentro do bloco `with`.
        aba_tabela, aba_mapa = st.tabs(["Tabela", "Mapa"])
        colunas = ["estabelecimento", "valor_declarado", "valor_venda", "data_venda",
                   "bairro", "logradouro", "numero", "latitude", "longitude"]
        tabela = postos[[c for c in colunas if c in postos]]
        with aba_tabela:
            st.dataframe(
                tabela, hide_index=True, use_container_width=True,
                column_config={
                    "estabelecimento": "Posto", "bairro": "Bairro", "logradouro": "Endereço",
                    "numero": "Nº", "latitude": "Lat.", "longitude": "Lon.",
                    "valor_declarado": st.column_config.NumberColumn("Preço (R$/un.)", format="R$ %.2f"),
                    "valor_venda": st.column_config.NumberColumn("Valor da venda", format="R$ %.2f"),
                    "data_venda": st.column_config.DatetimeColumn("Última nota", format="DD/MM/YYYY HH:mm"),
                },
            )
        with aba_mapa:
            mapa = criar_mapa(postos, "valor_declarado")
            if mapa is None:
                st.info("Nenhum posto com coordenadas para mostrar no mapa.")
            else:
                st.caption("🔴 menor preço · 🔵 demais postos. Passe o mouse para ver o preço.")
                # O mapa é feito com folium (Leaflet) e inserido na página como HTML.
                html(mapa.get_root().render(), height=560)

        d1, d2 = st.columns(2)
        d1.download_button("Baixar CSV", tabela.to_csv(index=False).encode("utf-8"),
                           "combustivel.csv", "text/csv")
        d2.download_button("Baixar GeoJSON (QGIS)", para_geojson(tabela, list(tabela.columns)),
                           "combustivel.geojson", "application/geo+json")

rodape()
