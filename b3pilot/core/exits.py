"""Motor de avaliação de saídas: Stop Loss, Take Profit, Trailing Stop e Time-Stop."""

from datetime import datetime, timedelta
from typing import List, Dict, Any
from sqlalchemy.orm import Session

from b3pilot.ledger.db import Position
from b3pilot.data.b3_feed import fetch_ticker_data, fetch_latest_price, get_clean_ticker
from b3pilot.core.strategies import compute_indicators
from b3pilot.config import TIME_STOP_DAYS, ATR_TRAILING_MULTIPLIER


def evaluate_open_positions_exits(session: Session) -> List[Dict[str, Any]]:
    """Avalia todas as posições em custódia e identifica se alguma atingiu gatilho de VENDA."""
    positions = session.query(Position).all()
    exit_signals = []

    for pos in positions:
        ticker = pos.ticker
        clean_ticker = get_clean_ticker(ticker)
        df = fetch_ticker_data(clean_ticker, period="1mo")

        if df is None or df.empty:
            continue

        data = compute_indicators(df)
        last = data.iloc[-1]
        current_price = float(last["Close"])
        high_price = float(last["High"])
        atr = float(last["ATR_14"]) if pd_not_na(last["ATR_14"]) else (current_price * 0.03)

        # 1. Atualiza máxima histórica da posição para calibrar Trailing Stop
        if pos.highest_price is None or high_price > pos.highest_price:
            pos.highest_price = high_price
            # Se for seguidor de tendência, eleva o Trailing Stop
            if pos.strategy == "TREND" or pos.trailing_stop is not None:
                new_trailing = round(high_price - (atr * ATR_TRAILING_MULTIPLIER), 2)
                if pos.trailing_stop is None or new_trailing > pos.trailing_stop:
                    pos.trailing_stop = new_trailing

        # 2. Checagem de Stop Loss inegociável
        if pos.stop_loss and current_price <= pos.stop_loss:
            exit_signals.append({
                "ticker": ticker,
                "type": "SELL_STOP_LOSS",
                "urgency": "ALTA",
                "price": current_price,
                "trigger_price": pos.stop_loss,
                "strategy": pos.strategy,
                "quantity": pos.quantity,
                "entry_price": pos.average_price,
                "pnl_pct": round(((current_price - pos.average_price) / pos.average_price) * 100, 2),
                "reason": f"🛑 STOP LOSS ATINGIDO: Cotação (R$ {current_price:.2f}) atingiu o limite de proteção (R$ {pos.stop_loss:.2f}). Encerrar para preservar capital.",
            })
            continue

        # 3. Checagem de Trailing Stop Móvel
        if pos.trailing_stop and current_price <= pos.trailing_stop:
            exit_signals.append({
                "ticker": ticker,
                "type": "SELL_TRAILING_STOP",
                "urgency": "ALTA",
                "price": current_price,
                "trigger_price": pos.trailing_stop,
                "strategy": pos.strategy,
                "quantity": pos.quantity,
                "entry_price": pos.average_price,
                "pnl_pct": round(((current_price - pos.average_price) / pos.average_price) * 100, 2),
                "reason": f"📈 TRAILING STOP ATINGIDO: Cotação recuou para R$ {current_price:.2f}, ativando o stop móvel em R$ {pos.trailing_stop:.2f}. Lucro travado.",
            })
            continue

        # 4. Checagem de Take Profit (Alvo Final)
        if pos.take_profit and current_price >= pos.take_profit:
            exit_signals.append({
                "ticker": ticker,
                "type": "SELL_TAKE_PROFIT",
                "urgency": "MEDIA",
                "price": current_price,
                "trigger_price": pos.take_profit,
                "strategy": pos.strategy,
                "quantity": pos.quantity,
                "entry_price": pos.average_price,
                "pnl_pct": round(((current_price - pos.average_price) / pos.average_price) * 100, 2),
                "reason": f"🎯 TAKE PROFIT ATINGIDO: Cotação atingiu o alvo projetado em R$ {pos.take_profit:.2f} (Atual: R$ {current_price:.2f}). Realizar lucros.",
            })
            continue

        # 5. Saída específica do setup IFR2 (Máxima dos últimos 2 dias)
        if pos.strategy == "IFR2":
            high_2d = float(last["HIGH_2D"]) if pd_not_na(last["HIGH_2D"]) else None
            if high_2d and current_price >= high_2d:
                exit_signals.append({
                    "ticker": ticker,
                    "type": "SELL_IFR2_TARGET",
                    "urgency": "MEDIA",
                    "price": current_price,
                    "trigger_price": high_2d,
                    "strategy": pos.strategy,
                    "quantity": pos.quantity,
                    "entry_price": pos.average_price,
                    "pnl_pct": round(((current_price - pos.average_price) / pos.average_price) * 100, 2),
                    "reason": f"⚡ ALVO IFR2 ATINGIDO: Papel repicou e superou a máxima de 2 dias (R$ {high_2d:.2f}). Encerrar posição de curto prazo.",
                })
                continue

        # 6. Checagem de Time-Stop (Posição estagnada)
        days_in_trade = (datetime.utcnow() - pos.entry_date).days
        if days_in_trade >= TIME_STOP_DAYS:
            pnl_pct = ((current_price - pos.average_price) / pos.average_price) * 100
            # Se após 10 pregões não andou nem 2%, encerra para desalocar capital
            if abs(pnl_pct) < 2.0:
                exit_signals.append({
                    "ticker": ticker,
                    "type": "SELL_TIME_STOP",
                    "urgency": "BAIXA",
                    "price": current_price,
                    "trigger_price": current_price,
                    "strategy": pos.strategy,
                    "quantity": pos.quantity,
                    "entry_price": pos.average_price,
                    "pnl_pct": round(pnl_pct, 2),
                    "reason": f"⏳ TIME-STOP: Operação estagnada há {days_in_trade} dias (PnL {pnl_pct:+.2f}%). Liberar margem para novos trades.",
                })

    try:
        session.commit()
    except Exception:
        session.rollback()

    return exit_signals


def pd_not_na(val) -> bool:
    import pandas as pd
    return pd.notna(val)
