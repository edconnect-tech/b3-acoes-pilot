"""Estratégia de negociação e captura técnica no período pré-Data COM (Dividendos e JCP)."""

from typing import Dict, Any, Optional
import pandas as pd
import pandas_ta as ta

from b3pilot.data.dividends_feed import get_ticker_dividend_calendar
from b3pilot.core.strategies import compute_indicators


def evaluate_dividend_setup(df: pd.DataFrame, ticker: str) -> Optional[Dict[str, Any]]:
    """Avalia oportunidade de compra no período legal pré-Data COM com proteção técnica."""
    div_info = get_ticker_dividend_calendar(ticker)
    if not div_info or not div_info.get("is_upcoming"):
        return None

    days_until_com = div_info["days_until_com"]

    # Foco no período ideal de posicionamento: entre 2 e 8 dias antes da Data COM
    if days_until_com < 1 or days_until_com > 8:
        return None

    if len(df) < 60:
        return None

    data = compute_indicators(df)
    last = data.iloc[-1]

    close = float(last["Close"])
    sma50 = float(last["SMA_50"])
    atr = float(last["ATR_14"]) if pd.notna(last["ATR_14"]) else (close * 0.03)

    # Dissenso Construtivo / Filtro de Segurança Essencial:
    # Não comprar ação em tendência de baixa apenas pelo dividendo.
    # O papel DEVE estar acima da SMA 50 para garantir suporte de mercado.
    is_supported = close >= sma50

    if not is_supported:
        return None

    projected_yield = div_info["projected_yield_pct"]
    stop_loss = round(close - (atr * 1.5), 2)
    risk = close - stop_loss

    # Alvo inicial: topo recente ou valorização pré-Data COM
    target = round(close + (atr * 2.0), 2)
    rr_ratio = round((target - close) / risk, 2) if risk > 0 else 1.0

    score = 7.0
    if projected_yield > 2.0:
        score += 1.5
    elif projected_yield > 1.0:
        score += 1.0

    if days_until_com <= 4:
        score += 0.5  # Janela de tempo de alta atratividade

    return {
        "strategy": "DIVIDEND_COM",
        "name": "Captura Pré-Data COM",
        "signal": "BUY",
        "entry_price": round(close, 2),
        "stop_loss": stop_loss,
        "take_profit": target,
        "rr_ratio": rr_ratio,
        "score": min(round(score, 1), 10.0),
        "data_com": div_info["data_com"].strftime("%d/%m/%Y"),
        "data_ex": div_info["data_ex"].strftime("%d/%m/%Y"),
        "days_until_com": days_until_com,
        "estimated_value": div_info["estimated_value"],
        "projected_yield_pct": round(projected_yield, 2),
        "reason": (
            f"Data COM em {div_info['data_com'].strftime('%d/%m/%Y')} (em {days_until_com} dias). "
            f"Provento est.: R$ {div_info['estimated_value']:.2f} ({projected_yield:.2f}%). "
            f"Ativo sustentado acima da SMA 50 (R$ {sma50:.2f})."
        ),
    }
