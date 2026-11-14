# Coleta estadual e histórico da cesta básica

A cada 10 dias, um robô (GitHub Actions) calcula a cesta básica nos 102 municípios de Alagoas
e guarda o resultado. Isso serve para três coisas:

- **Registro:** cada coleta fica arquivada com a data, e não muda depois de publicada.
- **Série histórica:** a API só devolve os últimos 10 dias, então o histórico só existe se for
  guardado. Ele começa na primeira coleta.
- **Velocidade:** a página *Panorama de Alagoas* lê os arquivos prontos e abre na hora.

## Como funciona

```text
GitHub Actions (todo dia às 04:23 de Maceió)
  └─ a última coleta tem 10 dias ou mais?  não → encerra
       └─ sim → scripts/coleta_estadual.py (102 municípios × 16 consultas = 1.632, 3 municípios por vez)
            ├─ ofertas.parquet     cada oferta da API, classificada (dados brutos + resultado)
            ├─ lojas.parquet       a cesta de cada estabelecimento
            ├─ municipios.parquet  indicadores por município
            ├─ precos.parquet      preço de cada item em cada município (mediana, P10, lojas)
            └─ manifesto.json      linhas e bytes de cada arquivo, resumo do estado
       → publica a Release "coleta-AAAA-MM-DD" com esses arquivos
       → atualiza coletas.json na Release fixa "indice" (histórico de todas as coletas)

App (página Panorama) → lê coletas.json e os Parquet pelos links públicos de download
```

**Por que 10 dias:** a API devolve no máximo as notas dos 10 dias anteriores. Com coletas a
cada 10 dias, as janelas se encaixam sem buracos nem sobreposição. O workflow roda todos os
dias e só coleta quando completa 10 dias da anterior. Por isso o intervalo é exato, sem os
saltos de fim de mês que um agendamento por dia do mês teria.

**Por que Releases do GitHub:** os arquivos não entram no histórico do git, então o repositório
não incha e o app não é republicado a cada coleta. Cada coleta tem um link permanente, e o
download não consome o limite de chamadas da API do GitHub. Segundo a documentação do GitHub,
cada arquivo de uma Release pode ter até 2 GiB.

**Por que Parquet:** é um formato colunar e comprimido (zstd). É lido por pandas, R e DuckDB,
e o QGIS também abre Parquet. O DuckDB permite consultar os arquivos em SQL direto pelo link,
sem baixar tudo para a memória:

```sql
SELECT municipio, item, median(preco_base) AS preco_mediano
FROM 'https://github.com/juliourb/pechincha-pronta/releases/download/coleta-2026-11-23/ofertas.parquet'
WHERE motivo = 'ok'
GROUP BY ALL ORDER BY municipio, item;
```

As ofertas guardam os **dados brutos** da API (descrição, GTIN, NCM, unidade e preços), além do
resultado da classificação. Assim, se as regras da cesta mudarem, as coletas antigas podem ser
reclassificadas sem consultar a API de novo.

## Ativação (uma vez)

1. No GitHub, abra o repositório e vá em **Settings → Secrets and variables → Actions →
   New repository secret**.
2. Nome: `ECONOMIZA_AL_TOKEN`; valor: o token da API. Salve.
3. Em **Actions → coleta-cesta-basica → Run workflow**, marque *forçar* e rode a primeira
   coleta. Ela deve levar de 15 a 40 minutos.
4. Ao terminar, a Release `coleta-AAAA-MM-DD` aparece na página do repositório, e a página
   Panorama passa a mostrar os dados reais.

Sem o *secret*, o workflow apenas pula a coleta e deixa um aviso no resumo da execução, sem
falhar todo dia. Como segunda proteção, o script roda com `--exigir-token` e se recusa a
publicar dados fictícios como se fossem reais.

## Como garantir que a coleta não pare

O que pode fazer a coleta parar, e o que já está preparado para cada caso:

| Risco | Proteção |
|---|---|
| O GitHub desativa agendamentos de repositórios públicos após **60 dias sem atividade** | O último passo do workflow reativa o agendamento pela API do GitHub a cada execução diária, o que reinicia a contagem. É a mesma técnica de ações populares de *keepalive*. |
| O token da SEFAZ expira ou é revogado | A coleta falha (HTTP 401/403) e o GitHub envia **e-mail de falha** para você. Atualize o *secret* `ECONOMIZA_AL_TOKEN`. |
| A API da SEFAZ fica fora do ar no dia | O workflow tenta de novo no dia seguinte, porque a última coleta continua com 10 dias ou mais. Perde-se no máximo um dia de notas. |
| Mais da metade das consultas falha | A coleta não é publicada, para não gravar dados incompletos; a falha gera e-mail. |
| Ninguém percebe que parou | A página Panorama mostra um aviso quando a última coleta tem mais de 12 dias, e o selo **coleta** no README fica vermelho quando a última execução falhou. |

