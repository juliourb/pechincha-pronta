# Pechincha Pronta 🛒

[![testes](https://github.com/juliourb/pechincha-pronta/actions/workflows/testes.yml/badge.svg)](https://github.com/juliourb/pechincha-pronta/actions/workflows/testes.yml)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Streamlit](https://img.shields.io/badge/streamlit-app-FF4B4B)
[![Licença: MIT](https://img.shields.io/badge/licen%C3%A7a-MIT-green)](LICENSE)

Aplicativo em **Streamlit** que consulta a API pública **Economiza Alagoas** (SEFAZ-AL) para
descobrir **onde está mais barato** comprar em cada município alagoano, com base nas
**notas fiscais eletrônicas** emitidas pelos estabelecimentos.

- ⛽ **Combustível**: preço por posto, menor/mediana/maior preço do município e mapa.
- 🍖 **Cesta de churrasco**: monte a cesta (itens + quantidades + marca) e veja o
  estabelecimento com o **menor total**, apenas entre os que vendem a cesta completa.
- 🗺️ **Exportação CSV e GeoJSON** (EPSG:4326), pronta para abrir no QGIS.
- 🧪 **Modo demonstração**: sem token, o app roda com dados **fictícios**, para que
  qualquer pessoa possa testar a interface.

App publicado: https://pechincha-pronta.streamlit.app

**Tecnologias:** Python · Streamlit · pandas · requests · folium (Leaflet) · pytest · GitHub Actions

| Combustível | Cesta de churrasco |
|---|---|
| ![Consulta de combustível](docs/combustivel.png) | ![Cesta de churrasco](docs/churrasco.png) |

<sub>Capturas feitas em modo demonstração: nomes, preços e posições são fictícios.</sub>

## Streamlit em 1 minuto

O app é feito com [Streamlit](https://streamlit.io), que transforma um script Python em
página web, sem HTML nem JavaScript. Quatro ideias explicam o código deste projeto:

| Conceito | Em poucas palavras | Onde aparece |
|---|---|---|
| **Reexecução** | a cada clique, o script roda inteiro de novo, de cima para baixo | todas as páginas |
| **`st.form`** | agrupa campos e só roda ao clicar no botão de envio | formulários de consulta |
| **`st.session_state`** | "memória" que sobrevive às reexecuções (por usuário) | resultados das consultas |
| **`st.cache_data`** | guarda o resultado de funções lentas, como chamadas à API | `economiza/ui.py` |

O passo a passo, com trechos reais do código, testes com `AppTest` e publicação no Streamlit
Community Cloud, está no **[Guia de Streamlit](docs/GUIA_STREAMLIT.md)**.

## Como funciona

```text
Streamlit (Inicio.py, pages/)
        │  escolhas do usuário
        ▼
economiza/ui.py ── cache de 15 min (st.cache_data)
        │
        ▼
economiza/api.py ── POST /combustivel/pesquisa e /produto/pesquisa
        │            (token no header AppToken, paginação, timeout, erros tratados)
        ▼
pandas DataFrame ── economiza/cesta.py (menor preço por item e loja, total da cesta)
                 └─ economiza/mapa.py  (mapa folium e GeoJSON)
```

**Regra da cesta** (`economiza/cesta.py`): para cada estabelecimento e item, fica o menor
preço (em empate, a nota mais recente). O subtotal é `preço × quantidade`, e só entram
estabelecimentos que têm **todos** os itens. Os itens são pesquisados pela descrição e pelos
códigos **NCM** (Nomenclatura Comum do Mercosul), conferidos na tabela NCM vigente
(`data/Tabela_NCM_Vigente_20240406.xlsx`).

## Rodando localmente

Requer Python 3.10 ou superior.

```bash
git clone https://github.com/juliourb/pechincha-pronta.git
```

```bash
cd pechincha-pronta
```

```bash
python -m venv .venv
```

```bash
source .venv/bin/activate   # no Windows: .venv\Scripts\activate
```

```bash
pip install -r requirements-dev.txt
```

```bash
streamlit run Inicio.py
```

Sem token, o app abre em **modo demonstração**. Para usar dados reais, veja abaixo.

### Token da API

O token é pessoal e gratuito: solicite à SEFAZ-AL pelo e-mail `api@sefaz.al.gov.br`,
conforme o [manual do desenvolvedor](https://economizaalagoas.sefaz.al.gov.br/desenvolvedor.htm).
Depois, configure-o de **uma** destas formas (nunca no código):

- arquivo `.streamlit/secrets.toml` (já está no `.gitignore`), a partir do exemplo:

  ```bash
  cp .streamlit/secrets.toml.example .streamlit/secrets.toml
  ```

- variável de ambiente:

  ```bash
  export ECONOMIZA_AL_TOKEN="seu-token"
  ```

- no **Streamlit Community Cloud**: *App settings → Secrets*, com a linha
  `ECONOMIZA_AL_TOKEN = "seu-token"` (passo a passo da publicação na seção 11 do
  [Guia de Streamlit](docs/GUIA_STREAMLIT.md#11-publicar-de-graça-no-streamlit-community-cloud)).

Se o endereço da API mudar, ele pode ser trocado sem alterar o código pela variável
`ECONOMIZA_AL_BASE_URL`.

## Erros comuns

| Mensagem no app | O que significa | O que fazer |
|---|---|---|
| Faixa amarela "Modo demonstração" | O token não foi encontrado | Configure `ECONOMIZA_AL_TOKEN` (veja acima) |
| "O token da API foi recusado" (HTTP 401/403) | Token inválido ou revogado | Peça um novo token à SEFAZ-AL |
| "O serviço da SEFAZ-AL está fora do ar…" (HTTP 500, `SHORTCIRCUIT`) | O *gateway* da SEFAZ cortou o acesso ao serviço, que está falhando ou sobrecarregado | Nada a corrigir no app: espere e tente mais tarde. O app já repete a consulta 2 vezes antes de desistir |
| "Não foi possível conectar…" | Sem resposta da API (rede ou tempo esgotado) | Tente mais tarde |

A API funciona por `http://`: na porta HTTPS, o servidor apresenta um certificado de outro
domínio, então não troque o endereço para `https://`.

## Testes

```bash
pytest -q
```

São 30 testes, todos sem acesso à rede: cliente da API com respostas simuladas (paginação,
erros HTTP, timeout), regras da cesta, mapa/GeoJSON e testes de ponta a ponta das páginas com
`streamlit.testing` em modo demonstração. O GitHub Actions roda a suíte a cada push
(Python 3.10 e 3.12).

## Estrutura

```text
Inicio.py                 página inicial
pages/1_Combustivel.py    consulta de combustível
pages/2_Churrasco.py      cesta de churrasco
economiza/                lógica reutilizável (sem Streamlit, exceto ui.py)
  api.py                  cliente da API Economiza Alagoas
  cesta.py                NCMs da cesta e cálculo do menor total
  mapa.py                 mapa folium e exportação GeoJSON
  municipios.py           102 municípios de AL e códigos IBGE
  demo.py                 dados fictícios para o modo demonstração
  ui.py                   componentes e cache compartilhados
tests/                    pytest
docs/                     capturas de tela e guia de Streamlit
data/                     tabela NCM e dados auxiliares (SINESP) para estudos futuros
```

## Limitações

- Só aparecem estabelecimentos que emitiram nota fiscal no período consultado (até 10 dias).
- O preço é o da nota mais recente e pode diferir do preço atual no local.
- O mapa depende das coordenadas registradas na nota, que podem faltar ou ser imprecisas.
- O NCM agrupa produtos parecidos (todos os cortes bovinos desossados têm o mesmo código).
  Sem escolher a descrição, o app usa a opção mais barata, o que pode comparar coisas
  diferentes (por exemplo, uma lata de cerveja com uma dose em um bar).

## Histórico

| Versão | O que mudou |
|---|---|
| 2.0 | Publicado como repositório aberto. Código reorganizado no pacote `economiza/`; token fora do código; correções na cesta (NCMs duplicados, itens com o mesmo NCM misturados, paginação com filtro de bairro); tratamento de erros e timeout; cache; mapa sem chave de API; exportação CSV/GeoJSON; modo demonstração; testes e CI. |
| 1.5 (alpha) | Consultas de combustível e cesta de churrasco. |

## Contribuindo

Sugestões e correções são bem-vindas: abra uma *issue* ou um *pull request*. Antes de enviar,
rode `pytest -q`. Nunca inclua tokens no código ou nos commits.

## Licença e termos de uso

Código sob a [licença MIT](LICENSE). Os dados consultados são públicos e pertencem à SEFAZ-AL;
este é um aplicativo informativo, desenvolvido como estudo de Python sobre a API Economiza
Alagoas, sem garantia sobre a precisão dos dados.
