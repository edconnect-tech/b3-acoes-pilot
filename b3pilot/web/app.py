"""Dashboard Web Local do B3 Ações Pilot (Streamlit + Plotly).

Modo Claro (Clean), Alta Acessibilidade (WCAG 2.2 AA) e Fontes Nativas do Sistema.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import time
from typing import Any, Dict

from b3pilot.ledger.db import init_db, get_db_session, Position, Transaction, MonthlyTaxRecord
from b3pilot.ledger.portfolio import (
    get_portfolio_summary,
    execute_buy,
    execute_sell,
    execute_partial_sale,
    simulate_partial_exit,
    delete_transaction,
)
from b3pilot.ledger.taxes import get_current_tax_summary
from b3pilot.core.screener import run_screener
from b3pilot.core.strategies import compute_indicators
from b3pilot.core.regime import analyze_market_regime
from b3pilot.core.risk import (
    audit_option_spread,
    calculate_position_size,
    check_sector_and_cluster_conflict,
    analyze_portfolio_sector_distribution,
    filter_diversified_signals,
)
from b3pilot.data.sectors import get_asset_sector_profile, B3_SECTORS_DATA
from b3pilot.core.chat import process_chat_query, process_chat_query_with_ai
from b3pilot.ai.providers import (
    detect_best_provider,
    list_providers_status,
    test_provider_connection,
)
from b3pilot.data.dividends_feed import scan_upcoming_dividends
from b3pilot.data.universe import get_universe, SMALL_MID_CAPS, BLUE_CHIPS
from b3pilot.data.b3_feed import (
    fetch_ticker_data,
    fetch_latest_price,
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

# Estilização Clean Light Mode Institucional (WCAG 2.2 AA, Fontes de Sistema e Práticas Modernas de UI)
st.markdown(
    """
    <style>
    /* Tipografia nativa do sistema Apple / Web Clean */
    html, body, [class*="css"] {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Inter", Helvetica, Arial, sans-serif;
        color: #0f172a;
    }

    /* Redução de padding superior padrão do Streamlit para visual de App/Dashboard moderno */
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2.5rem;
        max-width: 1400px;
    }

    /* =========================================================================
       SIDEBAR & MENU DE ACESSO PROFISSIONAL
       ========================================================================= */
    [data-testid="stSidebar"] {
        background-color: #f8fafc;
        border-right: 1px solid #e2e8f0;
    }

    /* Brand Header da Sidebar */
    .sidebar-brand-card {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 6px 4px 16px 4px;
        margin-bottom: 8px;
        border-bottom: 1px solid #e2e8f0;
    }
    .brand-avatar {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 38px;
        height: 38px;
        background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
        color: #ffffff;
        font-size: 1.25rem;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(37, 99, 235, 0.2);
    }
    .brand-info {
        display: flex;
        flex-direction: column;
    }
    .brand-title {
        font-size: 1.05rem;
        font-weight: 700;
        color: #0f172a;
        letter-spacing: -0.02em;
        line-height: 1.2;
    }
    .brand-badge {
        font-size: 0.72rem;
        font-weight: 600;
        color: #2563eb;
        background-color: #eff6ff;
        padding: 2px 6px;
        border-radius: 4px;
        display: inline-block;
        width: fit-content;
        margin-top: 2px;
        border: 1px solid #dbeafe;
    }

    /* Subtítulos de Categorias no Menu */
    .sidebar-category-header {
        font-size: 0.70rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: #64748b;
        margin-top: 14px;
        margin-bottom: 6px;
        padding-left: 8px;
    }

    /* Estilização dos Itens de Menu (Transforma Radiogroup em Lista de Navegação) */
    [data-testid="stSidebar"] div[role="radiogroup"] {
        display: flex;
        flex-direction: column;
        gap: 3px;
    }

    [data-testid="stSidebar"] div[role="radiogroup"] > label {
        display: flex !important;
        align-items: center !important;
        padding: 9px 12px !important;
        border-radius: 7px !important;
        border: 1px solid transparent !important;
        cursor: pointer !important;
        transition: all 0.15s ease-in-out !important;
        background-color: transparent !important;
        margin: 0 !important;
        width: 100% !important;
    }

    [data-testid="stSidebar"] div[role="radiogroup"] > label:hover {
        background-color: #f1f5f9 !important;
        color: #0f172a !important;
    }

    /* Oculta o círculo de seleção nativo de formulário */
    [data-testid="stSidebar"] div[role="radiogroup"] > label > div:first-child {
        display: none !important;
    }

    /* Ajuste do texto do item */
    [data-testid="stSidebar"] div[role="radiogroup"] > label > div:last-child {
        width: 100% !important;
    }
    [data-testid="stSidebar"] div[role="radiogroup"] > label p {
        font-size: 0.88rem !important;
        font-weight: 500 !important;
        color: #334155 !important;
        margin: 0 !important;
        line-height: 1.4 !important;
        transition: color 0.15s ease-in-out !important;
    }

    /* Item Ativo / Selecionado no Menu */
    [data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) {
        background-color: #eff6ff !important;
        border: 1px solid #bfdbfe !important;
        border-left: 4px solid #2563eb !important;
        box-shadow: 0 1px 2px rgba(37, 99, 235, 0.06) !important;
    }
    [data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) p {
        color: #1d4ed8 !important;
        font-weight: 600 !important;
    }

    /* Card de Ambiente da Carteira */
    .env-selector-wrapper {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 10px 12px;
        margin-top: 16px;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
    }
    .env-selector-title {
        font-size: 0.72rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #64748b;
        margin-bottom: 6px;
    }

    /* Card de Rodapé da Sidebar */
    .sidebar-footer-card {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 12px;
        margin-top: 18px;
        font-size: 0.78rem;
        color: #475569;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
    }
    .sidebar-footer-item {
        display: flex;
        justify-content: space-between;
        margin-bottom: 4px;
    }
    .sidebar-footer-item:last-child {
        margin-bottom: 0;
    }
    .footer-highlight {
        font-weight: 600;
        color: #0f172a;
    }

    /* =========================================================================
       BOTÕES E ALINHAMENTO GERAL DA INTERFACE
       ========================================================================= */
    /* Botões nativos do Streamlit */
    div.stButton > button {
        border-radius: 6px !important;
        font-size: 0.88rem !important;
        font-weight: 500 !important;
        padding: 7px 16px !important;
        min-height: 40px !important;
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        gap: 6px !important;
        transition: all 0.15s ease-in-out !important;
        border: 1px solid #cbd5e1 !important;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04) !important;
    }
    div.stButton > button:hover {
        background-color: #f8fafc !important;
        border-color: #94a3b8 !important;
        color: #0f172a !important;
    }

    /* Botão Primário */
    div.stButton > button[kind="primary"] {
        background-color: #2563eb !important;
        border-color: #2563eb !important;
        color: #ffffff !important;
        font-weight: 600 !important;
        box-shadow: 0 1px 2px rgba(37, 99, 235, 0.2) !important;
    }
    div.stButton > button[kind="primary"]:hover {
        background-color: #1d4ed8 !important;
        border-color: #1d4ed8 !important;
        color: #ffffff !important;
    }

    /* Cards de Métricas Clean */
    .metric-card {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 16px;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
    }

    /* Badges Semânticos Institucionais */
    .badge-success {
        background-color: #f0fdf4;
        color: #166534;
        border: 1px solid #bbf7d0;
        padding: 6px 12px;
        border-radius: 6px;
        font-weight: 600;
        font-size: 0.85rem;
        display: inline-flex;
        align-items: center;
        gap: 6px;
    }
    .badge-warning {
        background-color: #fffbeb;
        color: #92400e;
        border: 1px solid #fde68a;
        padding: 6px 12px;
        border-radius: 6px;
        font-weight: 600;
        font-size: 0.85rem;
        display: inline-flex;
        align-items: center;
        gap: 6px;
    }
    .badge-danger {
        background-color: #fef2f2;
        color: #991b1b;
        border: 1px solid #fecaca;
        padding: 6px 12px;
        border-radius: 6px;
        font-weight: 600;
        font-size: 0.85rem;
        display: inline-flex;
        align-items: center;
        gap: 6px;
    }

    /* Cockpit Header de Regime Macro */
    .macro-cockpit-bar {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 10px 14px;
        margin-bottom: 16px;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
        display: flex;
        align-items: center;
        justify-content: space-between;
    }

    .legend-box {
        background-color: #f8fafc;
        border-left: 4px solid #2563eb;
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
regime = analyze_market_regime()

# =============================================================================
# SIDEBAR INSTITUCIONAL (DESIGN SYSTEM WEB MODERNO)
# =============================================================================
st.sidebar.markdown(
    """
    <div class="sidebar-brand-card">
        <div class="brand-avatar">📈</div>
        <div class="brand-info">
            <span class="brand-title">B3 Ações Pilot</span>
            <span class="brand-badge">Institucional • v0.5.0</span>
        </div>
    </div>
    <div class="sidebar-category-header">Navegação Principal</div>
    """,
    unsafe_allow_html=True,
)

MENU_OPTIONS = [
    "📊 Visão Geral da Carteira",
    "💬 Assistente & Chat Operacional",
    "🎯 Radar de Oportunidades & Proventos",
    "🛡️ Auditoria de Travas de Baixa & Opções",
    "📈 Análise Gráfica & Variações (1D a 10A)",
    "📚 Guia dos Setups & Estratégias",
    "📜 Histórico & Performance",
    "📑 Gestão Fiscal & DARF",
    "➕ Registrar Ordem",
]
if "selected_page" not in st.session_state or st.session_state["selected_page"] not in MENU_OPTIONS:
    st.session_state["selected_page"] = MENU_OPTIONS[0]

nav_idx = MENU_OPTIONS.index(st.session_state["selected_page"])
chosen_menu = st.sidebar.radio(
    "Navegação:",
    MENU_OPTIONS,
    index=nav_idx,
    label_visibility="collapsed",
)
if chosen_menu != st.session_state["selected_page"]:
    st.session_state["selected_page"] = chosen_menu

menu = st.session_state["selected_page"]

# Seletor de Ambiente Institucional
st.sidebar.markdown(
    """
    <div class="env-selector-wrapper">
        <div class="env-selector-title">Ambiente de Custódia</div>
    </div>
    """,
    unsafe_allow_html=True,
)
portfolio_env = st.sidebar.radio(
    "Ambiente da Carteira:",
    ["💼 Carteira Real (Capital Ativo)", "🧪 Laboratório Simulado (Paper Trading)"],
    index=0,
    label_visibility="collapsed",
)
is_sim_mode = "Simulado" in portfolio_env or "Simulação" in portfolio_env

# Rodapé da Sidebar
st.sidebar.markdown(
    f"""
    <div class="sidebar-footer-card">
        <div class="sidebar-footer-item">
            <span>Regime IBOV:</span>
            <span class="footer-highlight">{regime['name']}</span>
        </div>
        <div class="sidebar-footer-item">
            <span>Isenção Fiscal:</span>
            <span class="footer-highlight">R$ 20.000 / mês</span>
        </div>
        <div class="sidebar-footer-item">
            <span>Motor Quant:</span>
            <span class="footer-highlight">Local-First (agy)</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# =============================================================================
# COCKPIT HEADER MACRO IBOVESPA NO TOPO
# =============================================================================
status_color_class = "badge-success" if regime["status"] == "BULL" else ("badge-warning" if regime["status"] == "CORRECTION" else "badge-danger")
status_icon = "🟢" if regime["status"] == "BULL" else ("🟡" if regime["status"] == "CORRECTION" else ("🚨" if regime["status"] == "PANIC" else "🔴"))

ibov_close_str = f"R$ {regime['ibov_close']:,.0f}" if regime.get("ibov_close") else "-"
ibov_change_str = f"{regime.get('ibov_change_pct', 0.0):+.2f}%"
ibov_5d_str = f"{regime.get('ibov_change_5d_pct', 0.0):+.2f}%"
alloc_pct_str = f"{int(regime['allocation_multiplier']*100)}%"

ibov_change_color = "#166534" if regime.get("ibov_change_pct", 0.0) >= 0 else "#991b1b"

st.markdown(
    f"""
    <div class="macro-cockpit-bar">
        <div style="display:flex; align-items:center; gap:12px; flex-wrap:wrap;">
            <span class="{status_color_class}">
                {status_icon} <b>{regime['name']}</b>
            </span>
            <span style="font-size:0.86rem; color:#475569;">
                {regime['description']}
            </span>
        </div>
        <div style="display:flex; align-items:center; gap:14px; font-size:0.84rem; background:#f8fafc; border:1px solid #e2e8f0; padding:6px 12px; border-radius:6px; flex-shrink:0;">
            <div><b>IBOV:</b> <span style="font-weight:600;">{ibov_close_str}</span> <span style="color:{ibov_change_color}; font-weight:600;">({ibov_change_str})</span></div>
            <div style="color:#cbd5e1;">|</div>
            <div><b>5D:</b> {ibov_5d_str}</div>
            <div style="color:#cbd5e1;">|</div>
            <div><b>Lote Permitido:</b> <span style="font-weight:600; color:#2563eb;">{alloc_pct_str}</span></div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ==========================================
# 1. VISÃO GERAL DA CARTEIRA
# ==========================================
if menu == "📊 Visão Geral da Carteira":
    env_title = "🧪 Laboratório de Simulação (Paper Trading)" if is_sim_mode else "💼 Custódia Real"
    st.title(f"Visão Geral — {env_title}")

    if is_sim_mode:
        st.markdown(
            '<div class="badge-warning" style="font-size:0.95rem; padding:10px 14px; margin-bottom:16px; border:1px solid #f59e0b;">'
            '🧪 <b>AMBIENTE DE SIMULAÇÃO (PAPER TRADING) ATIVO:</b> Estas posições e métricas de rentabilidade são 100% virtuais para testes sem risco financeiro real.'
            '</div>',
            unsafe_allow_html=True,
        )

    summary = get_portfolio_summary(session, is_simulated=is_sim_mode)

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

    # Auditoria de Concentração Setorial & Risco de Correlação Cruzada
    if summary["positions"]:
        sec_audit = analyze_portfolio_sector_distribution(
            summary["positions"],
            total_capital=summary["current_market_value"],
        )

        if sec_audit.get("concentration_warnings"):
            for w in sec_audit["concentration_warnings"]:
                st.warning(f"⚠️ {w}")

        with st.expander("🛡️ Radiografia Setorial & Mitigação de Correlações Cruzadas", expanded=bool(sec_audit.get("concentration_warnings"))):
            c_score, c_chart1, c_chart2 = st.columns([1.2, 2, 2])
            with c_score:
                st.metric(
                    "Score de Diversificação",
                    f"{sec_audit['diversification_score']:.0f} / 100",
                    sec_audit['diversification_status'],
                )
                st.caption(
                    "Mede o isolamento contra perdas em cadeia. Evita que papéis do mesmo setor "
                    "ou com risco rural compartilhado (ex: BBAS3 + Agronegócio) derrubem a carteira juntos."
                )
            with c_chart1:
                if sec_audit.get("sector_breakdown"):
                    sec_df = pd.DataFrame([
                        {"Setor": s, "Total": d["total_cost"], "Alocação (%)": d["allocation_pct"]}
                        for s, d in sec_audit["sector_breakdown"].items()
                    ])
                    fig_sec = px.pie(
                        sec_df,
                        names="Setor",
                        values="Total",
                        title="Alocação por Setor B3",
                        hole=0.4,
                        color_discrete_sequence=px.colors.qualitative.Safe,
                    )
                    fig_sec.update_layout(margin=dict(t=35, b=10, l=10, r=10), height=260)
                    st.plotly_chart(fig_sec, use_container_width=True)
            with c_chart2:
                if sec_audit.get("cluster_breakdown"):
                    cl_df = pd.DataFrame([
                        {"Fator de Risco": c, "Total (R$)": d["total_cost"], "Ativos": ", ".join(d["tickers"])}
                        for c, d in sec_audit["cluster_breakdown"].items()
                    ])
                    fig_cl = px.bar(
                        cl_df,
                        x="Fator de Risco",
                        y="Total (R$)",
                        title="Exposição por Macro-Cluster",
                        hover_data=["Ativos"],
                        color_discrete_sequence=["#3b82f6"],
                    )
                    fig_cl.update_layout(margin=dict(t=35, b=10, l=10, r=10), height=260)
                    st.plotly_chart(fig_cl, use_container_width=True)

    st.markdown("### Posições em Aberto")
    if summary["positions"]:
        # Enriquecimento com Setor e Segmento
        for p in summary["positions"]:
            prof = get_asset_sector_profile(p["ticker"])
            p["sector"] = prof.get("sector", "Outros")
            p["subsector"] = prof.get("subsector", "Geral")

        df_pos = pd.DataFrame(summary["positions"])
        df_pos = df_pos[[
            "ticker", "sector", "subsector", "quantity", "average_price", "current_price",
            "market_value", "unrealized_pnl", "unrealized_pnl_pct",
            "stop_loss", "take_profit", "trailing_stop", "strategy", "entry_date"
        ]]
        df_pos.columns = [
            "Código da Ação", "Setor", "Segmento", "Quantidade", "Preço Médio (R$)", "Cotação Atual (R$)",
            "Valor a Mercado (R$)", "Resultado Não Realizado (R$)", "Rentabilidade (%)",
            "Stop Loss (R$)", "Alvo / Take Profit (R$)", "Trailing Stop (R$)", "Estratégia", "Data de Entrada"
        ]
        st.dataframe(df_pos, width="stretch")

        with st.expander("⚡ Executar Realização Parcial (Scale-Out & Subir Stop)"):
            st.markdown(
                "Embolse lucro em 50% das ações e suba o Stop Loss das ações restantes para **eliminar 100% do risco** do trade."
            )
            part_col1, part_col2, part_col3, part_col4 = st.columns(4)
            pos_tickers = [p["ticker"] for p in summary["positions"]]
            with part_col1:
                sel_part_tk = st.selectbox("Selecione o Ativo", pos_tickers, key="quick_part_tk")
                target_p = next(p for p in summary["positions"] if p["ticker"] == sel_part_tk)
                sugg_qty = max(1, target_p["quantity"] // 2) if target_p["quantity"] > 1 else 1
            with part_col2:
                exec_price = st.number_input("Preço de Venda (R$)", value=float(target_p["current_price"]), step=0.01, format="%.2f", key="quick_part_price")
            with part_col3:
                max_q = max(1, target_p["quantity"] - 1) if target_p["quantity"] > 1 else 1
                part_qty = st.number_input("Qtd a Vender (50%)", min_value=1, max_value=max_q, value=min(sugg_qty, max_q), step=1, key="quick_part_qty")
            with part_col4:
                sugg_new_stop = float(target_p.get("new_stop_after_partial") or target_p["average_price"])
                new_stop_val = st.number_input("Novo Stop Loss (R$)", value=sugg_new_stop, step=0.01, format="%.2f", key="quick_part_new_stop")

            # Simulação ao vivo
            if target_p["quantity"] > 1:
                sim_live = simulate_partial_exit(session, sel_part_tk, target_price=exec_price, new_stop_loss=new_stop_val, partial_pct=(part_qty / target_p["quantity"]), is_simulated=is_sim_mode)
                if "error" not in sim_live:
                    st.caption(
                        f"💰 **Lucro Embolsado Agora:** R$ {sim_live['realized_profit_half']:+,.2f} | "
                        f"🛡️ **Lucro Mínimo Garantido no Pior Caso:** **R$ {sim_live['guaranteed_total_profit']:+,.2f}** ({sim_live['guaranteed_total_pct']:+.2f}%)"
                    )

            if st.button("🚀 Confirmar Realização Parcial", type="primary", key="btn_confirm_quick_part"):
                try:
                    res_part = execute_partial_sale(
                        session=session,
                        ticker=sel_part_tk,
                        quantity=part_qty,
                        price=exec_price,
                        new_stop_loss=new_stop_val,
                        is_simulated=is_sim_mode,
                    )
                    st.success(
                        f"✓ Realização Parcial de {sel_part_tk} executada! "
                        f"Lucro realizado de R$ {res_part['realized_pnl']:+,.2f} e novo stop cadastrado em R$ {res_part['new_stop_loss']:.2f}."
                    )
                    st.markdown("**📋 Roteiro de Execução no Home Broker da sua Corretora:**")
                    for step in res_part["broker_instructions"]:
                        st.markdown(f"- {step}")
                except Exception as e:
                    st.error(f"Erro ao processar parcial: {e}")
    else:
        st.info("Nenhuma ação em custódia no momento. Use o menu 'Registrar Ordem' para cadastrar sua primeira compra.")

# ==========================================
# 2. CHAT & ASSISTENTE OPERACIONAL
# ==========================================
elif menu == "💬 Assistente & Chat Operacional":
    env_title = "🧪 Laboratório de Simulação" if is_sim_mode else "💼 Custódia Real"
    st.title(f"💬 Assistente & Chat Operacional — {env_title}")
    st.markdown(
        "Consulte em tempo real se é momento de **comprar**, **vender** ou **aguardar** determinada ação na B3. "
        "A análise cruza automaticamente o Regime do IBOVESPA, indicadores técnicos (IFR2, Médias, ATR, Range 52S) "
        "e a sua carteira atual — com suporte opcional a **APIs de IA e CLIs com login Google (`agy` / `gemini`)**."
    )

    # Configuração do Conector de IA (Sessão + .env)
    provider_statuses = list_providers_status()
    provider_map = {item["id"]: item for item in provider_statuses}
    provider_ids = [item["id"] for item in provider_statuses]
    default_pid = detect_best_provider()
    if "ai_selected_provider" not in st.session_state or st.session_state["ai_selected_provider"] not in provider_ids:
        st.session_state["ai_selected_provider"] = default_pid

    with st.expander("🤖 Conector de IA (APIs & Login Google agy / CLIs)", expanded=False):
        ai_col1, ai_col2 = st.columns([2, 1])
        with ai_col1:
            selected_provider = st.selectbox(
                "Motor de Resposta / Provedor de IA:",
                options=provider_ids,
                index=provider_ids.index(st.session_state["ai_selected_provider"]),
                format_func=lambda pid: f"{provider_map[pid]['name']} [{provider_map[pid]['status_label']}]",
                key="ai_provider_select",
            )
            st.session_state["ai_selected_provider"] = selected_provider

        sel_meta = provider_map[selected_provider]
        with ai_col2:
            model_placeholder = sel_meta.get("default_model") or "Padrão da conta/CLI"
            ai_model_override = st.text_input(
                "Modelo (Opcional):",
                value=st.session_state.get("ai_session_model", ""),
                placeholder=model_placeholder,
                key="ai_model_input",
            ).strip()
            st.session_state["ai_session_model"] = ai_model_override

        ai_session_key = ""
        ai_session_base_url = ""
        auth_type = sel_meta["auth_type"]

        if auth_type == "cli_oauth":
            if sel_meta["ready"]:
                st.success(
                    f"✓ Binário detectado em `{sel_meta['binary_path']}`. "
                    f"Autenticação via login nativo (sem API Key): {sel_meta['login_hint']}"
                )
            else:
                st.warning(
                    f"⚠️ Binário CLI não encontrado no PATH. {sel_meta['login_hint']}"
                )
        elif auth_type == "api_key":
            k_col, b_col = st.columns(2)
            with k_col:
                env_hint = (
                    f"Chave ativa via .env ({sel_meta['env_key']}). Deixe em branco para usar a do .env."
                    if sel_meta["ready"]
                    else f"Informe apenas para esta sessão ou defina {sel_meta.get('env_key') or 'AI_API_KEY'} no .env."
                )
                ai_session_key = st.text_input(
                    "API Key (Somente Sessão — não salva em disco):",
                    value=st.session_state.get("ai_session_api_key", ""),
                    type="password",
                    help=env_hint,
                    key="ai_api_key_input",
                ).strip()
                st.session_state["ai_session_api_key"] = ai_session_key
            with b_col:
                if selected_provider == "openai_compatible":
                    ai_session_base_url = st.text_input(
                        "Base URL (Endpoint OpenAI-Compatible):",
                        value=st.session_state.get("ai_session_base_url", sel_meta.get("base_url") or ""),
                        placeholder="http://localhost:1234/v1",
                        key="ai_base_url_input",
                    ).strip()
                    st.session_state["ai_session_base_url"] = ai_session_base_url
                else:
                    st.caption(f"Status no `.env`: **{sel_meta['status_label']}**")
        elif auth_type == "local":
            ai_session_base_url = st.text_input(
                "URL do Servidor Ollama:",
                value=st.session_state.get("ai_session_base_url", sel_meta.get("base_url") or "http://localhost:11434"),
                key="ai_ollama_url_input",
            ).strip()
            st.session_state["ai_session_base_url"] = ai_session_base_url
            if sel_meta["ready"]:
                st.success(f"✓ Ollama respondendo em `{ai_session_base_url}`.")
            else:
                st.info(f"ℹ️ {sel_meta['login_hint']}")
        else:
            st.info("✓ Modo determinístico local ativo: zero dependência externa e precisão aritmética 64-bit.")

        if st.button("🔌 Testar Conector", key="btn_test_ai_connector"):
            with st.spinner(f"Testando {selected_provider}..."):
                test_res = test_provider_connection(
                    provider=selected_provider,
                    model=ai_model_override or None,
                    api_key=ai_session_key or None,
                    base_url=ai_session_base_url or None,
                )
            if test_res["ok"]:
                st.success(f"✓ {test_res['provider']} ({test_res['model']}): {test_res['message']}")
            else:
                st.error(f"✗ {test_res['message']}")

    active_provider = st.session_state.get("ai_selected_provider", "deterministic")
    active_model = st.session_state.get("ai_session_model") or None
    active_api_key = st.session_state.get("ai_session_api_key") or None
    active_base_url = st.session_state.get("ai_session_base_url") or None

    def _run_chat_turn(user_text: str) -> Dict[str, Any]:
        return process_chat_query_with_ai(
            user_text,
            session,
            is_simulated=is_sim_mode,
            provider=active_provider,
            model=active_model,
            api_key=active_api_key,
            base_url=active_base_url,
        )

    # Inicializa histórico de mensagens no session_state
    if "chat_messages" not in st.session_state:
        st.session_state["chat_messages"] = [
            {
                "role": "assistant",
                "content": (
                    "Olá! Sou o seu **Assistente Operacional da B3**.\n\n"
                    "Posso te ajudar a decidir antes de abrir uma ordem. Você pode me perguntar:\n"
                    "• *\"Posso comprar PETR4 agora?\"*\n"
                    "• *\"Vale a pena vender VALE3 hoje?\"*\n"
                    "• *\"Como está o IBOVESPA hoje?\"*\n"
                    "• *\"Devo vender alguma posição da minha carteira?\"*\n\n"
                    "Qual ativo ou estratégia você quer analisar?"
                ),
            }
        ]

    # Sugestões rápidas de perguntas (chips clicáveis)
    st.markdown("**Perguntas Frequentes / Ações Rápidas:**")
    quick_cols = st.columns(4)
    with quick_cols[0]:
        if st.button("📊 Como está o IBOVESPA?", key="btn_q_ibov", use_container_width=True):
            q_text = "Como está o IBOVESPA hoje?"
            st.session_state["chat_messages"].append({"role": "user", "content": q_text})
            res = _run_chat_turn(q_text)
            st.session_state["chat_messages"].append({
                "role": "assistant",
                "content": res["response"],
                "meta": f"{res['provider']} ({res['model']})",
                "warning": res.get("warning"),
            })
            st.rerun()
    with quick_cols[1]:
        if st.button("🛡️ Devo vender algo?", key="btn_q_exits", use_container_width=True):
            q_text = "Devo vender alguma ação da minha carteira?"
            st.session_state["chat_messages"].append({"role": "user", "content": q_text})
            res = _run_chat_turn(q_text)
            st.session_state["chat_messages"].append({
                "role": "assistant",
                "content": res["response"],
                "meta": f"{res['provider']} ({res['model']})",
                "warning": res.get("warning"),
            })
            st.rerun()
    with quick_cols[2]:
        if st.button("🎯 Melhores Compras Agora", key="btn_q_buys", use_container_width=True):
            q_text = "Quais são as melhores oportunidades de compra no radar?"
            st.session_state["chat_messages"].append({"role": "user", "content": q_text})
            res = _run_chat_turn(q_text)
            st.session_state["chat_messages"].append({
                "role": "assistant",
                "content": res["response"],
                "meta": f"{res['provider']} ({res['model']})",
                "warning": res.get("warning"),
            })
            st.rerun()
    with quick_cols[3]:
        if st.button("🗑️ Limpar Chat", key="btn_clear_chat", use_container_width=True):
            st.session_state["chat_messages"] = []
            st.rerun()

    st.markdown("---")

    # Renderiza mensagens anteriores
    for msg in st.session_state["chat_messages"]:
        with st.chat_message(msg["role"]):
            if msg.get("warning"):
                st.warning(msg["warning"])
            st.markdown(msg["content"])
            if msg.get("meta"):
                st.caption(f"Motor: {msg['meta']}")

    # Input do chat
    if prompt := st.chat_input("Digite sua dúvida (ex: Posso comprar PETR4? ou Analisar VALE3)..."):
        st.session_state["chat_messages"].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Analisando dados técnicos e regime de mercado..."):
                res = _run_chat_turn(prompt)
                if res.get("warning"):
                    st.warning(res["warning"])
                st.markdown(res["response"])
                meta_label = f"{res['provider']} ({res['model']})"
                st.caption(f"Motor: {meta_label}")
        st.session_state["chat_messages"].append({
            "role": "assistant",
            "content": res["response"],
            "meta": meta_label,
            "warning": res.get("warning"),
        })

# ==========================================
# 3. RADAR DE OPORTUNIDADES & PROVENTOS
# ==========================================
elif menu == "🎯 Radar de Oportunidades & Proventos":
    st.title("Radar de Oportunidades & Calendário de Proventos")

    tab1, tab2 = st.tabs(["🔍 Radar de Setups Técnicos", "📅 Calendário de Data COM (Dividendos & JCP)"])

    with tab1:
        st.subheader("Scanner de Confluência na B3")

        # Filtros de Segmento de Mercado e Setores
        with st.container():
            st.markdown('<div class="metric-card" style="margin-bottom:14px;">', unsafe_allow_html=True)
            c1, c2, c3 = st.columns([3, 3, 2])
            with c1:
                st.markdown("<span style='font-size:0.80rem; font-weight:700; text-transform:uppercase; color:#64748b;'>Universo B3</span>", unsafe_allow_html=True)
                segment_label = st.radio(
                    "Segmento de Mercado:",
                    [
                        "🌟 Universo Amplo B3 (~100 Ações)",
                        "🚀 Small & Mid Caps (Alto Crescimento)",
                        "🏢 Blue Chips Tradicionais (IBOV)",
                        "⚡ Top 20 Mais Líquidas",
                    ],
                    index=0,
                    label_visibility="collapsed",
                )
                only_uncorrelated = st.checkbox(
                    "🛡️ Ocultar ativos correlacionados à custódia",
                    value=False,
                    help="Elimina ações do mesmo setor ou com fatores de risco em comum com papéis que você já possui em carteira.",
                )
            with c2:
                st.markdown("<span style='font-size:0.80rem; font-weight:700; text-transform:uppercase; color:#64748b;'>Estratégia & Setor</span>", unsafe_allow_html=True)
                strategy_style = st.selectbox(
                    "Estilo Operacional Desejado:",
                    [
                        "🌟 Todas as Estratégias",
                        "🟢 Comprar na Baixa / Queda (Reversão IFR2)",
                        "🚀 Comprar na Força / Rompimento (Momentum)",
                        "🎯 Retomada de Fundo (Pivô Concluído)",
                        "💰 Captura de Proventos (Pré-Data COM)",
                    ],
                    index=0,
                    label_visibility="collapsed",
                )
                all_sectors = ["Todos os Setores"] + sorted(list({v["sector"] for v in B3_SECTORS_DATA.values()}))
                sector_filter = st.selectbox("Filtrar por Setor:", all_sectors, index=0)
            with c3:
                st.markdown("<span style='font-size:0.80rem; font-weight:700; text-transform:uppercase; color:#64748b;'>Confluência & Disparo</span>", unsafe_allow_html=True)
                only_high = st.checkbox("Alta Convicção (Score $\ge 8.0$)", value=False)
                if not only_high:
                    min_score = st.slider("Nota Mínima:", min_value=6.0, max_value=9.5, value=7.0, step=0.5)
                else:
                    min_score = 8.0
                st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
                btn_scan = st.button("🔄 Executar Scanner", type="primary", use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)

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
                  - *Seguidor de Tendência (Momentum):* Rompimento ou repique em médias móveis alinhadas no Sweet Spot (ampla pista livre até a máxima).
                  - *Retomada de Fundo (Pivô Concluído):* Conclusão de suporte / fundo duplo com superação da EMA 9 em ativos defasados (alta assimetria).
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
        if "Comprar na Baixa" in strategy_style:
            results = [r for r in results if r["strategy"] == "IFR2"]
        elif "Comprar na Força" in strategy_style:
            results = [r for r in results if r["strategy"] == "TREND"]
        elif "Retomada de Fundo" in strategy_style:
            results = [r for r in results if r["strategy"] == "REVERSAL_PIVOT"]
        elif "Captura de Proventos" in strategy_style:
            results = [r for r in results if r["strategy"] == "DIVIDEND_COM"]

        # Filtro de Setor da B3
        if sector_filter != "Todos os Setores":
            results = [r for r in results if r.get("sector") == sector_filter]

        # Filtro de Descorrelação contra a Custódia Atual do Usuário
        user_custody_positions = session.query(Position).filter_by(is_simulated=is_sim_mode).all()
        user_custody_tickers = [p.ticker for p in user_custody_positions]

        if only_uncorrelated and user_custody_tickers:
            results = [
                r for r in results
                if not check_sector_and_cluster_conflict(r["ticker"], user_custody_tickers)["has_conflict"]
            ]

        if results:
            st.success(f"Encontradas {len(results)} oportunidades com setup ativo.")

            # Monta dataframe formatado
            table_rows = []
            for r in results:
                info_link = f"[{r['ticker']} no StatusInvest]({r['info_url']})"
                shares_val = r.get("suggested_shares", 100)
                cap_val = r.get("suggested_capital", shares_val * r["entry_price"])
                adtv_val = f"R$ {r.get('adtv_milhoes', 0):.1f}M" if "adtv_milhoes" in r else "-"

                range_52s_str = f"{r.get('range_52w_pct', 0):.0f}% (Topo: R$ {r.get('high_52w', 0):.2f})" if "range_52w_pct" in r else "-"

                # Checa relação com a custódia atual
                sec_prof = get_asset_sector_profile(r["ticker"])
                sec_name = sec_prof.get("sector", "Outros")
                sub_name = sec_prof.get("subsector", "Geral")
                cluster_tags = ", ".join(sec_prof.get("clusters", []))

                div_status = "✓ Descorrelacionado"
                if user_custody_tickers:
                    conf = check_sector_and_cluster_conflict(r["ticker"], user_custody_tickers)
                    if conf.get("has_conflict"):
                        div_status = f"⚠️ Risco compartilhado ({', '.join(conf['conflicting_tickers'])})"

                table_rows.append({
                    "Código da Ação": r["ticker"],
                    "Setor": sec_name,
                    "Segmento": sub_name,
                    "Fator de Risco Macro": cluster_tags,
                    "Diversificação Carteira": div_status,
                    "Setup (Estratégia)": r["name"],
                    "Nota de Confluência": f"{r['score']:.1f} / 10",
                    "Preço Entrada (R$)": f"R$ {r['entry_price']:.2f}",
                    "Stop Loss (R$)": f"R$ {r['stop_loss']:.2f}",
                    "Alvo de Lucro (R$)": f"R$ {r['take_profit']:.2f}",
                    "Relação R/R": f"{r.get('rr_ratio', 'N/A')}x",
                    "Posição 52S": range_52s_str,
                    "Lote Sugerido (2% Risco)": f"{shares_val} ações",
                    "Capital Alocado": f"R$ {cap_val:,.2f}",
                    "ADTV 21": adtv_val,
                    "Análise Técnica Detalhada": r["reason"].replace("\n", " | "),
                    "Ficha Fundamentalista": info_link,
                })

            df_display = pd.DataFrame(table_rows)
            st.caption("💡 **Navegação Integrada:** Clique em qualquer linha ou no código da ação para abrir instantaneamente sua **Análise Gráfica e Variações de 1D a 10 Anos**.")
            selection_event = st.dataframe(
                df_display,
                width="stretch",
                column_config={
                    "Ficha Fundamentalista": st.column_config.LinkColumn("Ficha Fundamentalista"),
                },
                on_select="rerun",
                selection_mode="single-row",
                key="radar_table_select",
            )
            if selection_event and hasattr(selection_event, "selection") and selection_event.selection.rows:
                sel_idx = selection_event.selection.rows[0]
                if sel_idx < len(results):
                    target_opp = results[sel_idx]
                    target_ticker = target_opp["ticker"]
                    st.session_state["analysis_ticker"] = target_ticker
                    st.session_state["input_analysis_ticker"] = target_ticker
                    st.session_state["selected_page"] = "📈 Análise Gráfica & Variações (1D a 10A)"
                    st.rerun()
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

    if "input_analysis_ticker" not in st.session_state:
        st.session_state["input_analysis_ticker"] = st.session_state.get("analysis_ticker", "WEGE3")

    col_input, col_info = st.columns([1, 2])
    with col_input:
        selected_ticker = st.text_input(
            "Digite o Ticker da Ação (ex: WEGE3, PETR4, KEPL3, TAEE11):",
            key="input_analysis_ticker",
        ).strip().upper()
        if selected_ticker:
            st.session_state["analysis_ticker"] = selected_ticker

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
    env_title = "🧪 Laboratório de Simulação" if is_sim_mode else "💼 Carteira Real"
    st.title(f"Histórico de Trades e Curva de Capital — {env_title}")

    if is_sim_mode:
        st.caption("Exibindo métricas de performance das operações virtuais / simuladas (Paper Trading).")
    else:
        st.caption("Exibindo métricas de performance das operações reais executadas na corretora.")

    transactions = (
        session.query(Transaction)
        .filter_by(is_simulated=is_sim_mode)
        .order_by(Transaction.date.asc())
        .all()
    )
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

        with st.expander("🛠️ Cancelar ou Excluir Ordem Acidental"):
            st.markdown("Se você registrou uma ordem por engano ou com valores duplicados, selecione-a abaixo para excluí-la. A posição de custódia e o Preço Médio serão recalculados automaticamente.")
            tx_options = {
                f"ID #{t.id} - {t.date.strftime('%d/%m/%Y %H:%M')} | {t.type} {t.quantity} {t.ticker} @ R$ {t.price:.2f} (Taxas R$ {t.fees:.2f})": t.id
                for t in transactions
            }
            if tx_options:
                selected_tx_label = st.selectbox("Selecione a Transação a Excluir:", list(tx_options.keys()))
                del_c1, del_c2 = st.columns([2, 3])
                with del_c1:
                    if st.button("🗑️ Confirmar Exclusão da Ordem", type="primary"):
                        target_tx_id = tx_options[selected_tx_label]
                        deleted = delete_transaction(session, target_tx_id)
                        if deleted:
                            st.success(f"✓ Transação #{target_tx_id} excluída com sucesso! Custódia e impostos recalculados.")
                            st.rerun()
                        else:
                            st.error("Não foi possível excluir a transação.")
                with del_c2:
                    st.caption("A exclusão reverte as alterações na carteira e recalcula o Preço Médio a partir das transações restantes.")
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
        is_sim_order = st.checkbox(
            "🧪 Ordem de Simulação / Paper Trading (Sem dinheiro real)",
            value=is_sim_mode,
            help="Se marcado, a ordem será registrada no Laboratório de Simulação sem comprometer seu capital real nem afetar seus impostos.",
            key="buy_is_sim_order",
        )

        with st.container():
            col_search_t, col_search_act = st.columns([4, 1])
            with col_search_t:
                default_t = st.session_state.get("order_ticker", "")
                typed_ticker = st.text_input(
                    "Código da Ação B3:",
                    value=default_t,
                    key="order_ticker_input",
                    placeholder="Digite o código da ação (ex: PETR4, WEGE3, BBAS3)...",
                ).strip().upper()
            with col_search_act:
                st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
                st.button("🔍 Consultar", use_container_width=True)

        clean_typed = get_clean_ticker(typed_ticker) if typed_ticker else ""
        base_typed = get_base_ticker(typed_ticker) if typed_ticker else ""

        live_price = None
        suggested_stop = 28.50
        suggested_target = 33.50
        default_price = 30.00
        suggested_qty = st.session_state.get("order_qty", 100)
        default_strategy = st.session_state.get("order_strategy", "IFR2")

        if base_typed:
            with st.spinner(f"Consultando cotação e dados de mercado de {base_typed}..."):
                live_price = fetch_latest_price(base_typed)
                df_quote = fetch_ticker_data(clean_typed, period="1mo")

            if live_price and live_price > 0:
                if st.session_state.get("order_ticker") == base_typed and "order_price" in st.session_state:
                    default_price = float(st.session_state.get("order_price", live_price))
                    suggested_stop = float(st.session_state.get("order_stop", live_price * 0.95))
                    suggested_target = float(st.session_state.get("order_target", live_price * 1.10))
                else:
                    default_price = float(live_price)
                    atr = 0.0
                    if df_quote is not None and not df_quote.empty and len(df_quote) >= 5:
                        import pandas_ta as ta
                        df_quote.ta.atr(length=14, append=True)
                        atr_col = [c for c in df_quote.columns if c.startswith("ATRr")]
                        if atr_col and not df_quote[atr_col[0]].isna().all():
                            atr = float(df_quote[atr_col[0]].dropna().iloc[-1])
                    if atr > 0:
                        suggested_stop = round(max(0.01, live_price - 2.0 * atr), 2)
                        suggested_target = round(live_price + 2.5 * (2.0 * atr), 2)
                    else:
                        suggested_stop = round(live_price * 0.95, 2)
                        suggested_target = round(live_price * 1.10, 2)
                    sizing = calculate_position_size(
                        entry_price=live_price,
                        stop_loss=suggested_stop,
                        capital=DEFAULT_CAPITAL,
                    )
                    suggested_qty = max(1, int(sizing.get("shares", 100)))

                inf1, inf2, inf3, inf4 = st.columns(4)
                with inf1:
                    st.metric("Cotação Atual a Mercado", f"R$ {live_price:.2f}")
                with inf2:
                    st.metric("Stop Loss Sugerido", f"R$ {suggested_stop:.2f}")
                with inf3:
                    st.metric("Alvo Sugerido (2.5R)", f"R$ {suggested_target:.2f}")
                with inf4:
                    st.metric("Lote Sugerido (2% Risco)", f"{suggested_qty} ações")

                # Perfil Setorial e Auditoria de Conflito de Risco
                sec_prof = get_asset_sector_profile(base_typed)
                st.caption(
                    f"🏢 **Setor:** {sec_prof.get('sector', 'Diversificado')} | "
                    f"**Segmento:** {sec_prof.get('subsector', 'Geral')} | "
                    f"**Macro-Cluster:** {', '.join(sec_prof.get('clusters', []))}"
                )

                custody_positions = session.query(Position).filter_by(is_simulated=is_sim_order).all()
                custody_tickers = [p.ticker for p in custody_positions]

                if custody_tickers:
                    conflict_info = check_sector_and_cluster_conflict(base_typed, custody_tickers)
                    if conflict_info.get("has_conflict"):
                        st.warning(
                            f"⚠️ **Alerta de Concentração Setorial / Correlação de Risco:**\n\n"
                            f"• {conflict_info['warning_message']}\n\n"
                            f"🛡️ *Diretriz Institucional:* {conflict_info['recommendation']}"
                        )
                    else:
                        st.success("✓ **Diversificação Aprovada:** Ativo descorrelacionado das posições atuais na custódia.")

                existing_pos = session.query(Position).filter_by(ticker=base_typed, is_simulated=is_sim_order).first()
                if existing_pos:
                    env_name = "Simulação" if is_sim_order else "Real"
                    st.info(
                        f"📊 **Posição Existente em Custódia ({env_name}):** "
                        f"Você possui **{existing_pos.quantity} ações** com Preço Médio de **R$ {existing_pos.average_price:.2f}** "
                        f"(Custo Total: R$ {existing_pos.total_cost:,.2f})."
                    )
            else:
                st.warning(f"Não foi possível obter cotação automática para `{base_typed}`. Você pode preencher os valores manualmente.")

        st.markdown("---")
        st.markdown("##### Detalhes da Ordem de Compra")
        f_col1, f_col2 = st.columns(2)
        with f_col1:
            if isinstance(suggested_qty, dict):
                suggested_qty = suggested_qty.get("shares", 100)
            try:
                safe_qty_value = max(1, int(suggested_qty))
            except (ValueError, TypeError):
                safe_qty_value = 100

            qty = st.number_input("Quantidade de Ações", min_value=1, step=10, value=safe_qty_value, key="buy_qty_input")
            price = st.number_input("Preço de Execução (R$)", min_value=0.01, step=0.01, format="%.2f", value=float(default_price), key="buy_price_input")
            fees = st.number_input("Taxas e Emolumentos da B3 (R$)", min_value=0.0, step=0.10, value=1.50, key="buy_fees_input")
        with f_col2:
            stop_loss = st.number_input("Stop Loss (R$)", min_value=0.0, step=0.01, value=float(suggested_stop), key="buy_stop_input")
            take_profit = st.number_input("Take Profit / Alvo (R$)", min_value=0.0, step=0.01, value=float(suggested_target), key="buy_tp_input")
            strat_options = ["IFR2", "TREND", "REVERSAL_PIVOT", "DIVIDEND_COM", "MANUAL"]
            strat_idx = strat_options.index(default_strategy) if default_strategy in strat_options else 0
            strategy = st.selectbox("Estratégia", strat_options, index=strat_idx, key="buy_strat_select")

        with st.expander("🎯 Plano de Realização Parcial (Opcional - Scale-Out & Trailing)", expanded=False):
            st.caption("Defina o gatilho para realizar 50% dos lucros e subir o stop das ações restantes.")
            col_p1, col_p2, col_p3 = st.columns(3)
            with col_p1:
                part_target_in = st.number_input("Alvo da Parcial / TP1 (R$)", min_value=0.0, step=0.01, format="%.2f", value=0.0, key="buy_part_target")
            with col_p2:
                part_qty_in = st.number_input("Qtd da Parcial", min_value=0, step=1, value=int(qty // 2) if qty > 1 else 0, key="buy_part_qty")
            with col_p3:
                new_stop_in = st.number_input("Novo Stop pós-parcial (R$)", min_value=0.0, step=0.01, format="%.2f", value=0.0, key="buy_new_stop_part")

        notes = st.text_area("Notas / Justificativa da Entrada", key="buy_notes_input")

        total_op_val = (price * qty) + fees
        st.caption(f"💰 **Total da Operação:** {qty} ações @ R$ {price:.2f} + R$ {fees:.2f} taxas = **R$ {total_op_val:,.2f}**")

        submitted_buy = st.button("🛒 Confirmar Compra", type="primary", key="btn_confirm_buy", use_container_width=True)
        if submitted_buy:
            if not base_typed:
                st.error("Informe o ticker da ação antes de confirmar a compra.")
            else:
                submit_key = f"{base_typed}_{qty}_{price}_{is_sim_order}"
                now_ts = time.time()
                last_submit_key = st.session_state.get("last_submit_key")
                last_submit_time = st.session_state.get("last_submit_time", 0.0)

                if submit_key == last_submit_key and (now_ts - last_submit_time) < 4.0:
                    st.warning("⚠️ Esta ordem acabou de ser processada! Evitamos um registro duplicado.")
                else:
                    st.session_state["last_submit_key"] = submit_key
                    st.session_state["last_submit_time"] = now_ts

                    pos = execute_buy(
                        session=session,
                        ticker=base_typed,
                        quantity=qty,
                        price=price,
                        fees=fees,
                        stop_loss=stop_loss if stop_loss > 0 else None,
                        take_profit=take_profit if take_profit > 0 else None,
                        partial_target=part_target_in if part_target_in > 0 else None,
                        partial_quantity=part_qty_in if part_qty_in > 0 else None,
                        new_stop_after_partial=new_stop_in if new_stop_in > 0 else None,
                        strategy=strategy,
                        notes=notes,
                        is_simulated=is_sim_order,
                    )
                    env_label = "Simulada (Paper Trading)" if is_sim_order else "Real"
                    st.success(f"✓ Compra {env_label} registrada com sucesso! Posição atualizada para {pos.quantity} ações de {pos.ticker} a PM de R$ {pos.average_price:.2f}.")
                    for k in ["order_ticker", "order_price", "order_stop", "order_target", "order_qty", "order_strategy"]:
                        st.session_state.pop(k, None)

    with tab_sell:
        positions = session.query(Position).filter_by(is_simulated=is_sim_mode).all()
        env_label = "simulada" if is_sim_mode else "real"
        if not positions:
            st.info(f"Nenhuma posição em custódia {env_label} disponível para venda.")
        else:
            ticker_sell = st.selectbox("Selecione o Ativo em Custódia", [p.ticker for p in positions], key="sell_pos_select")
            selected_pos = session.query(Position).filter_by(ticker=ticker_sell, is_simulated=is_sim_mode).first()
            st.caption(f"Quantidade em custódia {env_label}: {selected_pos.quantity} | Preço Médio: R$ {selected_pos.average_price:.2f}")

            s_col1, s_col2 = st.columns(2)
            with s_col1:
                qty_sell = st.number_input("Quantidade a Vender", min_value=1, max_value=selected_pos.quantity, step=10, value=selected_pos.quantity, key="sell_qty_input")
                price_sell = st.number_input("Preço de Venda (R$)", min_value=0.01, step=0.01, format="%.2f", value=selected_pos.average_price * 1.05, key="sell_price_input")
            with s_col2:
                fees_sell = st.number_input("Taxas e Emolumentos (R$)", min_value=0.0, step=0.10, value=1.50, key="sell_fees_input")
                notes_sell = st.text_area("Notas do Encerramento", key="sell_notes_input")

            is_partial = qty_sell < selected_pos.quantity
            new_stop_for_sell = None
            if is_partial:
                st.info(f"💡 **Venda Parcial Detectada:** Você está vendendo {qty_sell} de {selected_pos.quantity} ações.")
                sugg_st = selected_pos.new_stop_after_partial or selected_pos.average_price
                new_stop_for_sell = st.number_input("Novo Stop Loss para as ações restantes (R$)", value=float(sugg_st), step=0.01, format="%.2f", key="sell_new_stop_in")

            total_sell_val = (price_sell * qty_sell) - fees_sell
            pnl_proj = (price_sell - selected_pos.average_price) * qty_sell - fees_sell
            st.caption(f"💰 **Valor Líquido Previsto:** R$ {total_sell_val:,.2f} | PnL Líquido Estimado: R$ {pnl_proj:,.2f}")

            submitted_sell = st.button("💰 Confirmar Venda", type="primary", key="btn_confirm_sell", use_container_width=True)
            if submitted_sell:
                if is_partial:
                    res = execute_partial_sale(
                        session=session,
                        ticker=ticker_sell,
                        quantity=qty_sell,
                        price=price_sell,
                        new_stop_loss=new_stop_for_sell,
                        fees=fees_sell,
                        notes=notes_sell,
                        is_simulated=is_sim_mode,
                    )
                    st.success(f"✓ Realização Parcial {env_label} confirmada! Lucro realizado: R$ {res['realized_pnl']:,.2f} ({res['realized_pnl_pct']:+.2f}%).")
                    st.markdown("**📋 Roteiro de Execução no Home Broker:**")
                    for step in res["broker_instructions"]:
                        st.markdown(f"- {step}")
                else:
                    res = execute_sell(
                        session=session,
                        ticker=ticker_sell,
                        quantity=qty_sell,
                        price=price_sell,
                        fees=fees_sell,
                        notes=notes_sell,
                        is_simulated=is_sim_mode,
                    )
                    st.success(f"✓ Venda {env_label} confirmada! PnL Líquido Realizado: R$ {res['realized_pnl']:,.2f} ({res['realized_pnl_pct']:+.2f}%).")

session.close()
