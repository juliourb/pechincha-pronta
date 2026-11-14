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

1. **Busca pelo nome, sem NCM.** A API exige uma descrição na pesquisa (o NCM só pode ir como
   complemento; manual do desenvolvedor, seção 6.1). Cada item é consultado por um termo
   ("FEIJAO", "CAFE", "OLEO SOJA"; a carne usa PATINHO, COXAO, CHA DENTRO e CHA FORA), **sem
   filtrar pelo NCM**. Uma sondagem em Batalha, Piranhas e Penedo mostrou que lojas pequenas
   cadastram NCM errado com frequência (pão francês como "preparação alimentícia", banana com
   NCM de alface): sem o filtro, as lojas com tomate em Penedo passaram de 8 para 17, e com
   farinha de 14 para 28.
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

### Decisões tomadas a partir dos dados reais (1ª coleta, nov/2026)

A primeira coleta estadual (58.642 ofertas) mostrou como as notas fiscais descrevem os produtos.
As regras foram ajustadas assim:

| Situação encontrada | Decisão |
|---|---|
| Unidade com sufixo (`KG0001`, `KG9`, `UN0001`) | Considera só as letras: `KG0001` = quilo. Isso recuperou carnes e pães vendidos por kg |
| Leite com "INT" ou só "UHT", sem o tipo | Aceito como integral (o UHT sem indicação é o integral; semi e desnatado vêm escritos) |
| Açúcar sem tipo ("ACUCAR CORURIPE 1KG") | Aceito como cristal; demerara, mascavo e refinado continuam excluídos por nome |
| Banana pacovan | Aceita como prata (pacovan é uma variedade da prata); fator 1,2 |
| Banana vendida por unidade | Dúzia = 12 × preço da unidade |
| Pão francês vendido por unidade, sem peso | Peso padrão de 50 g por pão (R$/kg = preço ÷ 0,05) |
| Café ou manteiga com peso sem unidade ("CAFE SANTA CLARA 250") | Número final de 250, 500 ou 1000 (café) ou 200 e 500 (manteiga) é lido como gramas |
| Cápsulas e solúvel (Dolce Gusto, Nescafé) | Excluídos do café em pó |

Com essas regras, as lojas com a cesta completa passaram de 44 para 57, e a cesta mediana de
**Maceió ficou em R$ 660,27**, contra **R$ 661,69 do DIEESE** em outubro de 2026, uma
diferença de 0,2%.

### Como separar o item de quem só cita o nome

A busca da API também devolve produtos que apenas citam o termo: biscoito "manteiga",
sardinha "com tomate", sabonete "café". A regra é:

- se o **NCM da nota é o correto** do item, basta a palavra do item aparecer na descrição
  (aceita abreviações como "MANT", "ACUC", "LEIT" e marca na frente);
- se o **NCM é outro**, a palavra precisa **abrir** a descrição ("TOMATE KG" entra;
  "EXT DE TOMATE" não). Prefixos de cadastro ("COD: 111 -", "FP ") são ignorados;
- o que não passa é "outro produto" e nem é guardado; o que é o item mas de outro tipo
  (arroz parboilizado, leite desnatado) fica guardado como "fora da especificação".

### Mecanismos de acurácia

Todas as camadas abaixo ficam em `economiza/produtos.py` e valem igualmente para a cesta básica,
a cesta de churrasco e qualquer módulo novo.

Identificar um produto pelo nome é um problema de classificação de texto. As camadas abaixo
se somam; cada uma pega um tipo de erro diferente.

| Camada | O que resolve | Exemplo |
|---|---|---|
| **Palavra do item** (com abreviações) | A busca da API traz produtos que só citam o termo | biscoito "manteiga" não é manteiga |
| **Cabeça da descrição** | Produto *feito com* o item: o nome do item aparece, mas a primeira palavra é outra | "HAMB BOV PICANHA 180G", "LING SABOR PICANHA", "CARNE DO SOL COXAO MOLE" |
| **Lista de exclusão por tipo** | É o item, mas de outro tipo | arroz parboilizado, leite desnatado, café solúvel |
| **NCM como reforço** | Com o NCM certo, a regra é mais tolerante; com NCM errado, mais rígida | "FARINHA PINHEIRO" só vale com NCM de farinha de mandioca |
| **Faixa de embalagem do varejo** | Sachês e atacado distorcem o preço por kg | açúcar de 5 g ou saco de 50 kg, arroz de 30 kg |
| **Consenso por código de barras** | Lojas descrevem o mesmo produto de formas diferentes; a decisão passa a ser a da maioria | "ACUC DEM PINDOR" (demerara abreviado) rejeitado porque as outras lojas escrevem "DEMERARA" |
| **Semelhança de texto (*fuzzy*)** | Erros de digitação no nome do item | "MANTEGA" aceita como manteiga; "BANANADA" não passa por banana |
| **Preço atípico** | Erro de cadastro ou de leitura do tamanho | preço por kg 3 vezes acima ou abaixo da mediana do item |

