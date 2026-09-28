"""Rastreamento de proventos (Dividendos e JCP), Data COM e Data EX para B3."""

from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Any
import yfinance as yf
import pandas as pd

from b3pilot.data.b3_feed import get_clean_ticker, get_base_ticker, fetch_latest_price


def get_ticker_dividend_calendar(ticker: str) -> Optional[Dict[str, Any]]:
    """Obtém informações sobre próximos proventos (Ex-Date, Data COM estimada) de um ativo."""
    clean_ticker = get_clean_ticker(ticker)
    base_ticker = get_base_ticker(ticker)

    try:
        yf_obj = yf.Ticker(clean_ticker)
        calendar = yf_obj.calendar

        if not calendar or not isinstance(calendar, dict):
            return None

        ex_date = calendar.get("Ex-Dividend Date")
        if not ex_date:
            return None

        if isinstance(ex_date, str):
            ex_date = datetime.strptime(ex_date, "%Y-%m-%d").date()
        elif isinstance(ex_date, datetime):
            ex_date = ex_date.date()

        today = date.today()
        # Data COM no Brasil é tipicamente o dia útil anterior à Data EX
        # Aproximação: 1 dia útil antes
        days_to_subtract = 3 if ex_date.weekday() == 0 else 1
        data_com = ex_date - timedelta(days=days_to_subtract)

        # Último provento distribuído como referência de valor por ação
        div_history = yf_obj.dividends
        last_div_val = float(div_history.iloc[-1]) if not div_history.empty else 0.0

        current_price = fetch_latest_price(clean_ticker) or 1.0
        projected_yield = (last_div_val / current_price) * 100 if current_price > 0 else 0.0

        days_until_com = (data_com - today).days

        return {
            "ticker": base_ticker,
            "data_com": data_com,
            "data_ex": ex_date,
            "days_until_com": days_until_com,
            "estimated_value": last_div_val,
            "current_price": current_price,
            "projected_yield_pct": projected_yield,
            "is_upcoming": days_until_com >= 0,
        }
    except Exception as e:
        return None


def scan_upcoming_dividends(universe: List[str], max_days_ahead: int = 15) -> List[Dict[str, Any]]:
    """Varre o universo de ações buscando ativos com Data COM nos próximos dias."""
    upcoming = []
    for ticker in universe:
        info = get_ticker_dividend_calendar(ticker)
        if info and info["is_upcoming"] and info["days_until_com"] <= max_days_ahead:
            upcoming.append(info)

    # Ordena pelos mais próximos da Data COM
    upcoming.sort(key=lambda x: x["days_until_com"])
    return upcoming
