import streamlit as st

from economiza.ui import aviso_modo_demo, rodape

st.set_page_config(page_title="Pechincha Pronta", page_icon="🛒")

st.title("Pechincha Pronta 🛒")
st.caption("Consulta de preços por município em Alagoas · versão 2.1")
aviso_modo_demo()

st.write(
    "Encontre onde está mais barato a partir das **notas fiscais eletrônicas** emitidas "
    "em Alagoas, usando a API pública Economiza Alagoas da SEFAZ-AL."
)

col1, col2, col3 = st.columns(3)
with col1:
    st.page_link("pages/1_Combustivel.py", label="Combustível", icon="⛽")
    st.caption("Preço por posto, estatísticas do município e mapa.")
with col2:
    st.page_link("pages/2_Churrasco.py", label="Cesta de churrasco", icon="🍖")
    st.caption("Monte a cesta e veja o estabelecimento com o menor total.")
with col3:
    st.page_link("pages/3_Cesta_basica.py", label="Cesta básica", icon="🧺")
    st.caption("Cesta do Decreto-Lei 399 (DIEESE) por loja, com análise e comparação.")
st.page_link("pages/4_Panorama.py", label="Panorama de Alagoas", icon="🗺️")
st.caption("A cesta básica nos 102 municípios: ranking, mapa e histórico, com coletas automáticas a cada 10 dias.")

st.header("Como usar")
st.markdown(
    """
- Escolha o **município** (obrigatório) e, se quiser, filtre pelo **bairro** — o filtro ignora
  acentos e aceita parte do nome.
- Na cesta de churrasco, a quantidade multiplica o preço da unidade de venda: para 500 g de
  picanha vendida por kg use `0,5`; para um pacote de farofa use `1`.
- Escolher a marca/descrição de cada item deixa a comparação mais justa (veja limitações).
- Os resultados podem ser baixados em **CSV** ou **GeoJSON** (abre direto no QGIS).
"""
)

st.header("Limitações")
st.markdown(
    """
- Só aparecem estabelecimentos que emitiram nota fiscal no período consultado (até 10 dias).
- O preço exibido é o da nota mais recente e pode diferir do preço atual no local.
- O mapa só mostra estabelecimentos com coordenadas na nota; as posições podem ser imprecisas.
- Sem escolher a descrição, o app pega o produto **mais barato** do mesmo código NCM — por
  exemplo, sem escolher a cerveja ele pode comparar uma lata com uma dose em um bar.
"""
)

st.header("Termos de uso")
st.markdown(
    "Aplicativo informativo, desenvolvido como estudo de Python sobre a API Economiza Alagoas. "
    "Não há garantia sobre a precisão dos dados exibidos."
)

rodape()
