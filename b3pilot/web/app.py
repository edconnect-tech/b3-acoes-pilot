"""Dashboard Web Local do B3 Ações Pilot (Streamlit + Plotly).

Modo Claro (Clean), Alta Acessibilidade (WCAG 2.2 AA) e Fontes Nativas do Sistema.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

from b3pilot.ledger.db import init_db, get_db_session, Transaction, Position, MonthlyTaxRecord, DividendRecord
from b3pilot.ledger.portfolio import get_portfolio_summary, execute_buy, execute_sell
from b3pilot.ledger.taxes import get_current_tax_summary
from b3pilot.core.screener import run_screener
from b3pilot.core.strategies import compute_indicators
from b3pilot.core.regime import analyze_market_regime
from b3pilot.core.risk import audit_option_spread, calculate_position_size
from b3pilot.data.dividends_feed import scan_upcoming_dividends
from b3pilot.data.universe import get_universe, SMALL_MID_CAPS, BLUE_CHIPS
from b3pilot.data.b3_feed import (
    fetch_ticker_data,
    compute_multi_timeframe_variations,
    get_statusinvest_url,
    get_tradingview_url,
    get_clean_ticker,
    get_base_ticker,
)
from b3pilot.config import TAX_EXEMPTION_LIMIT_MONTHLY, DEFAULT_CAPITAL

# Configuração da Página
st.set_page_config(
    page_title="B3 Ações Pilot - Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Estilização Clean Light Mode (Acessibilidade WCAG 2.2 AA e Fontes de Sistema)
st.markdown(
    """
    <style>
    /* Tipografia nativa do sistema Apple / Web Clean */
    html, body, [class*="css"] {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        color: #1f2937;
    }
    .metric-card {
        background-color: #f9fafb;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 16px;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
    }
    .badge-success {
        background-color: #ecfdf5;
        color: #065f46;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .badge-warning {
        background-color: #fffbeb;
        color: #92400e;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .badge-danger {
        background-color: #fef2f2;
        color: #991b1b;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .legend-box {
        background-color: #f8fafc;
        border-left: 4px solid #3b82f6;
        padding: 12px 16px;
        border-radius: 4px;
        margin-bottom: 16px;
        font-size: 0.9rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

init_db()
session = get_db_session()

# Sidebar
st.sidebar.title("🚀 B3 Ações Pilot")
st.sidebar.markdown("**Assistente de Swing Trade & Proventos**")
st.sidebar.markdown("---")
menu = st.sidebar.radio(
    "Navegação:",
    [
        "📊 Visão Geral da Carteira",
        "🎯 Radar de Oportunidades & Proventos",
        "🛡️ Auditoria de Travas de Baixa & Opções",
        "📈 Análise Gráfica & Variações (1D a 10A)",
        "📚 Guia dos Setups & Estratégias",
        "📜 Histórico & Performance",
        "📑 Gestão Fiscal & DARF",
        "➕ Registrar Ordem",
    ],
)
st.sidebar.markdown("---")
st.sidebar.info("Modo: **Local / Antigravity agy**\n\nIsenção B3: **R$ 20.000,00/mês**")

# Gatekeeper Macro IBOVESPA no Topo
regime = analyze_market_regime()
reg_col1, reg_col2 = st.columns([3, 1])
with reg_col1:
    if regime["status"] == "BULL":
        st.markdown(f'<div class="badge-success" style="font-size:0.95rem; padding:8px 12px; margin-bottom:14px; border:1px solid #10b981;">🟢 <b>REGIME IBOVESPA: {regime["name"]}</b> — {regime["description"]}</div>', unsafe_allow_html=True)
    elif regime["status"] == "CORRECTION":
        st.markdown(f'<div class="badge-warning" style="font-size:0.95rem; padding:8px 12px; margin-bottom:14px; border:1px solid #f59e0b;">🟡 <b>REGIME IBOVESPA: {regime["name"]}</b> — {regime["description"]}</div>', unsafe_allow_html=True)
    elif regime["status"] == "BEAR":
        st.markdown(f'<div class="badge-danger" style="font-size:0.95rem; padding:8px 12px; margin-bottom:14px; border:1px solid #ef4444;">🔴 <b>REGIME IBOVESPA: {regime["name"]}</b> — {regime["description"]}</div>', unsafe_allow_html=True)
    elif regime["status"] == "PANIC":
        st.markdown(f'<div class="badge-danger" style="font-size:0.95rem; padding:8px 12px; margin-bottom:14px; border:2px solid #b91c1c;">🚨 <b>PÂNICO NO IBOVESPA ({regime["ibov_change_pct"]}%)</b> — {regime["description"]}</div>', unsafe_allow_html=True)
    else:
        st.caption(f"Status IBOVESPA: {regime['name']}")

with reg_col2:
    if regime.get("ibov_close"):
        st.caption(f"IBOV: **R$ {regime['ibov_close']:,.0f}** ({regime['ibov_change_pct']:+.2f}%)")

# ==========================================
# 1. VISÃO GERAL DA CARTEIRA
# ==========================================
if menu == "📊 Visão Geral da Carteira":
    st.title("Visão Geral da Custódia")
    summary = get_portfolio_summary(session)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Investido", f"R$ {summary['total_invested']:,.2f}")
    with col2:
        st.metric("Valor a Mercado", f"R$ {summary['current_market_value']:,.2f}")
    with col3:
        pnl = summary["total_unrealized_pnl"]
        pnl_pct = summary["total_unrealized_pnl_pct"]
        st.metric("PnL Não Realizado", f"R$ {pnl:,.2f}", f"{pnl_pct:+.2f}%")
    with col4:
        st.metric("Posições Abertas", f"{summary['num_positions']} ativos")

    st.markdown("### Posições em Aberto")
    if summary["positions"]:
        df_pos = pd.DataFrame(summary["positions"])
        df_pos = df_pos[[
            "ticker", "quantity", "average_price", "current_price",
            "market_value", "unrealized_pnl", "unrealized_pnl_pct",
            "stop_loss", "take_profit", "trailing_stop", "strategy", "entry_date"
        ]]
        df_pos.columns = [
            "Código da Ação", "Quantidade", "Preço Médio (R$)", "Cotação Atual (R$)",
            "Valor a Mercado (R$)", "Resultado Não Realizado (R$)", "Rentabilidade (%)",
            "Stop Loss (R$)", "Alvo / Take Profit (R$)", "Trailing Stop (R$)", "Estratégia", "Data de Entrada"
        ]
        st.dataframe(df_pos, width="stretch")
    else:
        st.info("Nenhuma ação em custódia no momento. Use o menu 'Registrar Ordem' para cadastrar sua primeira compra.")

# ==========================================
# 2. RADAR DE OPORTUNIDADES & PROVENTOS
# ==========================================
elif menu == "🎯 Radar de Oportunidades & Proventos":
    st.title("Radar de Oportunidades & Calendário de Proventos")

    tab1, tab2 = st.tabs(["🔍 Radar de Setups Técnicos", "📅 Calendário de Data COM (Dividendos & JCP)"])

    with tab1:
        st.subheader("Scanner de Confluência na B3")

        # Filtros de Segmento de Mercado
        c1, c2, c3 = st.columns([3, 2, 1])
        with c1:
            segment_label = st.radio(
                "Segmento de Mercado:",
                [
                    "🌟 Universo Amplo B3 (~100 Ações: Blue Chips + Small & Mid Caps)",
                    "🚀 Small & Mid Caps / Fora do Radar (Empresas Menores de Alto Crescimento)",
                    "🏢 Blue Chips Tradicionais (Grandes Empresas / IBOV)",
                    "⚡ Top 20 Mais Líquidas",
                ],
                index=0,
            )
        with c2:
            only_high = st.checkbox("Apenas Alta Convicção (Score >= 8.0 & R/R >= 2.2)", value=False)
            if not only_high:
                min_score = st.slider("Nota de Confluência Mínima:", min_value=6.0, max_value=9.5, value=7.0, step=0.5)
            else:
                min_score = 8.0
        with c3:
            st.write("")
            btn_scan = st.button("🔄 Executar Scanner", type="primary")

        # Mapeamento do segmento
        if "Small & Mid Caps" in segment_label:
            category_code = "small_caps"
        elif "Blue Chips" in segment_label:
            category_code = "blue_chips"
        elif "Top 20" in segment_label:
            category_code = "top20"
        else:
            category_code = "all"

        # Legenda Informativa
        with st.expander("ℹ️ Legenda Informativa dos Termos da Tabela (Clique para abrir)"):
            st.markdown(
                r"""
                - **Código da Ação (Ticker):** Código de negociação do ativo na B3 (ex: PETR4, KEPL3, WEGE3).
                - **Setup (Estratégia):** Padrão matemático detectado:
                  - *Reversão à Média (IFR2):* Correção aguda em papel que está em tendência primária de alta (alta taxa de acerto de 65-75%).
                  - *Seguidor de Tendência (Momentum):* Rompimento ou repique em médias móveis alinhadas (alto ganho assimétrico de 2.5R a 5R).
                  - *Captura Pré-Data COM:* Compra programada dias antes do corte de proventos em ativo com suporte técnico.
                - **Nota de Confluência (Score 0 a 10):** Grau de alinhamento simultâneo entre tendência, volume financeiro, sobrevenda/rompimento e assimetria. Notas $\ge 8.0$ representam alta convicção.
                - **Preço Entrada Ref. (R$):** Preço de referência do último fechamento para tomada de decisão no pregão.
                - **Stop Loss (R$):** Limite máximo de perda tolerada. Se atingido, encerra-se a posição para proteger o patrimônio.
                - **Alvo / Take Profit (R$):** Preço projetado para realização de lucros.
                - **Relação Risco/Retorno (R/R):** Quantas vezes o ganho potencial supera o risco corrido (ex: 2.5x significa buscar R$ 2,50 de lucro para cada R$ 1,00 arriscado).
                - **Ficha Fundamentalista:** Link direto para consultar indicadores da empresa no StatusInvest (P/L, ROE, Dívida Líquida, Margens).
                """
            )

        if btn_scan or "cached_scan" not in st.session_state or st.session_state.get("last_category") != category_code:
            with st.spinner("Escaneando ativos da B3..."):
                selected_tickers = get_universe(category=category_code)
                st.session_state["cached_scan"] = run_screener(
                    tickers=selected_tickers,
                    min_score=min_score,
                    high_conviction_only=only_high,
                    show_progress=False,
                )
                st.session_state["last_category"] = category_code

        results = st.session_state.get("cached_scan", [])
        if results:
            st.success(f"Encontradas {len(results)} oportunidades com setup ativo.")

            # Monta dataframe formatado
            table_rows = []
            for r in results:
                info_link = f"[{r['ticker']} no StatusInvest]({r['info_url']})"
                shares_val = r.get("suggested_shares", 100)
                cap_val = r.get("suggested_capital", shares_val * r["entry_price"])
                adtv_val = f"R$ {r.get('adtv_milhoes', 0):.1f}M" if "adtv_milhoes" in r else "-"

                table_rows.append({
                    "Código da Ação": r["ticker"],
                    "Setup (Estratégia)": r["name"],
                    "Nota de Confluência": f"{r['score']:.1f} / 10",
                    "Preço Entrada (R$)": f"R$ {r['entry_price']:.2f}",
                    "Stop Loss (R$)": f"R$ {r['stop_loss']:.2f}",
                    "Alvo de Lucro (R$)": f"R$ {r['take_profit']:.2f}",
                    "Relação R/R": f"{r.get('rr_ratio', 'N/A')}x",
                    "Lote Sugerido (2% Risco)": f"{shares_val} ações",
                    "Capital Alocado": f"R$ {cap_val:,.2f}",
                    "ADTV 21": adtv_val,
                    "Análise Técnica Detalhada": r["reason"].replace("\n", " | "),
                    "Ficha Fundamentalista": info_link,
                })

            df_display = pd.DataFrame(table_rows)
            st.dataframe(
                df_display,
                width="stretch",
                column_config={
                    "Ficha Fundamentalista": st.column_config.LinkColumn("Ficha Fundamentalista"),
                },
            )
        else:
            st.info("Nenhuma oportunidade atende aos critérios selecionados no momento. Tente selecionar 'Universo Amplo B3' ou diminuir a Nota de Confluência.")

    with tab2:
        st.subheader("Eventos de Proventos Próximos (Período Legal)")
        st.markdown(
            "Identifica anúncios de **Dividendos** e **JCP** com **Data COM** nos próximos dias úteis para planejamento de posicionamento."
        )
        if st.button("🔄 Atualizar Calendário de Proventos"):
            with st.spinner("Buscando proventos anunciados..."):
                st.session_state["cached_divs"] = scan_upcoming_dividends(get_universe(category="all"))

        divs = st.session_state.get("cached_divs", [])
        if divs:
            df_divs = pd.DataFrame(divs)[[
                "ticker", "data_com", "data_ex", "days_until_com", "estimated_value", "current_price", "projected_yield_pct"
            ]]
            df_divs.columns = [
                "Código da Ação", "Data COM (Corte)", "Data EX", "Dias até Data COM",
                "Provento Estimado (R$)", "Cotação Atual (R$)", "Yield da Rodada (%)"
            ]
            st.dataframe(df_divs, width="stretch")
        else:
            st.info("Nenhum anúncio recente com Data COM nos próximos 15 dias para os ativos monitorados.")

# ==========================================
# 2.5 AUDITORIA DE TRAVAS DE BAIXA & OPÇÕES
# ==========================================
elif menu == "🛡️ Auditoria de Travas de Baixa & Opções":
    st.title("Auditoria de Travas de Baixa e Operações Estruturadas")
    st.markdown(
        "Avaliação matemática independente para **auditar recomendações de bancos e corretoras** "
        "(como a Trava de Baixa sugerida hoje em **MCDC34**). Descubra se a assimetria real favorece o investidor ou a mesa do banco."
    )

    with st.expander("📌 Por que o seu banco está sugerindo Trava de Baixa em MCDC34 hoje?", expanded=True):
        st.markdown(
            """
            * **Tese no Ativo (McDonald's / MCDC34):** Desaceleração de tráfego de clientes de média/baixa renda, guerras de preços de combos de US$ 5 e compressão de margens nos EUA, além de resistência gráfica após altas recentes.
            * **O Conflito de Interesses do Banco:** Ao empurrar travas de opções pré-formatadas em "1 clique", a mesa do banco atua como contraparte de balcão. O banco embute uma margem generosa no spread entre compra e venda das opções e desova riscos que grandes clientes institucionais não querem carregar.
            * **A Armadilha do Varejo:** A maioria dessas travas arrisca **100% de perda do capital investido** para um ganho máximo de apenas **30% a 50%**. Você arrisca R$ 1.000 para ganhar R$ 350. Além disso, **opções NÃO possuem a isenção fiscal de R$ 20.000/mês da Receita Federal** (15% de IR obrigatório).
            """
        )

    st.subheader("Simulador e Auditor de Assimetria de Travas")
    c_in1, c_in2, c_in3 = st.columns(3)

    with c_in1:
        op_ticker = st.text_input("Ativo-Objeto (ex: MCDC34, PETR4, VALE3):", value="MCDC34").strip().upper()
        spread_choice = st.selectbox(
            "Tipo de Estrutura:",
            ["Trava de Baixa com PUT (Débito)", "Trava de Baixa com CALL (Crédito)"],
            index=0,
        )
        type_code = "BEAR_PUT" if "PUT" in spread_choice else "BEAR_CALL"

    with c_in2:
        s_long = st.number_input("Strike Superior (K_high em R$):", value=54.00, step=0.50, format="%.2f")
        s_short = st.number_input("Strike Inferior (K_low em R$):", value=50.00, step=0.50, format="%.2f")

    with c_in3:
        n_prem = st.number_input("Custo Líquido / Prêmio por Ação (R$):", value=1.40, min_value=0.01, step=0.05, format="%.2f")
        n_contracts = st.number_input("Quantidade de Opções (Cotas):", value=100, min_value=10, step=100)

    # Executa auditoria quantitativa
    audit_res = audit_option_spread(
        underlying=op_ticker,
        spread_type=type_code,
        strike_long=s_long,
        strike_short=s_short,
        net_premium=n_prem,
        contracts_qty=int(n_contracts),
    )

    st.markdown("---")
    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.metric("Relação Risco x Retorno", f"{audit_res['risk_reward_ratio']:.2f}x")
    with m2:
        st.metric("Ganho Máximo Possível", f"R$ {audit_res['max_profit_total']:,.2f}")
    with m3:
        st.metric("Perda Máxima Possível", f"R$ {audit_res['max_loss_total']:,.2f}")
    with m4:
        st.metric("Ponto de Equilíbrio (Break-Even)", f"R$ {audit_res['break_even']:.2f}")
    with m5:
        st.metric("Taxa de Acerto Necessária", f"{audit_res['required_win_rate_pct']:.1f}%")

    if audit_res["is_retail_trap"]:
        st.error(f"🚨 **DIAGNÓSTICO DO ARQUITETO:** {audit_res['recommendation']}")
    else:
        st.success(f"✓ **DIAGNÓSTICO DO ARQUITETO:** {audit_res['recommendation']}")

    st.caption(audit_res["tax_warning"])

    # Gráfico de Payoff Interativo no Vencimento
    st.subheader(f"Curva de Payoff no Vencimento ({audit_res['strategy_desc']})")
    
    k_min = min(s_long, s_short)
    k_max = max(s_long, s_short)
    prices = [round(k_min * 0.85 + (i * (k_max * 1.15 - k_min * 0.85) / 100), 2) for i in range(101)]
    payoffs = []

    for p in prices:
        if type_code == "BEAR_PUT":
            # Compra put k_max, vende put k_min
            val_put_long = max(0.0, k_max - p)
            val_put_short = max(0.0, k_min - p)
            pnl_per_share = (val_put_long - val_put_short) - n_prem
        else:
            # Vende call k_min, compra call k_max
            val_call_short = max(0.0, p - k_min)
            val_call_long = max(0.0, p - k_max)
            pnl_per_share = n_prem - (val_call_short - val_call_long)
        payoffs.append(round(pnl_per_share * n_contracts, 2))

    df_payoff = pd.DataFrame({"Preco_Ativo": prices, "Resultado_RS": payoffs})

    fig_payoff = go.Figure()
    fig_payoff.add_trace(
        go.Scatter(
            x=df_payoff["Preco_Ativo"],
            y=df_payoff["Resultado_RS"],
            mode="lines",
            name="Resultado Financeiro (R$)",
            line=dict(color="#2563eb", width=3),
        )
    )
    fig_payoff.add_hline(y=0, line_dash="dash", line_color="#64748b", annotation_text="Break-Even (Zero a Zero)")
    fig_payoff.add_vline(x=audit_res["break_even"], line_dash="dot", line_color="#f59e0b", annotation_text=f"BE: R$ {audit_res['break_even']:.2f}")

    fig_payoff.update_layout(
        template="plotly_white",
        title=f"Payoff no Vencimento para {op_ticker} ({int(n_contracts)} opções)",
        xaxis_title="Cotação do Ativo-Objeto no Vencimento (R$)",
        yaxis_title="Lucro / Prejuízo Líquido (R$)",
        hovermode="x unified",
    )
    st.plotly_chart(fig_payoff, width="stretch")


# ==========================================
# 3. ANÁLISE GRÁFICA & VARIAÇÕES (1D a 10A)
# ==========================================
elif menu == "📈 Análise Gráfica & Variações (1D a 10A)":
    st.title("Análise Gráfica e Retornos Históricos Multitemporais")
    st.markdown("Consulte qualquer ação brasileira e visualize suas variações de **1 Dia a 10 Anos**, médias móveis e indicadores.")

    col_input, col_info = st.columns([1, 2])
    with col_input:
        selected_ticker = st.text_input("Digite o Ticker da Ação (ex: WEGE3, PETR4, KEPL3, TAEE11):", value="WEGE3").strip().upper()

    clean_t = get_clean_ticker(selected_ticker)
    base_t = get_base_ticker(selected_ticker)

    with st.spinner(f"Carregando dados históricos de {base_t}..."):
        variations = compute_multi_timeframe_variations(clean_t)
        df_hist = fetch_ticker_data(clean_t, period="5y")

    if df_hist is not None and not df_hist.empty:
        # Variações percentuais em cards
        st.subheader(f"Variações Percentuais de {base_t}")
        v_cols = st.columns(8)
        periods = [
            ("1D", "1 Dia"),
            ("1S", "1 Semana"),
            ("1M", "1 Mês"),
            ("3M", "Trimestre"),
            ("6M", "Semestre"),
            ("1A", "1 Ano"),
            ("5A", "5 Anos"),
            ("10A", "10 Anos"),
        ]

        for i, (k, label) in enumerate(periods):
            val = variations.get(k)
            with v_cols[i]:
                if val is not None:
                    st.metric(label, f"{val:+.2f}%")
                else:
                    st.metric(label, "N/D")

        # Links rápidos
        st.markdown(
            f"🔗 **Links Externos:** "
            f"[[StatusInvest - Ficha de {base_t}]]({get_statusinvest_url(base_t)}) | "
            f"[[TradingView - Gráfico de {base_t}]]({get_tradingview_url(base_t)})"
        )

        # Gráfico Interativo com Plotly
        st.subheader("Gráfico Interativo de Cotação e Médias Móveis")
        df_chart = compute_indicators(df_hist).dropna(subset=["SMA_200", "EMA_9", "EMA_21"])

        timeframe_choice = st.radio(
            "Período do Gráfico:",
            ["Últimos 6 Meses", "Último 1 Ano", "Últimos 2 Anos", "Últimos 5 Anos"],
            horizontal=True,
            index=1,
        )

        if timeframe_choice == "Últimos 6 Meses":
            df_plot = df_chart.tail(126)
        elif timeframe_choice == "Último 1 Ano":
            df_plot = df_chart.tail(252)
        elif timeframe_choice == "Últimos 2 Anos":
            df_plot = df_chart.tail(504)
        else:
            df_plot = df_chart

        fig = go.Figure()
        # Candlestick
        fig.add_trace(
            go.Candlestick(
                x=df_plot.index,
                open=df_plot["Open"],
                high=df_plot["High"],
                low=df_plot["Low"],
                close=df_plot["Close"],
                name="Preço (OHLC)",
            )
        )
        # Médias
        fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot["EMA_9"], line=dict(color="#3b82f6", width=1.5), name="EMA 9 (Rápida)"))
        fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot["EMA_21"], line=dict(color="#f59e0b", width=1.5), name="EMA 21 (Intermediária)"))
        fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot["SMA_200"], line=dict(color="#ef4444", width=2), name="SMA 200 (Tendência Primária)"))

        fig.update_layout(
            template="plotly_white",
            xaxis_rangeslider_visible=False,
            height=500,
            yaxis_title="Preço (R$)",
            margin=dict(l=20, r=20, t=30, b=20),
        )
        st.plotly_chart(fig, width="stretch")
    else:
        st.error(f"Não foi possível obter dados para o ticker {selected_ticker}. Verifique se o código está correto na B3.")

