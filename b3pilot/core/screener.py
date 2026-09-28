"""Scanner unificado da B3 com filtro de confluência, Regime de Mercado e Position Sizing."""

from typing import List, Dict, Any, Optional
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from b3pilot.data.b3_feed import (
    fetch_ticker_data,
    get_base_ticker,
    get_statusinvest_url,
    get_tradingview_url,
)
from b3pilot.data.universe import get_universe
from b3pilot.core.strategies import evaluate_ifr2_setup, evaluate_trend_setup, evaluate_bear_setup
from b3pilot.core.dividend_strategy import evaluate_dividend_setup
from b3pilot.core.regime import analyze_market_regime
from b3pilot.core.risk import calculate_position_size
from b3pilot.config import (
    DEFAULT_CAPITAL,
    RISK_MAX_PER_TRADE_PERCENT,
    MAX_POSITION_ALLOCATION_PERCENT,
)


def run_screener(
    tickers: Optional[List[str]] = None,
    category: str = "all",
    min_score: float = 7.0,
    high_conviction_only: bool = False,
    show_progress: bool = True,
    capital: float = DEFAULT_CAPITAL,
    include_bear_signals: bool = False,
) -> List[Dict[str, Any]]:
    """Varre os ativos da B3 aplicando:
      1. Gatekeeper de Regime de Mercado (IBOVESPA)
      2. Filtros de Liquidez Financeira Real (ADTV >= R$ 5M)
      3. Setups Quantitativos (IFR2, Momentum com Pullback, Pré-Data COM)
      4. Position Sizing Automático (Lote sugerido por risco fixo de 2%)
    """
    regime = analyze_market_regime()

    # Em caso de pânico sistêmico, novas compras são bloqueadas
    if regime["status"] == "PANIC":
        return []

    if tickers is None:
        tickers = get_universe(category=category)

    results: List[Dict[str, Any]] = []

    progress_context = (
        Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        )
        if show_progress
        else None
    )

    def scan_single_ticker(ticker: str):
        base_ticker = get_base_ticker(ticker)
        df = fetch_ticker_data(ticker)
        if df is None or len(df) < 50:
            return

        info_link = get_statusinvest_url(base_ticker)
        chart_link = get_tradingview_url(base_ticker)

        # 1. Avalia IFR2 (se BEAR market, exige sobrevenda extrema <= 5.0)
        if regime["allow_ifr2"]:
            require_extreme = regime["status"] == "BEAR"
            ifr2_res = evaluate_ifr2_setup(df, require_extreme_only=require_extreme)
            if ifr2_res:
                ifr2_res["ticker"] = base_ticker
                ifr2_res["info_url"] = info_link
                ifr2_res["chart_url"] = chart_link
                results.append(ifr2_res)

        # 2. Avalia Seguidor de Tendência (bloqueado em Bear Market ou Correção do Ibovespa)
        if regime["allow_momentum"]:
            trend_res = evaluate_trend_setup(df)
            if trend_res:
                trend_res["ticker"] = base_ticker
                trend_res["info_url"] = info_link
                trend_res["chart_url"] = chart_link
                results.append(trend_res)

        # 3. Avalia Oportunidade Pré-Data COM (bloqueado em Bear Market)
        if regime["allow_dividends"]:
            div_res = evaluate_dividend_setup(df, ticker)
            if div_res:
                div_res["ticker"] = base_ticker
                div_res["info_url"] = info_link
                div_res["chart_url"] = chart_link
                results.append(div_res)

        # 4. Avalia Sinal de Baixa / Pressão Vendedora (opcional)
        if include_bear_signals:
            bear_res = evaluate_bear_setup(df)
            if bear_res:
                bear_res["ticker"] = base_ticker
                bear_res["info_url"] = info_link
                bear_res["chart_url"] = chart_link
                results.append(bear_res)

    if progress_context:
        with progress_context:
            task = progress_context.add_task(f"Escaneando {len(tickers)} ativos da B3...", total=len(tickers))
            for ticker in tickers:
                scan_single_ticker(ticker)
                progress_context.advance(task)
    else:
        for ticker in tickers:
            scan_single_ticker(ticker)

    # Aplica filtros de score
    filtered = [r for r in results if r["score"] >= min_score]

    if high_conviction_only:
        filtered = [
            r for r in filtered
            if (r["score"] >= 8.0 and r.get("rr_ratio", 1.0) >= 2.2)
            or (r["strategy"] == "DIVIDEND_COM" and r["score"] >= 8.0)
        ]

    # Dimensionamento de Posição (Position Sizing) para cada oportunidade aprovada
    for item in filtered:
        if item.get("signal") == "BUY" and "entry_price" in item and "stop_loss" in item:
            sizing = calculate_position_size(
                entry_price=item["entry_price"],
                stop_loss=item["stop_loss"],
                capital=capital,
                risk_pct=RISK_MAX_PER_TRADE_PERCENT,
                max_allocation_pct=MAX_POSITION_ALLOCATION_PERCENT,
                allocation_multiplier=regime["allocation_multiplier"],
            )
            item["suggested_shares"] = sizing["shares"]
            item["suggested_capital"] = sizing["total_value"]
            item["actual_risk_money"] = sizing["total_risk_money"]
            item["actual_risk_pct"] = sizing["actual_risk_pct"]
            item["market_regime"] = regime["status"]
            item["regime_name"] = regime["name"]

    # Ordena pelo maior score de confluência
    filtered.sort(key=lambda x: x["score"], reverse=True)
    return filtered
