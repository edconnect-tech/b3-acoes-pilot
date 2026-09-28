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
from b3pilot.data.dividends_feed import scan_upcoming_dividends
from b3pilot.data.universe import get_universe
from b3pilot.config import TAX_EXEMPTION_LIMIT_MONTHLY

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
    ["📊 Visão Geral da Carteira", "🎯 Radar & Proventos (Data COM)", "📜 Histórico & Performance", "📑 Gestão Fiscal & DARF", "➕ Registrar Ordem"],
)
st.sidebar.markdown("---")
st.sidebar.info("Modo de Operação: **Local / Antigravity Native**\n\nIsenção B3: **R$ 20.000,00/mês**")

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
            "Ticker", "Qtd", "Preço Médio", "Cotação Atual",
            "Valor Mercado", "PnL (R$)", "PnL (%)",
            "Stop Loss", "Take Profit", "Trailing Stop", "Estratégia", "Data Entrada"
        ]
        st.dataframe(df_pos, width="stretch")
    else:
        st.info("Nenhuma ação em custódia no momento. Use o menu 'Registrar Ordem' para cadastrar sua primeira compra.")

# ==========================================
# 2. RADAR & PROVENTOS
# ==========================================
elif menu == "🎯 Radar & Proventos (Data COM)":
    st.title("Radar de Oportunidades & Calendário de Proventos")

    tab1, tab2 = st.tabs(["🔍 Radar de Setups Técnicos", "📅 Calendário de Data COM (Dividendos & JCP)"])

    with tab1:
        st.subheader("Scanner de Confluência (IFR2 & Seguidor de Tendência)")
        c1, c2 = st.columns([3, 1])
        with c1:
            only_high = st.checkbox("Filtrar apenas Compras Muito Vantajosas (Score >= 8.0)", value=True)
        with c2:
            btn_scan = st.button("🔄 Executar Scanner Agora", type="primary")

        if btn_scan or "cached_scan" not in st.session_state:
            with st.spinner("Escaneando ativos líquidos da B3..."):
                top_tickers = get_universe(top_only=True)
                st.session_state["cached_scan"] = run_screener(tickers=top_tickers, high_conviction_only=only_high, show_progress=False)

        results = st.session_state.get("cached_scan", [])
        if results:
            df_scan = pd.DataFrame(results)[[
                "ticker", "name", "score", "entry_price", "stop_loss", "take_profit", "rr_ratio", "reason"
            ]]
            df_scan.columns = ["Ticker", "Setup", "Score", "Entrada Ref.", "Stop Loss", "Take Profit", "R/R", "Justificativa Técnica"]
            st.dataframe(df_scan, width="stretch")
        else:
            st.info("Nenhuma oportunidade atende aos critérios restritivos no momento.")

    with tab2:
        st.subheader("Eventos de Proventos Próximos (Período Legal)")
        st.markdown(
            "Identifica anúncios de **Dividendos** e **JCP** com **Data COM** nos próximos dias úteis para planejamento de posicionamento."
        )
        if st.button("🔄 Atualizar Calendário de Proventos"):
            with st.spinner("Buscando proventos anunciados..."):
                st.session_state["cached_divs"] = scan_upcoming_dividends(get_universe(top_only=True))

        divs = st.session_state.get("cached_divs", [])
        if divs:
            df_divs = pd.DataFrame(divs)[[
                "ticker", "data_com", "data_ex", "days_until_com", "estimated_value", "current_price", "projected_yield_pct"
            ]]
            df_divs.columns = ["Ticker", "Data COM", "Data EX", "Dias até COM", "Provento Est. (R$)", "Cotação Atual", "Yield Estimado (%)"]
            st.dataframe(df_divs, width="stretch")
        else:
            st.info("Nenhum anúncio recente com Data COM nos próximos 15 dias para os ativos monitorados.")

# ==========================================
# 3. HISTÓRICO & PERFORMANCE
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
# 4. GESTÃO FISCAL & DARF
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
# 5. REGISTRAR ORDEM
# ==========================================
elif menu == "➕ Registrar Ordem":
    st.title("Registrar Nova Operação")

    tab_buy, tab_sell = st.tabs(["🛒 Nova Compra", "💰 Nova Venda"])

    with tab_buy:
        with st.form("form_buy"):
            ticker = st.text_input("Ticker do Ativo (ex: PETR4, VALE3, WEGE3)").upper()
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
