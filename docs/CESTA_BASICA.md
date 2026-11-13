# Cesta básica: metodologia

Este documento descreve como o Pechincha Pronta calcula a cesta básica por estabelecimento
a partir das notas fiscais eletrônicas (API Economiza Alagoas, SEFAZ-AL), e em que ponto
o cálculo segue ou se afasta da metodologia do DIEESE.

## 1. Conceito e composição

A cesta segue o **Decreto-Lei nº 399/1938**, ainda em vigor, que fixa as "provisões mínimas"
mensais de um trabalhador adulto por região. **Alagoas está na Região 2**, que tem 12 itens
(não inclui batata). As quantidades e a especificação de cada produto são as usadas pelo DIEESE
na Pesquisa Nacional da Cesta Básica de Alimentos, que inclui Maceió desde abril de 2025.

| Item | Quantidade mensal (Região 2) | Especificação (DIEESE) | NCM pesquisado |
|---|---|---|---|
| Carne | 4,5 kg | bovina de primeira: coxão mole, coxão duro ou patinho, sem osso | 0201.30.00, 0202.30.00 |
| Leite | 6,0 L | integral UHT | 0401.20.10 |
| Feijão | 4,5 kg | carioca | 0713.33.99, 0713.33.19 |
| Arroz | 3,6 kg | agulhinha tipo 1 (branco) | 1006.30.21 |
| Farinha | 3,0 kg | de mandioca (Norte e Nordeste) | 1106.20.00 |
| Tomate | 12,0 kg | comum | 0702.00.00 |
| Pão francês | 6,0 kg | pão francês | 1905.90.90 |
| Café em pó | 300 g | torrado e moído | 0901.21.00 |
| Banana | 90 unidades (7,5 dúzias) | prata ou nanica | 0803.90.00 |
| Açúcar | 3,0 kg | cristal | 1701.99.00, 1701.14.00 |
| Óleo | 750 g | de soja | 1507.90.11 |
| Manteiga | 750 g | manteiga | 0405.10.00 |

Os códigos NCM foram conferidos na Tabela NCM vigente (`data/Tabela_NCM_Vigente_20240406.xlsx`).

## 2. Da nota fiscal ao preço por kg, litro ou dúzia

1. **Busca por NCM.** Para cada item, a API é consultada pelo código NCM, sem descrição. Isso
   traz todas as marcas do produto: a marca não importa.