**Para receber os avisos por e-mail**, confira no GitHub em *Settings (do seu perfil) →
Notifications → System → Actions* se a opção de notificar execuções com falha está ligada. Os
avisos de workflows agendados vão para quem modificou o agendamento por último, no caso
você, porque os commits estão no seu nome.

**Se mesmo assim o agendamento for desativado**, a aba Actions mostra um aviso com o botão
*Enable workflow*. As coletas já publicadas nunca se perdem: o histórico fica nas Releases,
e o próximo dado entra assim que o workflow voltar a rodar. Só os dias parados ficam sem dado.

## Tamanho dos arquivos

O que domina é `ofertas.parquet`. As tabelas `lojas` e `municipios` somam poucos por cento.

**Bytes por oferta (medidos aqui):**

| Simulação | Bytes por oferta |
|---|---:|
| Dados do modo demonstração (descrições muito repetidas) | ~13 |
| Simulação com alta variedade (descrições, lojas, CNPJs e GTINs todos diferentes) | ~40 |

Os dados reais devem ficar entre esses dois valores: as descrições se repetem bastante, mas
menos que no modo demonstração. Para planejar, use o valor mais alto, 40 bytes por oferta.

**Projeção (40 bytes por oferta, 36,5 coletas por ano):**

| Ofertas por coleta (hipótese) | Por coleta | Por ano | Em 5 anos |
|---:|---:|---:|---:|
| 30 mil | 1,2 MB | 44 MB | 0,2 GB |
| 100 mil | 4 MB | 146 MB | 0,7 GB |
| 300 mil | 12 MB | 438 MB | 2,2 GB |

**Primeira coleta real (13/11/2026):** 58.642 ofertas em **1,73 MB** (29,5 bytes por oferta,
entre os dois cenários simulados); `lojas` 0,10 MB e `municipios` 0,01 MB. No total, **cerca de
1,9 MB por coleta, ou ~70 MB por ano** (~0,35 GB em 5 anos). A coleta levou 2h43min
(1.938 consultas) e só 1 consulta falhou por tempo esgotado.

O `manifesto.json` de cada coleta registra linhas e bytes de cada arquivo, e a aba
**Dados e tamanho** do Panorama acompanha o crescimento real.

Mesmo no cenário mais alto, o volume é pequeno para Parquet e cabe nas Releases. O app não
sofre com o crescimento, porque baixa só `lojas` e `municipios` da coleta escolhida, que são
pequenos; `ofertas` fica para download e análise. Se um dia o volume crescer muito, o caminho
natural é um banco PostgreSQL/PostGIS ou o MotherDuck (DuckDB na nuvem).

**Uso dos dados:** o manual do desenvolvedor da SEFAZ/AL afirma que "todos os dados fornecidos
são livres para uso particular ou comercial" e recomenda que quem usa muito a API monte uma
base intermediária própria, que é o que esta coleta faz.

## Reclassificar coletas antigas

Como as ofertas guardam os dados brutos, dá para aplicar regras novas a coletas antigas sem
consultar a API: em *Actions → reclassificar-coletas → Run workflow*, informe a tag
(ex.: `coleta-2026-11-13`) ou `todas`. Os arquivos da Release e o índice são substituídos, e o
manifesto ganha o campo `reclassificada_em`. Na primeira coleta, as regras ajustadas com os dados
reais aumentaram as lojas com a cesta completa de 44 para 57.

## Malha municipal

O mapa do Panorama usa `data/malha_municipios_al.geojson`, guardado no repositório. O app não
depende do IBGE estar acessível, porque o servidor do IBGE costuma recusar conexões vindas do
exterior, como as do Streamlit Cloud. Para gerar ou atualizar o arquivo, rode *Actions →
malha-municipal → Run workflow*: ele baixa do IBGE (ou de uma cópia pública), confere os 102
municípios e grava o arquivo no repositório.

## Rodando localmente

```bash
python scripts/coleta_estadual.py --municipios MACEIO ARAPIRACA --saida coleta_teste
```

Para a página Panorama ler coletas locais, organize uma pasta com `coletas.json` na raiz e uma
subpasta por coleta (`coleta-AAAA-MM-DD/`), e aponte para ela:

```bash
PECHINCHA_COLETAS_DIR=minhas_coletas streamlit run Inicio.py
```
