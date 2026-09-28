"""Gerenciamento de ordens, custódia e Preço Médio Ponderado da carteira."""

from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from b3pilot.ledger.db import Transaction, Position
from b3pilot.ledger.taxes import recalculate_monthly_taxes
from b3pilot.data.b3_feed import get_base_ticker, fetch_latest_price


def execute_buy(
    session: Session,
    ticker: str,
    quantity: int,
    price: float,
    fees: float = 0.0,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None,
    strategy: str = "MANUAL",
    notes: Optional[str] = None,
    date: Optional[datetime] = None,
) -> Position:
    """Registra uma ordem de COMPRA, atualizando a custódia e o Preço Médio oficial."""
    base_ticker = get_base_ticker(ticker)
    tx_date = date or datetime.utcnow()

    total_cost_operation = (price * quantity) + fees

    # Registra no histórico de transações
    tx = Transaction(
        date=tx_date,
        ticker=base_ticker,
        type="BUY",
        quantity=quantity,
        price=price,
        fees=fees,
        total_value=total_cost_operation,
        realized_pnl=0.0,
        strategy=strategy,
        notes=notes,
    )
    session.add(tx)

    # Atualiza ou cria a posição em custódia
    pos = session.query(Position).filter_by(ticker=base_ticker).first()
    if pos:
        old_total_cost = pos.average_price * pos.quantity
        new_quantity = pos.quantity + quantity
        # Novo Preço Médio Ponderado (inclui taxas de compra)
        new_avg_price = (old_total_cost + total_cost_operation) / new_quantity
        pos.quantity = new_quantity
        pos.average_price = round(new_avg_price, 4)
        pos.total_cost = round(new_avg_price * new_quantity, 2)
        if stop_loss:
            pos.stop_loss = stop_loss
        if take_profit:
            pos.take_profit = take_profit
    else:
        # Primeira compra do ativo
        avg_price = total_cost_operation / quantity
        pos = Position(
            ticker=base_ticker,
            quantity=quantity,
            average_price=round(avg_price, 4),
            total_cost=round(total_cost_operation, 2),
            stop_loss=stop_loss,
            take_profit=take_profit,
            trailing_stop=stop_loss,
            highest_price=price,
            strategy=strategy,
            entry_date=tx_date,
        )
        session.add(pos)

    session.commit()
    session.refresh(pos)
    return pos


def execute_sell(
    session: Session,
    ticker: str,
    quantity: int,
    price: float,
    fees: float = 0.0,
    notes: Optional[str] = None,
    date: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Registra uma ordem de VENDA, calcula PnL líquido e atualiza obrigações fiscais."""
    base_ticker = get_base_ticker(ticker)
    tx_date = date or datetime.utcnow()

    pos = session.query(Position).filter_by(ticker=base_ticker).first()
    if not pos or pos.quantity < quantity:
        raise ValueError(
            f"Quantidade insuficiente em custódia para vender {quantity} de {base_ticker}. "
            f"Disponível: {pos.quantity if pos else 0}."
        )

    # Cálculo oficial da Receita Federal:
    # Receita líquida da venda = (Preço * Quantidade) - Taxas
    net_sale_value = (price * quantity) - fees
    # Custo de aquisição proporcional pelo Preço Médio
    acquisition_cost = pos.average_price * quantity
    # Resultado Líquido da Operação
    realized_pnl = net_sale_value - acquisition_cost

    tx = Transaction(
        date=tx_date,
        ticker=base_ticker,
        type="SELL",
        quantity=quantity,
        price=price,
        fees=fees,
        total_value=price * quantity,
        realized_pnl=round(realized_pnl, 2),
        strategy=pos.strategy,
        notes=notes,
    )
    session.add(tx)

    # Atualiza posição
    remaining_qty = pos.quantity - quantity
    if remaining_qty == 0:
        session.delete(pos)
    else:
        pos.quantity = remaining_qty
        pos.total_cost = round(pos.average_price * remaining_qty, 2)

    session.commit()

    # Recalcula apuração fiscal do mês
    year_month = tx_date.strftime("%Y-%m")
    tax_record = recalculate_monthly_taxes(session, year_month)

    return {
        "ticker": base_ticker,
        "quantity_sold": quantity,
        "sale_price": price,
        "realized_pnl": round(realized_pnl, 2),
        "realized_pnl_pct": round((realized_pnl / acquisition_cost) * 100, 2) if acquisition_cost > 0 else 0.0,
        "remaining_quantity": remaining_qty,
        "tax_year_month": year_month,
        "is_exempt_month": tax_record.is_exempt,
        "final_darf_month": tax_record.final_darf,
    }


def get_portfolio_summary(session: Session) -> Dict[str, Any]:
    """Retorna o estado consolidado da carteira atual com cotações a mercado."""
    positions = session.query(Position).all()

    total_invested = 0.0
    current_market_value = 0.0
    positions_data = []

    for pos in positions:
        current_price = fetch_latest_price(pos.ticker) or pos.average_price
        position_market_val = current_price * pos.quantity
        unrealized_pnl = position_market_val - pos.total_cost
        unrealized_pnl_pct = (unrealized_pnl / pos.total_cost) * 100 if pos.total_cost > 0 else 0.0

        total_invested += pos.total_cost
        current_market_value += position_market_val

        positions_data.append({
            "ticker": pos.ticker,
            "quantity": pos.quantity,
            "average_price": pos.average_price,
            "current_price": round(current_price, 2),
            "total_cost": pos.total_cost,
            "market_value": round(position_market_val, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "unrealized_pnl_pct": round(unrealized_pnl_pct, 2),
            "stop_loss": pos.stop_loss,
            "take_profit": pos.take_profit,
            "trailing_stop": pos.trailing_stop,
            "strategy": pos.strategy,
            "entry_date": pos.entry_date.strftime("%d/%m/%Y") if pos.entry_date else "-",
        })

    total_unrealized_pnl = current_market_value - total_invested
    total_unrealized_pnl_pct = (total_unrealized_pnl / total_invested) * 100 if total_invested > 0 else 0.0

    return {
        "positions": positions_data,
        "total_invested": round(total_invested, 2),
        "current_market_value": round(current_market_value, 2),
        "total_unrealized_pnl": round(total_unrealized_pnl, 2),
        "total_unrealized_pnl_pct": round(total_unrealized_pnl_pct, 2),
        "num_positions": len(positions_data),
    }
