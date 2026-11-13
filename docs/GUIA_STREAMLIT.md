# Guia de Streamlit (com exemplos deste projeto)

Este guia explica, em linguagem simples, os conceitos de Streamlit usados no Pechincha Pronta.
Para cada conceito há um trecho real do código. Se você sabe Python e pandas, já tem o
necessário: no Streamlit, **não é preciso escrever HTML, CSS nem JavaScript**.

## 1. A ideia central: o script roda de novo a cada clique

Um app Streamlit é um **script Python comum**, executado de cima para baixo. A diferença é
que, **a cada interação** (clicar num botão, mudar um campo), o Streamlit **roda o script
inteiro de novo** e redesenha a página.

```text
usuário muda um campo ──► Streamlit roda o arquivo .py do início ao fim ──► página atualizada
```

Isso explica quase tudo o que vem a seguir:

- variáveis comuns **somem** a cada execução, por isso existe o `st.session_state` (seção 4);
- consultas lentas seriam repetidas a cada clique, por isso existe o `st.cache_data` (seção 5);
- vários campos disparariam várias execuções, por isso existe o `st.form` (seção 3).

## 2. Widgets: cada campo é uma função que devolve o valor

Em Streamlit, um campo de entrada é uma função. Ela desenha o campo **e** devolve o que o
usuário escolheu, como uma variável qualquer:

```python
# pages/1_Combustivel.py
bairro = st.text_input("Bairro (opcional)")               # devolve um texto
dias = st.number_input("Últimos dias", 1, DIAS_MAXIMO, 7)  # devolve um número
tipo_nome = st.radio("Combustível", list(TIPOS_COMBUSTIVEL), horizontal=True)
```

Para exibir resultados, também bastam funções:

| Função | O que mostra | Onde é usada |
|---|---|---|
| `st.title`, `st.markdown`, `st.caption` | textos | todas as páginas |
| `st.metric` | número em destaque (menor preço, mediana…) | combustível e churrasco |
| `st.dataframe` | tabela interativa de um DataFrame do pandas | combustível e churrasco |
| `st.tabs` | abas ("Tabela", "Mapa") | combustível e churrasco |
| `st.download_button` | botão para baixar CSV/GeoJSON | combustível e churrasco |
| `st.warning`, `st.info`, `st.error` | caixas de aviso | modo demo, erros da API |

O `st.dataframe` aceita `column_config`, que muda o nome e o formato das colunas sem alterar
o DataFrame:

```python
column_config={
    "valor_declarado": st.column_config.NumberColumn("Preço (R$/un.)", format="R$ %.2f"),
    "data_venda": st.column_config.DatetimeColumn("Última nota", format="DD/MM/YYYY HH:mm"),
}
```

## 3. `st.form`: agrupar campos e só rodar ao clicar

Sem formulário, cada tecla digitada no bairro faria o script rodar de novo. Dentro de um
`st.form`, o Streamlit **espera o clique no botão de envio** para rodar com todos os valores
de uma vez:

```python
with st.form("consulta_combustivel"):
    cidade = seletor_municipio("cidade_combustivel")
    bairro = st.text_input("Bairro (opcional)")
    consultar = st.form_submit_button("Consultar", type="primary")  # True só no clique

if consultar:
    ...  # só aqui a API é chamada
```

## 4. `st.session_state`: a memória entre execuções

Como o script roda de novo a cada clique, o resultado de uma consulta sumiria assim que o
usuário trocasse de aba ou mudasse uma quantidade. O `st.session_state` é um **dicionário que
sobrevive entre execuções** (um por usuário/aba do navegador):

```python
# pages/2_Churrasco.py
if consultar:
    df = buscar_cesta(itens, codigo_ibge(cidade), int(dias))
    st.session_state["cesta"] = {"df": df, "itens": itens, ...}   # guarda

if "cesta" not in st.session_state:          # ainda não consultou?
    st.info("Escolha os itens e clique em Consultar preços.")
    st.stop()                                 # encerra esta execução aqui

consulta = st.session_state["cesta"]          # recupera nas execuções seguintes
```

É por isso que, na cesta, você pode mudar quantidades e marcas e o total é recalculado na hora,
**sem chamar a API de novo**: os dados já estão guardados, e só o cálculo é refeito.

## 5. `st.cache_data`: não repetir consultas lentas

O decorador `@st.cache_data` guarda o resultado de uma função. Se ela for chamada de novo
**com os mesmos argumentos**, o Streamlit devolve o resultado guardado, sem executá-la:

```python
# economiza/ui.py
@st.cache_data(ttl=15 * 60, show_spinner=False)   # validade de 15 minutos
def buscar_combustivel(tipo: int, codigo_ibge: int, dias: int) -> pd.DataFrame:
    return obter_cliente().pesquisar_combustivel(tipo, codigo_ibge, dias)
```