# ==========================================
# 4. GUIA DOS SETUPS & ESTRATÉGIAS
# ==========================================
elif menu == "📚 Guia dos Setups & Estratégias":
    st.title("Guia Técnico dos Setups de Swing Trade & Proventos")
    st.markdown("Compreenda a fundamentação matemática, regras de entrada e gestão de risco de cada modelo operacional utilizado pelo sistema.")

    g_tab1, g_tab2, g_tab3, g_tab4 = st.tabs([
        "🟢 Reversão à Média (IFR2)",
        "🚀 Seguidor de Tendência (Momentum)",
        "💰 Captura Pré-Data COM",
        "⭐ Como Funciona a Nota de Confluência",
    ])

    with g_tab1:
        st.subheader("Setup IFR2 (Larry Connors) - Reversão à Média")
        st.markdown(
            """
            ### O que é?
            O **IFR2** é um dos setups quantitativos mais testados e comprovados da história dos mercados. Desenvolvido pelo estatístico norte-americano Larry Connors, ele se baseia no princípio de **reversão à média**: após uma sequência abrupta de quedas em um ativo estruturalmente forte, o preço tende a realizar um repique violento para equilibrar a oferta e a demanda.

            ### Por que funciona tão bem na B3?
            O mercado acionário brasileiro possui forte característica cíclica e oscilatória. Estatisticamente, em ações com alta liquidez na B3, o IFR2 apresenta **taxa de acerto histórica entre 65% e 75%**, com tempo médio de permanência no trade de apenas **2 a 5 pregões**.

            ### Regras Operacionais Estritas:
            1. **Filtro de Tendência Primária:** O preço de fechamento **deve estar acima da Média Móvel Simples de 200 períodos (SMA 200)**. Nunca compramos facas caindo em ativos com tendência de baixa de longo prazo.
            2. **Gatilho de Compra:** O **IFR de 2 períodos (RSI 2)** deve fechar abaixo de **10** (sobrevenda extrema).
            3. **Gatilho de Saída (Take Profit):** A posição é encerrada na **máxima dos últimos 2 pregões** (HIGH_2D) ou no primeiro fechamento acima da SMA 5.
            4. **Stop de Proteção:** Stop loss inegociável posicionado a $2 \times \text{ATR(14)}$ abaixo do preço de compra.
            """
        )

    with g_tab2:
        st.subheader("Setup Seguidor de Tendência (Momentum & Médias Móveis)")
        st.markdown(
            """
            ### O que é?
            Inspirado nos conceitos de Larry Williams e Richard Donchian, o objetivo deste setup é **surfar grandes pernadas direcionais de alta** (rallys) que duram de 1 a 4 semanas. Enquanto a reversão à média busca pequenos ganhos frequentes, o seguidor de tendência busca **assimetria de retorno (Payoff elevado)**.

            ### A Dinâmica Matemática:
            - **Taxa de Acerto:** Moderada (40% a 50%).
            - **Relação Ganho/Perda (Payoff):** Elevadíssima (3:1 a 5:1). Uma única operação vencedora compensa com sobra 3 ou 4 pequenos stops.

            ### Regras Operacionais:
            1. **Alinhamento Altista Clássico:** O preço deve estar acima da Média Móvel Exponencial rápida (EMA 9), que por sua vez deve estar acima da EMA lenta (EMA 21), ambas acima da SMA 200.
            2. **Gatilho de Entrada:** Rompimento da máxima da vela de sinal após um recuo ou virada da EMA 9 para cima.
            3. **Condução por Trailing Stop:** O stop loss não fica parado. Conforme a ação atinge novos topos, a linha de stop móvel é elevada progressivamente pela volatilidade ATR ($2 \times \text{ATR}$ abaixo da máxima).
            4. **Alvo Projetado:** Projeção inicial de **2.5 vezes o risco corrido** ($2.5R$).
            """
        )

    with g_tab3:
        st.subheader("Estratégia de Captura de Proventos Pré-Data COM")
        st.markdown(
            """
            ### O Ciclo Legal de Dividendos e JCP na B3:
            1. **Data do Anúncio:** A empresa divulga o Fato Relevante informando que distribuirá proventos aos acionistas.
            2. **Data COM (Data de Corte):** É o **último dia útil** em que você precisa estar com as ações em carteira para ter direito de receber o dividendo ou JCP.
            3. **Data EX:** É o dia útil imediatamente seguinte à Data COM. A partir deste dia, quem comprar **não** receberá o provento.
            4. **Data de Pagamento:** Quando o dinheiro cai efetivamente na conta da sua corretora.

            ### O Dissenso Construtivo: A Armadilha da Data EX
            Na B3, na abertura da **Data EX**, o preço da ação sofre um **desconto matemático no valor exato do dividendo**.
            > *Exemplo:* Se uma ação fecha a Data COM a R$ 30,00 com anúncio de dividendo de R$ 2,00, ela abre a Data EX cotada a R$ 28,00.
            
            **Por isso, comprar apenas pelo dividendo é perigoso!** O algoritmo do B3 Ações Pilot só emite sinal de compra pré-Data COM se a ação estiver **sustentada acima da SMA 50**, garantindo que há força compradora no mercado para fechar o gap de proventos rapidamente.

            ### Diferença Tributária: Dividendo vs. JCP
            - **Dividendos:** São **100% isentos** de Imposto de Renda para pessoas físicas no Brasil.
            - **Juros sobre Capital Próprio (JCP):** Sofrem retenção na fonte de **15% de IR** pela própria empresa. O valor creditado na sua conta já é líquido de impostos.
            """
        )

    with g_tab4:
        st.subheader("Como Funciona a Nota de Confluência (Score de 0 a 10)")
        st.markdown(
            r"""
            A **Nota de Confluência** é um modelo estatístico proprietário que atribui pontos a uma oportunidade com base na convergência simultânea de múltiplos fatores técnicos e quantitativos:

            | Fator Técnico Avaliado | Peso no Score | Critério de Pontuação |
            | :--- | :---: | :--- |
            | **Setup Base Identificado** | 7.0 pts | O ativo cumpriu todas as regras eliminatórias do setup. |
            | **Sobrevenda Extrema (no IFR2)** | +1.5 pts | IFR(2) abaixo de 5.0 (nível de pânico raríssimo de mercado). |
            | **Sobrevenda Moderada (no IFR2)** | +1.0 pt | IFR(2) entre 5.0 e 10.0. |
            | **Volume Acima da Média** | +1.0 a +1.5 pts | Volume financeiro $\ge 1.3\times$ a média móvel de 21 dias (exaustão vendedora ou fluxo comprador institucional). |
            | **Dividend Yield Relevante** | +1.0 a +1.5 pts | Provento na rodada superior a 1.5% a 2.0% da cotação. |
            | **Janela Temporal Otimizada** | +0.5 pt | Data COM a menos de 4 pregões de distância. |

            - **Score 8.0 a 10.0:** **Altíssima Convicção.** Todos os indicadores convergem na mesma direção. É o único nível que dispara alertas matinais no Telegram.
            - **Score 7.0 a 7.9:** **Convicção Padrão.** O setup é matematicamente válido e possui bom risco/retorno.
            - **Score < 7.0:** Descartado pelo filtro de qualidade.
            """
        )

