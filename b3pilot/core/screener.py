"""Scanner unificado da B3 com filtro de confluência para Compras Vantajosas."""

from typing import List, Dict, Any, Optional
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from b3pilot.data.b3_feed import (
    fetch_ticker_data,
    get_base_ticker,
    get_statusinvest_url,
    get_tradingview_url,
)
from b3pilot.data.universe import get_universe
from b3pilot.core.strategies import evaluate_ifr2_setup, evaluate_trend_setup
from b3pilot.core.dividend_strategy import evaluate_dividend_setup


def run_screener(
    tickers: Optional[List[str]] = None,
    category: str = "all",
    min_score: float = 7.0,
    high_conviction_only: bool = False,
    show_progress: bool = True,
) -> List[Dict[str, Any]]:
    """Varre os ativos da B3 avaliando setups técnicos e proventos.
    
    Se high_conviction_only for True, retorna apenas compras com Score >= 8.0 e R/R >= 2.2.
    """
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

        # 1. Avalia IFR2
        ifr2_res = evaluate_ifr2_setup(df)
        if ifr2_res:
            ifr2_res["ticker"] = base_ticker
            ifr2_res["info_url"] = info_link
            ifr2_res["chart_url"] = chart_link
            results.append(ifr2_res)

        # 2. Avalia Seguidor de Tendência
        trend_res = evaluate_trend_setup(df)
        if trend_res:
            trend_res["ticker"] = base_ticker
            trend_res["info_url"] = info_link
            trend_res["chart_url"] = chart_link
            results.append(trend_res)

        # 3. Avalia Oportunidade Pré-Data COM
        div_res = evaluate_dividend_setup(df, ticker)
        if div_res:
            div_res["ticker"] = base_ticker
            div_res["info_url"] = info_link
            div_res["chart_url"] = chart_link
            results.append(div_res)

    if progress_context:
        with progress_context:
            task = progress_context.add_task(f"Escaneando {len(tickers)} ativos da B3...", total=len(tickers))
            for ticker in tickers:
                scan_single_ticker(ticker)
                progress_context.advance(task)
    else:
        for ticker in tickers:
            scan_single_ticker(ticker)

    # Aplica filtros
    filtered = [r for r in results if r["score"] >= min_score]

    if high_conviction_only:
        filtered = [
            r for r in filtered
            if (r["score"] >= 8.0 and r.get("rr_ratio", 1.0) >= 2.2)
            or (r["strategy"] == "DIVIDEND_COM" and r["score"] >= 8.0)
        ]

    # Ordena pelo maior score de confluência
    filtered.sort(key=lambda x: x["score"], reverse=True)
    return filtered