2. **Filtro pela especificação.** O NCM é mais amplo que o item do DIEESE (o 1905.90.90 inclui
   bolos; o 0201.30.00 inclui picanha). Cada item tem palavras obrigatórias e proibidas na
   descrição: por exemplo, a carne precisa conter patinho, coxão mole ou coxão duro (ou "chã de
   dentro" e "chã de fora"), e o café não pode ser em grão nem em cápsula. As regras estão em
   `economiza/cesta_basica.py` (`ITENS_REGIAO_2`).
3. **Preço por unidade-base.** O tamanho da embalagem é lido na descrição ("5KG", "250G",
   "900ML", "12X1L"). O preço é dividido por ele: arroz de 5 kg a R$ 29,90 vira R$ 5,98/kg.
   Produtos vendidos a granel (unidade KG na nota) já estão por kg.
4. **Banana.** Vendida por kg, é convertida para dúzia com os fatores do DIEESE: × 1,2 para
   a prata e × 1,8 para a nanica.
5. **Óleo.** O decreto fala em 750 g; o óleo é vendido em mililitros. A conversão usa uma
   densidade de 0,92 kg/L (750 g ≈ 0,815 L). *Hipótese do projeto, não do DIEESE.*
6. **Preço usado.** O valor unitário declarado na nota (`valorDeclarado`), equivalente ao
   preço de prateleira.
7. **Preços atípicos.** Uma oferta cujo preço-base fica abaixo de 1/3 ou acima de 3 vezes a
   mediana do item no município é descartada. Isso pega erros de cadastro ou de leitura do
   tamanho da embalagem.

A aba **Diagnóstico** do app mostra cada oferta e o motivo de ter sido aceita ou descartada.

## 3. Cesta por estabelecimento

Para cada estabelecimento e item, o app calcula o menor, o mediano e o maior preço-base
entre as ofertas da loja. Então:

- **menor cesta** = Σ quantidade do decreto × preço mais baixo do item na loja;
- **cesta típica** = idem com o preço mediano;
- **maior cesta** = idem com o preço mais alto.

A distância entre a menor e a maior cesta mostra **quanto a escolha da marca pesa dentro da
mesma loja**. Só tem valor de cesta o estabelecimento que vende **todos** os itens selecionados.

## 4. Indicadores

| Indicador | Cálculo |
|---|---|
| Lojas com a cesta completa | lojas com todos os itens ÷ lojas com ao menos *k* itens (*k* ajustável; evita contar padarias e açougues) |
| Menor, mediana, média e maior cesta | estatísticas da *menor cesta* entre as lojas completas |
| Horas de trabalho | cesta × 220 ÷ salário mínimo (R$ 1.621,00 em 2026), fórmula do DIEESE |
| % do salário mínimo líquido | cesta ÷ (salário mínimo × 0,925), descontada a Previdência (7,5%) |
| Composição | gasto de cada item na cesta, usando o preço mediano entre as lojas completas |
| Variação entre lojas | maior ÷ menor preço-base do item entre as lojas |
| Sensibilidade ("entram e saem") | quantas lojas a mais teriam a cesta completa se o item saísse |

As fórmulas foram conferidas com o boletim do DIEESE de outubro de 2026: a cesta de Maceió,
de R$ 661,69, corresponde a 89h48m de trabalho e a 44,13% do salário mínimo líquido. O mesmo
resultado é verificado nos testes automatizados.

## 5. Diferenças em relação ao DIEESE

| | DIEESE | Pechincha Pronta |
|---|---|---|
| Coleta | pesquisadores em uma amostra de lojas, quatro semanas por mês | todas as notas fiscais emitidas no período (1 a 10 dias) |
| Preço do item | média de três marcas por loja | menor, mediano e maior preço da loja |
| Resultado | uma cesta média por capital | uma cesta por estabelecimento, em qualquer município |
| Tipos de loja | supermercado, feira, açougue e padaria, ponderados | só as lojas que emitem NF-e e vendem todos os itens |

Por isso a comparação com o valor do DIEESE é **uma referência, não uma validação**.

## 6. Escala estadual

O script `scripts/cesta_basica_estado.py` aplica a mesma metodologia a vários municípios, ou
aos 102, e gera `municipios.csv` (indicadores por município, com o código IBGE para juntar à
malha municipal no QGIS) e `lojas.geojson` (pontos dos estabelecimentos).

```bash
python scripts/cesta_basica_estado.py --todos --dias 7 --saida resultados_cesta
```

Possibilidades de análise com esses arquivos:

- municípios com a cesta mediana mais barata e mais cara;
- relação entre o número de estabelecimentos e o preço (concorrência);
- municípios sem nenhuma loja com a cesta completa (indício de acesso restrito a alimentos);
- autocorrelação espacial (Moran) dos valores por município.

## 7. Limitações conhecidas

- **Descrições das notas fiscais não são padronizadas.** Abreviações fora das regras
  (por exemplo, "PTO BOV" para patinho) são descartadas. Use a aba Diagnóstico para encontrar
  esses casos e ajustar as regras.
- **Pão francês e outros produtos de padaria** podem ser vendidos por unidade ("UN"), sem peso
  na descrição. Esses casos são descartados por falta de tamanho.
- **Leite em caixa com 12 unidades** depende de a descrição indicar a quantidade ("C/12" ou
  "12X1L").
- **Período.** A API devolve as notas dos últimos *n* dias, então o resultado é
  um retrato do período, não um índice mensal.

## Fontes

- BRASIL. Decreto-Lei nº 399, de 30 de abril de 1938.
- DIEESE. *Metodologia da Pesquisa Nacional da Cesta Básica de Alimentos*. Agosto de 2025.
  https://www.dieese.org.br/metodologia/metodologiaCestaBasica2025.pdf
- DIEESE. *Pesquisa Nacional da Cesta Básica de Alimentos: outubro de 2026*.
  https://www.dieese.org.br/analisecestabasica/2026/202610cestabasica.pdf
- BRASIL. Decreto nº 12.797, de dezembro de 2025 (salário mínimo de R$ 1.621,00).
- Receita Federal. Tabela NCM vigente.
