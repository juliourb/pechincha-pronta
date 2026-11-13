"""Gráficos (plotly) da cesta básica.

Regras de visual: uma série por gráfico, na mesma cor (azul); o destaque usa laranja
e SEMPRE vem acompanhado de texto, para não depender só da cor. As cores seguem
uma paleta validada para daltonismo.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from .cesta_basica import ITENS_POR_NOME

AZUL = "#2a78d6"
LARANJA = "#eb6834"
CINZA = "#b9b8b3"
_LAYOUT = dict(margin=dict(l=8, r=8, t=48, b=8), hoverlabel=dict(namelength=-1), showlegend=False)


def _moeda(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def distribuicao_cestas(cestas: pd.DataFrame, referencia: dict | None = None) -> go.Figure:
    """Valor da cesta em cada loja completa. Com poucas lojas, cada loja é um ponto
    (um histograma com 4 valores não diz nada); com muitas, um histograma."""
    completas = cestas[cestas["completa"]]
    valores = completas["cesta_min"]
    if len(completas) < 15:
        nomes = completas["estabelecimento"].fillna(completas["cnpj"]).astype(str)
        fig = go.Figure(go.Scatter(
            x=valores, y=[0] * len(valores), mode="markers",
            marker=dict(color=AZUL, size=16, opacity=0.85, line=dict(color="white", width=2)),
            text=nomes, hovertemplate="<b>%{text}</b><br>R$ %{x:.2f}<extra></extra>"))
        fig.update_yaxes(visible=False, range=[-1, 1])
        altura = 260
    else:
        fig = go.Figure(go.Histogram(
            x=valores, marker=dict(color=AZUL, line=dict(color="white", width=2)), nbinsx=20,
            hovertemplate="R$ %{x}<br>%{y} estabelecimento(s)<extra></extra>"))
        fig.update_yaxes(title="Estabelecimentos")
        altura = 380
    mediana = valores.median()
    # Os dois rótulos ficam no topo, cada um "virado" para fora, para não se sobreporem.
    lado_mediana = "right" if not referencia or mediana <= referencia["valor"] else "left"
    fig.add_vline(x=mediana, line=dict(color="#52514e", width=2, dash="dot"),
                  annotation=dict(text=f"mediana {_moeda(mediana)} ", xanchor=lado_mediana,
                                  yanchor="bottom", y=1, yref="paper"))
    if referencia:
        fig.add_vline(x=referencia["valor"], line=dict(color=LARANJA, width=2),
                      annotation=dict(text=f" DIEESE {referencia['periodo']}: {_moeda(referencia['valor'])}",
                                      xanchor="left" if lado_mediana == "right" else "right",
                                      yanchor="bottom", y=1, yref="paper", font=dict(color=LARANJA)))
    fig.update_layout(title="Quanto custa a cesta em cada estabelecimento (opção mais barata de cada item)",
                      xaxis_title="Valor da cesta (R$)", height=altura, bargap=0.05, **_LAYOUT)
    fig.update_layout(margin=dict(l=8, r=8, t=70, b=40))
    return fig


def faixa_por_estabelecimento(cestas: pd.DataFrame, limite: int = 25) -> go.Figure:
    """Menor, típica e maior cesta de cada loja: a barra mostra quanto a escolha das
    marcas pesa dentro do mesmo estabelecimento."""
    dados = cestas[cestas["completa"]].nsmallest(limite, "cesta_min").iloc[::-1]
    nomes = dados["estabelecimento"].fillna(dados["cnpj"]).astype(str)
    fig = go.Figure()
    # Uma linha cinza por loja, ligando a menor à maior cesta (None separa os segmentos).
    xs, ys = [], []
    for nome, menor, maior in zip(nomes, dados["cesta_min"], dados["cesta_max"]):
        xs += [menor, maior, None]
        ys += [nome, nome, None]
    fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color=CINZA, width=6), hoverinfo="skip"))
    fig.add_trace(go.Scatter(
        x=dados["cesta_min"], y=nomes, mode="markers", name="Menor cesta",
        marker=dict(color=AZUL, size=11, line=dict(color="white", width=2)),
        customdata=dados[["cesta_tipica", "cesta_max", "amplitude"]],
        hovertemplate="<b>%{y}</b><br>Menor: R$ %{x:.2f}<br>Típica: R$ %{customdata[0]:.2f}"
                      "<br>Maior: R$ %{customdata[1]:.2f}<br>Diferença: R$ %{customdata[2]:.2f}<extra></extra>"))
    fig.add_trace(go.Scatter(
        x=dados["cesta_max"], y=nomes, mode="markers", name="Maior cesta",
        marker=dict(color="white", size=10, line=dict(color=AZUL, width=2)), hoverinfo="skip"))
    fig.update_layout(title=f"Menor e maior cesta por estabelecimento (até {limite} mais baratos)",
                      xaxis_title="Valor da cesta (R$)  ·  ● opção mais barata de cada item   ○ mais cara",
                      height=max(320, 26 * len(dados) + 120), **_LAYOUT)
    return fig


def composicao_barras(tabela: pd.DataFrame) -> go.Figure:
    """Quanto cada item pesa na cesta típica (R$ e %)."""
    t = tabela.iloc[::-1]
    fig = go.Figure(go.Bar(
        x=t["gasto"], y=t["item"], orientation="h", marker=dict(color=AZUL, cornerradius=4),
        text=[f"{_moeda(g)} · {p:.0f}%" for g, p in zip(t["gasto"], t["participacao"])],
        textposition="outside", cliponaxis=False,
        customdata=t[["quantidade", "preco_base_mediano", "unidade"]],
        hovertemplate="<b>%{y}</b><br>%{customdata[0]} × R$ %{customdata[1]:.2f}/%{customdata[2]}"
                      "<br>= R$ %{x:.2f}<extra></extra>"))
    fig.update_layout(title="Quanto cada item pesa na cesta (preço mediano entre as lojas completas)",
                      xaxis_title="Gasto mensal (R$)", height=420, **_LAYOUT)
    fig.update_xaxes(range=[0, t["gasto"].max() * 1.3])
    return fig


def dispersao_barras(tabela: pd.DataFrame) -> go.Figure:
    """Quanto o preço mais alto supera o mais baixo entre as lojas, item a item (%)."""
    t = tabela.iloc[::-1].assign(acima=lambda d: 100 * (d["razao_maior_menor"] - 1))
    fig = go.Figure(go.Bar(
        x=t["acima"], y=t["item"], orientation="h", marker=dict(color=AZUL, cornerradius=4),
        text=[f"+{v:.0f}%" for v in t["acima"]], textposition="outside", cliponaxis=False,
        customdata=t[["menor", "mediano", "maior", "unidade", "estabelecimentos"]],
        hovertemplate="<b>%{y}</b> (R$/%{customdata[3]})<br>Menor: R$ %{customdata[0]:.2f}"
                      "<br>Mediano: R$ %{customdata[1]:.2f}<br>Maior: R$ %{customdata[2]:.2f}"
                      "<br>%{customdata[4]} estabelecimentos<extra></extra>"))
    fig.update_layout(title="Onde comparar compensa mais: quanto a loja mais cara cobra a mais que a mais barata",
                      xaxis_title="Diferença entre o maior e o menor preço (%)", height=420, **_LAYOUT)
    fig.update_xaxes(range=[0, max(1, t["acima"].max()) * 1.2], ticksuffix="%")
    return fig


def mapa_cobertura(matriz: pd.DataFrame, limite: int = 40) -> go.Figure:
    """Estabelecimento × item: quem vende o quê (✓) e o que falta (–)."""
    m = matriz.head(limite)
    z = m.astype(int).values
    texto = [["✓" if v else "–" for v in linha] for linha in m.values]
    fig = go.Figure(go.Heatmap(
        z=z, x=list(m.columns), y=list(m.index), text=texto, texttemplate="%{text}",
        colorscale=[[0, "#efeeea"], [1, AZUL]], showscale=False, xgap=2, ygap=2, zmin=0, zmax=1,
        hovertemplate="%{y}<br>%{x}: %{text}<extra></extra>"))
    fig.update_layout(title="Quais itens cada estabelecimento vende (✓) ou não (–)",
                      height=max(320, 24 * len(m) + 140), **_LAYOUT)
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(side="bottom", tickangle=-30)
    return fig


def sensibilidade_barras(tabela: pd.DataFrame) -> go.Figure:
    """Quantas lojas a mais teriam a cesta completa se o item saísse da cesta."""
    t = tabela.iloc[::-1]
    maximo = t["ganho"].max()
    unico = maximo > 0 and (t["ganho"] == maximo).sum() == 1  # só destaca se houver um único "vilão"
    fig = go.Figure(go.Bar(
        x=t["ganho"], y=t["item"], orientation="h",
        marker=dict(color=[LARANJA if unico and g == maximo else AZUL for g in t["ganho"]], cornerradius=4),
        text=[f"+{g}" + ("  ← o que mais limita" if unico and g == maximo else "") for g in t["ganho"]],
        textposition="outside", cliponaxis=False,
        customdata=t[["cobertura_pct", "unico_item_faltando"]],
        hovertemplate="<b>%{y}</b><br>Vendido em %{customdata[0]:.0f}% das lojas"
                      "<br>Único item faltando em %{customdata[1]} loja(s)<extra></extra>"))
    fig.update_layout(title="Se o item saísse da cesta, quantas lojas a mais ficariam completas?",
                      xaxis_title="Estabelecimentos a mais com cesta completa", height=420, **_LAYOUT)
    fig.update_xaxes(range=[0, max(1, t["ganho"].max()) * 1.5], dtick=1)
    return fig


def unidade_legivel(item: str) -> str:
    return {"kg": "R$/kg", "L": "R$/L", "dz": "R$/dúzia"}[ITENS_POR_NOME[item].unidade]


def ranking_divergente(rank: pd.DataFrame, n: int = 10) -> go.Figure:
    """Os n municípios mais baratos e os n mais caros, em % da mediana estadual dos municípios."""
    sel = pd.concat([rank.head(n), rank.tail(n)]).drop_duplicates("municipio").sort_values("pct_vs_estado", ascending=False)
    cores = [AZUL if v < 0 else LARANJA for v in sel["pct_vs_estado"]]
    fig = go.Figure(go.Bar(
        x=sel["pct_vs_estado"], y=sel["nome"], orientation="h", marker=dict(color=cores, cornerradius=4),
        text=[f"{v:+.0f}% · {_moeda(m)}" for v, m in zip(sel["pct_vs_estado"], sel["mediana"])],
        textposition="outside", cliponaxis=False,
        customdata=sel[["com_cesta_completa"]],
        hovertemplate="<b>%{y}</b><br>%{x:+.1f}% vs. estado<br>%{customdata[0]} lojas com a cesta<extra></extra>"))
    fig.add_vline(x=0, line=dict(color="#52514e", width=1))
    limite = max(5, sel["pct_vs_estado"].abs().max() * 1.45)
    fig.update_layout(title=f"Os {n} municípios mais baratos (azul) e os {n} mais caros (laranja)",
                      xaxis_title="Cesta mediana em relação à mediana dos municípios (%)",
                      height=max(360, 24 * len(sel) + 120), **_LAYOUT)
    fig.update_xaxes(range=[-limite, limite], ticksuffix="%")
    return fig


def dispersao_concorrencia(rank: pd.DataFrame) -> go.Figure:
    """Cada ponto é um município: número de lojas com a cesta × preço mediano."""
    fig = go.Figure(go.Scatter(
        x=rank["com_cesta_completa"], y=rank["mediana"], mode="markers", text=rank["nome"],
        marker=dict(color=AZUL, size=11, opacity=0.8, line=dict(color="white", width=1.5)),
        hovertemplate="<b>%{text}</b><br>%{x} lojas com a cesta<br>Mediana R$ %{y:.2f}<extra></extra>"))
    fig.update_layout(title="Mais lojas, cesta mais barata? (cada ponto é um município)",
                      xaxis_title="Lojas com a cesta completa (escala logarítmica)",
                      yaxis_title="Cesta mediana (R$)", height=420, **_LAYOUT)
    fig.update_xaxes(type="log")
    return fig


def serie_historica(indice: list[dict]) -> go.Figure:
    """Mediana estadual da cesta em cada coleta."""
    pontos = [(c["data_coleta"], c["estado"]["cesta_mediana"], c["estado"]["lojas_com_cesta"])
              for c in indice if c.get("estado", {}).get("cesta_mediana")]
    datas, medianas, lojas = zip(*pontos) if pontos else ([], [], [])
    fig = go.Figure(go.Scatter(
        x=list(datas), y=list(medianas), mode="lines+markers", customdata=list(lojas),
        line=dict(color=AZUL, width=2), marker=dict(size=9, color=AZUL, line=dict(color="white", width=2)),
        hovertemplate="%{x}<br>Mediana R$ %{y:.2f}<br>%{customdata} lojas com a cesta<extra></extra>"))
    fig.update_layout(title="Cesta básica mediana em Alagoas, por coleta",
                      yaxis_title="R$", height=360, **_LAYOUT)
    return fig