# ==========================================
# 5. HISTÓRICO & PERFORMANCE
# ==========================================
elif menu == "📜 Histórico & Performance":
    st.title("Histórico de Trades e Curva de Capital")

    transactions = session.query(Transaction).order_by(Transaction.date.asc()).all()
    if transactions:
        tx_data = []
        cumulative_pnl = 0.0
        pnl_history = []

        wins = 0
        losses = 0
        total_profit = 0.0
        total_loss = 0.0

        for t in transactions:
            if t.type == "SELL":
                cumulative_pnl += t.realized_pnl
                pnl_history.append({"data": t.date, "pnl_acumulado": cumulative_pnl})
                if t.realized_pnl > 0:
                    wins += 1
                    total_profit += t.realized_pnl
                elif t.realized_pnl < 0:
                    losses += 1
                    total_loss += abs(t.realized_pnl)

            tx_data.append({
                "Data": t.date.strftime("%d/%m/%Y %H:%M"),
                "Ticker": t.ticker,
                "Tipo": t.type,
                "Qtd": t.quantity,
                "Preço": f"R$ {t.price:,.2f}",
                "Taxas": f"R$ {t.fees:,.2f}",
                "PnL Líquido": f"R$ {t.realized_pnl:,.2f}" if t.type == "SELL" else "-",
                "Estratégia": t.strategy,
            })

        total_closed = wins + losses
        win_rate = (wins / total_closed) * 100 if total_closed > 0 else 0.0
        profit_factor = (total_profit / total_loss) if total_loss > 0 else (99.0 if total_profit > 0 else 0.0)

        # Métricas
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("PnL Realizado Total", f"R$ {cumulative_pnl:,.2f}")
        c2.metric("Taxa de Acerto (Win Rate)", f"{win_rate:.1f}%")
        c3.metric("Fator de Lucro (Profit Factor)", f"{profit_factor:.2f}")
        c4.metric("Trades Encerrados", f"{total_closed} ({wins}V / {losses}D)")

        # Gráfico de Evolução Patrimonial
        if pnl_history:
            df_chart = pd.DataFrame(pnl_history)
            fig = px.line(
                df_chart,
                x="data",
                y="pnl_acumulado",
                title="Curva de Lucro Líquido Acumulado (R$)",
                markers=True,
            )
            fig.update_layout(template="plotly_white", xaxis_title="Data", yaxis_title="R$ Líquido")
            st.plotly_chart(fig, width="stretch")

        st.subheader("Registro de Operações")
        st.dataframe(pd.DataFrame(tx_data), width="stretch")
    else:
        st.info("Nenhuma operação registrada no banco de dados.")