- `ttl` (*time to live*) é o tempo de validade. Os preços vêm de notas fiscais e não mudam a
  cada segundo, então 15 minutos é um bom equilíbrio.
- Diferente do `session_state`, o cache é **compartilhado entre todos os usuários**: se duas
  pessoas consultam gasolina em Maceió, a API é chamada uma vez só.
- Use `st.cache_data` para funções que devolvem dados (DataFrames, listas, dicionários).

## 6. Várias páginas: a pasta `pages/`

O arquivo passado ao `streamlit run` é a página inicial. Todo arquivo `.py` dentro da pasta
`pages/` vira automaticamente uma página no menu lateral:

```text
Inicio.py                → página inicial
pages/1_Combustivel.py   → "Combustivel" no menu
pages/2_Churrasco.py     → "Churrasco" no menu
```

O número no começo do nome só define a ordem no menu. Para criar um link entre páginas:

```python
st.page_link("pages/1_Combustivel.py", label="Combustível", icon="⛽")
```

Cada página chama `st.set_page_config(...)` logo no início para definir título da aba,
ícone e largura (`layout="wide"`).

## 7. Mapas com folium

O Streamlit tem `st.map`, mas ele só mostra pontos. Para ter cores (menor preço em vermelho),
popups e tooltips, o projeto monta o mapa com **folium** (biblioteca Python que gera mapas
Leaflet) e insere o HTML na página:

```python
from streamlit.components.v1 import html

mapa = criar_mapa(postos, "valor_declarado")       # economiza/mapa.py devolve um folium.Map
html(mapa.get_root().render(), height=560)          # insere o HTML do mapa na página
```

Os mesmos pontos podem ser baixados em GeoJSON (botão "Baixar GeoJSON (QGIS)") para
análise em SIG.

### Gráficos com plotly

Para gráficos interativos (passar o mouse e ver os valores), a página de cesta básica monta a
figura com **plotly** em `economiza/graficos.py` e a exibe com uma linha:

```python
st.plotly_chart(graficos.composicao_barras(comp), use_container_width=True, theme="streamlit")
```

`theme="streamlit"` faz o gráfico seguir o tema claro/escuro do app.

## 8. Segredos: `st.secrets`

Tokens e senhas **nunca** devem ficar no código. O Streamlit lê o arquivo
`.streamlit/secrets.toml` (que está no `.gitignore`) e o expõe como um dicionário:

```toml
# .streamlit/secrets.toml
ECONOMIZA_AL_TOKEN = "seu-token"
```

```python
# economiza/api.py
token = st.secrets.get("ECONOMIZA_AL_TOKEN")
```

No Streamlit Community Cloud, o mesmo conteúdo é colado em *App settings → Secrets*.

## 9. Configuração visual: `.streamlit/config.toml`

Cores e comportamento da interface ficam em `.streamlit/config.toml`:

```toml
[theme]
primaryColor = "#C62828"   # cor dos botões e destaques
```

## 10. Testar o app sem abrir o navegador

O Streamlit tem um "robô" de testes, o `AppTest`. Ele roda a página, clica nos botões e
permite conferir o que apareceu na tela:

```python
# tests/test_app.py
from streamlit.testing.v1 import AppTest

at = AppTest.from_file("pages/1_Combustivel.py").run()  # abre a página
at.button[0].click().run()                              # clica em "Consultar"
assert at.metric[0].value == "12"                       # confere o nº de postos
```

## 11. Publicar de graça no Streamlit Community Cloud

1. Entre em https://share.streamlit.io com sua conta do GitHub.
2. *Create app* → escolha o repositório `juliourb/pechincha-pronta`, a branch `main` e o
   arquivo principal `Inicio.py`.
3. Em *Advanced settings*, escolha Python 3.11 ou 3.12 e, em *Secrets*, cole
   `ECONOMIZA_AL_TOKEN = "seu-token"`.
4. *Deploy*. O Streamlit instala o `requirements.txt` e gera o endereço do app. A cada push na
   `main`, o app é atualizado sozinho.

No plano gratuito, o app "dorme" após alguns dias sem acesso e leva alguns segundos para
acordar na próxima visita.

## Para continuar estudando

- Documentação oficial: https://docs.streamlit.io
- Modelo de execução (seção 1): https://docs.streamlit.io/develop/concepts/architecture/run-your-app
- Cache (seção 5): https://docs.streamlit.io/develop/concepts/architecture/caching
- Session State (seção 4): https://docs.streamlit.io/develop/concepts/architecture/session-state
- Várias páginas (seção 6): https://docs.streamlit.io/develop/concepts/multipage-apps