**Sobre *fuzzy matching*:** medir semelhança entre textos corrige grafias diferentes da *mesma*
palavra. Ele não resolve o caso do hambúrguer de picanha, porque ali a palavra está escrita
certa: o problema é de sentido (qual é o produto e qual é o ingrediente). Por isso o *fuzzy*
entra só para erros de digitação, e o caso do hambúrguer é tratado pela regra da cabeça.

**Auditoria na 1ª coleta (30,5 mil ofertas aceitas):** nenhum hambúrguer, molho ou extrato entre
os aceitos da cesta básica. As camadas novas mudaram a decisão de 2% das ofertas: 84 embalagens
fora do varejo, cerca de 200 rejeições pelo consenso do código de barras e pela cabeça da
descrição. O valor da cesta mudou menos de 0,1%. O erro do hambúrguer estava na cesta de
churrasco, que tinha regras mais simples e agora usa as mesmas camadas.

**Limite:** as regras são listas mantidas à mão. A aba *Diagnóstico* de cada cesta mostra o que
foi aceito e descartado, e serve para encontrar casos novos. Um passo seguinte possível é
classificar as descrições distintas com um modelo de linguagem e guardar o resultado como
dicionário revisado.

## 3. Cesta do município

Para comparar municípios, a cesta **não exige que uma única loja venda tudo**. Como no DIEESE,
o preço de cada item é o típico do lugar, e o pão pode vir da padaria e a carne do açougue:

- **cesta do município** = Σ quantidade do decreto × **mediana**, entre as lojas do município,
  do preço do item (usando a opção mais barata de cada loja);
- **cesta econômica** = a mesma soma com o **percentil 10** dos preços (comprar cada item onde
  é barato; o percentil é menos sensível a erros de cadastro que o mínimo);
- **itens estimados**: se o município não tem nenhuma nota de até 3 itens, o preço deles é
  estimado pela mediana do estado, e o município aparece marcado. Com mais de 3, fica sem valor.

Na 1ª coleta, isso levou a cobertura de 15 municípios (com alguma loja completa) para 73
(31 com os 12 itens próprios e 42 com itens estimados).

## 4. Cesta numa única loja

Para cada estabelecimento e item, o app calcula o menor, o mediano e o maior preço-base
entre as ofertas da loja. Então:

- **menor cesta** = Σ quantidade do decreto × preço mais baixo do item na loja;
- **cesta típica** = idem com o preço mediano;
- **maior cesta** = idem com o preço mais alto.

A distância entre a menor e a maior cesta mostra **quanto a escolha da marca pesa dentro da
mesma loja**. Só tem valor de cesta o estabelecimento que vende **todos** os itens selecionados.

## 5. Indicadores

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

## 6. Diferenças em relação ao DIEESE

| | DIEESE | Pechincha Pronta |
|---|---|---|
| Coleta | pesquisadores em uma amostra de lojas, quatro semanas por mês | todas as notas fiscais emitidas no período (1 a 10 dias) |
| Preço do item | média de três marcas por loja | menor, mediano e maior preço da loja |
| Resultado | uma cesta média por capital | uma cesta por estabelecimento, em qualquer município |
| Tipos de loja | supermercado, feira, açougue e padaria, ponderados | só as lojas que emitem NF-e e vendem todos os itens |

Por isso a comparação com o valor do DIEESE é **uma referência, não uma validação**.

## 7. Escala estadual

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

## 8. Limitações conhecidas

- **Descrições das notas fiscais não são padronizadas.** Abreviações fora das regras
  (por exemplo, "PTO BOV" para patinho) são descartadas. Use a aba Diagnóstico para encontrar
  esses casos e ajustar as regras.
- **Pão francês e outros produtos de padaria** podem ser vendidos por unidade ("UN"), sem peso
  na descrição. Esses casos são descartados por falta de tamanho.
- **Leite em caixa com 12 unidades** depende de a descrição indicar a quantidade ("C/12" ou
  "12X1L").
- **Pão francês é o principal gargalo.** Na 1ª coleta, faltava em 156 das lojas com 10 ou
  mais itens da cesta. Provavelmente parte das padarias de supermercado registra o pão com
  outro código ou descrição. Retirar o item na página Cesta básica mostra o efeito.
- **Período.** A API devolve as notas dos últimos *n* dias, então o resultado é
  um retrato do período, não um índice mensal.

## Fontes

- BRASIL. Decreto-Lei nº 399, de 30 de abril de 1938.
- SEFAZ/AL. *Projeto Economiza Alagoas: Manual de Orientação do Desenvolvedor*, versão 1.0,
  março de 2023. (Critérios de pesquisa, datas em UTC, e a indicação de que os dados são
  "livres para uso particular ou comercial".)
- DIEESE. *Metodologia da Pesquisa Nacional da Cesta Básica de Alimentos*. Agosto de 2025.
  https://www.dieese.org.br/metodologia/metodologiaCestaBasica2025.pdf
- DIEESE. *Pesquisa Nacional da Cesta Básica de Alimentos: outubro de 2026*.
  https://www.dieese.org.br/analisecestabasica/2026/202610cestabasica.pdf
- BRASIL. Decreto nº 12.797, de dezembro de 2025 (salário mínimo de R$ 1.621,00).
- Receita Federal. Tabela NCM vigente.