# ==========================================
# 6. GESTÃO FISCAL & DARF
# ==========================================
elif menu == "📑 Gestão Fiscal & DARF":
    st.title("Gestão Tributária e Apuração de DARF")
    st.markdown("Regras Oficiais da Receita Federal do Brasil para **Swing Trade de Ações**.")

    tax_summary = get_current_tax_summary(session)

    # Termômetro de Vendas Mensais
    total_sales = tax_summary["total_sales"]
    limit = tax_summary["sales_limit"]
    pct_used = min(total_sales / limit, 1.0)

    st.subheader(f"Apuração do Mês Vigente ({tax_summary['year_month']})")

    st.markdown(f"**Volume de Vendas no Mês:** R$ {total_sales:,.2f} de R$ {limit:,.2f} (Limite de Isenção)")
    st.progress(pct_used)

    if tax_summary["is_exempt"]:
        st.markdown('<span class="badge-success">✓ MÊS ISENTO: Total de vendas inferior a R$ 20.000,00.</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="badge-warning">⚠️ MÊS TRIBUTÁVEL: Vendas ultrapassaram R$ 20.000,00. Alíquota de 15% incidente sobre lucros.</span>', unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Lucro Líquido do Mês", f"R$ {tax_summary['net_profit']:,.2f}")
    c2.metric("Prejuízo Compensado", f"R$ {tax_summary['prior_losses_used']:,.2f}")
    c3.metric("Prejuízo Acumulado Restante", f"R$ {tax_summary['accumulated_loss']:,.2f}")
    c4.metric("DARF a Pagar (Cód 6015)", f"R$ {tax_summary['final_darf']:,.2f}")

    if tax_summary["final_darf"] > 0:
        st.warning(f"🔔 **Atenção:** DARF gerado no valor de **R$ {tax_summary['final_darf']:,.2f}**. Pagamento vence até o último dia útil do mês subsequente.")

    # Tabela com histórico de meses anteriores
    st.subheader("Histórico Fiscal por Mês")
    records = session.query(MonthlyTaxRecord).order_by(MonthlyTaxRecord.year_month.desc()).all()
    if records:
        rec_data = []
        for r in records:
            rec_data.append({
                "Mês": r.year_month,
                "Vendas Totais": f"R$ {r.total_sales:,.2f}",
                "Lucro Líquido": f"R$ {r.net_profit:,.2f}",
                "Status": "Isento" if r.is_exempt else "Tributável",
                "Prej. Compensado": f"R$ {r.prior_losses_used:,.2f}",
                "Prej. Acumulado": f"R$ {r.accumulated_loss:,.2f}",
                "IR Devido": f"R$ {r.tax_due:,.2f}",
                "DARF (6015)": f"R$ {r.final_darf:,.2f}",
                "Pago": "Sim" if r.is_paid else "Não",
            })
        st.dataframe(pd.DataFrame(rec_data), width="stretch")

# ==========================================
# 7. REGISTRAR ORDEM
# ==========================================
elif menu == "➕ Registrar Ordem":
    st.title("Registrar Nova Operação")

    tab_buy, tab_sell = st.tabs(["🛒 Nova Compra", "💰 Nova Venda"])

    with tab_buy:
        with st.form("form_buy"):
            ticker = st.text_input("Ticker do Ativo (ex: PETR4, VALE3, KEPL3, WEGE3)").upper()
            qty = st.number_input("Quantidade de Ações", min_value=1, step=100, value=100)
            price = st.number_input("Preço de Execução (R$)", min_value=0.01, step=0.01, format="%.2f", value=30.00)
            fees = st.number_input("Taxas e Emolumentos da B3 (R$)", min_value=0.0, step=0.10, value=1.50)
            stop_loss = st.number_input("Stop Loss (R$)", min_value=0.0, step=0.01, value=28.50)
            take_profit = st.number_input("Take Profit / Alvo (R$)", min_value=0.0, step=0.01, value=33.50)
            strategy = st.selectbox("Estratégia", ["IFR2", "TREND", "DIVIDEND_COM", "MANUAL"])
            notes = st.text_area("Notas / Justificativa da Entrada")

            submitted_buy = st.form_submit_button("Confirmar Compra", type="primary")
            if submitted_buy:
                if not ticker:
                    st.error("Informe o ticker da ação.")
                else:
                    pos = execute_buy(
                        session=session,
                        ticker=ticker,
                        quantity=qty,
                        price=price,
                        fees=fees,
                        stop_loss=stop_loss if stop_loss > 0 else None,
                        take_profit=take_profit if take_profit > 0 else None,
                        strategy=strategy,
                        notes=notes,
                    )
                    st.success(f"Compra registrada com sucesso! Posição atualizada para {pos.quantity} ações de {pos.ticker} a PM de R$ {pos.average_price:.2f}.")

    with tab_sell:
        positions = session.query(Position).all()
        if not positions:
            st.info("Nenhuma posição disponível para venda.")
        else:
            with st.form("form_sell"):
                ticker_sell = st.selectbox("Selecione o Ativo em Custódia", [p.ticker for p in positions])
                selected_pos = session.query(Position).filter_by(ticker=ticker_sell).first()
                st.caption(f"Quantidade em custódia: {selected_pos.quantity} | Preço Médio: R$ {selected_pos.average_price:.2f}")

                qty_sell = st.number_input("Quantidade a Vender", min_value=1, max_value=selected_pos.quantity, step=100, value=selected_pos.quantity)
                price_sell = st.number_input("Preço de Venda (R$)", min_value=0.01, step=0.01, format="%.2f", value=selected_pos.average_price * 1.05)
                fees_sell = st.number_input("Taxas e Emolumentos (R$)", min_value=0.0, step=0.10, value=1.50)
                notes_sell = st.text_area("Notas do Encerramento")

                submitted_sell = st.form_submit_button("Confirmar Venda", type="primary")
                if submitted_sell:
                    res = execute_sell(
                        session=session,
                        ticker=ticker_sell,
                        quantity=qty_sell,
                        price=price_sell,
                        fees=fees_sell,
                        notes=notes_sell,
                    )
                    st.success(f"Venda confirmada! PnL Líquido Realizado: R$ {res['realized_pnl']:,.2f} ({res['realized_pnl_pct']:+.2f}%).")

session.close()
