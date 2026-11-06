"""Gerenciamento de ordens, custódia e Preço Médio Ponderado da carteira."""

from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from b3pilot.ledger.db import Transaction, Position, naive_utc_now
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
    partial_target: Optional[float] = None,
    partial_quantity: Optional[int] = None,
    new_stop_after_partial: Optional[float] = None,
    strategy: str = "MANUAL",
    notes: Optional[str] = None,
    date: Optional[datetime] = None,
    is_simulated: bool = False,
) -> Position:
    """Registra uma ordem de COMPRA (Real ou Simulada), atualizando a custódia e Preço Médio."""
    base_ticker = get_base_ticker(ticker)
    tx_date = date or naive_utc_now()

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
        is_simulated=is_simulated,
    )
    session.add(tx)

    # Atualiza ou cria a posição na respectiva custódia (Real ou Simulada)
    pos = session.query(Position).filter_by(ticker=base_ticker, is_simulated=is_simulated).first()
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
        if partial_target:
            pos.partial_target = partial_target
        if partial_quantity:
            pos.partial_quantity = partial_quantity
        if new_stop_after_partial:
            pos.new_stop_after_partial = new_stop_after_partial
    else:
        # Primeira compra do ativo neste ambiente
        avg_price = total_cost_operation / quantity
        pos = Position(
            ticker=base_ticker,
            quantity=quantity,
            average_price=round(avg_price, 4),
            total_cost=round(total_cost_operation, 2),
            stop_loss=stop_loss,
            take_profit=take_profit,
            partial_target=partial_target,
            partial_quantity=partial_quantity or (quantity // 2 if quantity > 1 else None),
            new_stop_after_partial=new_stop_after_partial,
            is_partial_executed=False,
            trailing_stop=stop_loss,
            highest_price=price,
            strategy=strategy,
            entry_date=tx_date,
            is_simulated=is_simulated,
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
    is_simulated: bool = False,
) -> Dict[str, Any]:
    """Registra uma ordem de VENDA, calcula PnL líquido e atualiza tributos apenas se for Real."""
    base_ticker = get_base_ticker(ticker)
    tx_date = date or naive_utc_now()

    pos = session.query(Position).filter_by(ticker=base_ticker, is_simulated=is_simulated).first()
    env_name = "simulada" if is_simulated else "real"
    if not pos or pos.quantity < quantity:
        raise ValueError(
            f"Quantidade insuficiente em custódia {env_name} para vender {quantity} de {base_ticker}. "
            f"Disponível: {pos.quantity if pos else 0}."
        )

    # Cálculo do resultado líquido da operação
    net_sale_value = (price * quantity) - fees
    acquisition_cost = pos.average_price * quantity
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
        is_simulated=is_simulated,
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

    year_month = tx_date.strftime("%Y-%m")
    # Recalcula apuração fiscal da Receita Federal APENAS se a operação for REAL
    if not is_simulated:
        tax_record = recalculate_monthly_taxes(session, year_month)
        is_exempt = tax_record.is_exempt
        final_darf = tax_record.final_darf
    else:
        is_exempt = True
        final_darf = 0.0

    return {
        "ticker": base_ticker,
        "quantity_sold": quantity,
        "sale_price": price,
        "realized_pnl": round(realized_pnl, 2),
        "realized_pnl_pct": round((realized_pnl / acquisition_cost) * 100, 2) if acquisition_cost > 0 else 0.0,
        "remaining_quantity": remaining_qty,
        "tax_year_month": year_month,
        "is_exempt_month": is_exempt,
        "final_darf_month": final_darf,
        "is_simulated": is_simulated,
    }


def execute_partial_sale(
    session: Session,
    ticker: str,
    quantity: int,
    price: float,
    new_stop_loss: Optional[float] = None,
    fees: float = 0.0,
    notes: Optional[str] = None,
    date: Optional[datetime] = None,
    is_simulated: bool = False,
) -> Dict[str, Any]:
    """Executa a Realização Parcial (Scale-Out) de uma posição,

    atualiza o Stop Loss da quantidade restante (para travar lucro/breakeven),
    mantém o preço médio de aquisição original e computa o roteiro para o Home Broker.
    """
    base_ticker = get_base_ticker(ticker)
    pos = session.query(Position).filter_by(ticker=base_ticker, is_simulated=is_simulated).first()
    if not pos:
        raise ValueError(f"Ativo {base_ticker} não encontrado em custódia.")

    initial_qty = pos.quantity
    avg_price = pos.average_price

    if quantity >= initial_qty:
        raise ValueError(
            f"Venda parcial inválida: a quantidade ({quantity}) deve ser menor que a posição total ({initial_qty}). "
            f"Para liquidar tudo, use o encerramento total."
        )

    # 1. Executa a venda da quantidade parcial via execute_sell
    sell_res = execute_sell(
        session=session,
        ticker=base_ticker,
        quantity=quantity,
        price=price,
        fees=fees,
        notes=notes or f"Realização Parcial ({quantity}/{initial_qty} ações a R$ {price:.2f})",
        date=date,
        is_simulated=is_simulated,
    )

    # 2. Atualiza a posição remanescente
    pos = session.query(Position).filter_by(ticker=base_ticker, is_simulated=is_simulated).first()
    if pos:
        pos.is_partial_executed = True
        if new_stop_loss is not None:
            pos.stop_loss = new_stop_loss
            if pos.trailing_stop and pos.trailing_stop < new_stop_loss:
                pos.trailing_stop = new_stop_loss
        session.commit()

    remaining_qty = pos.quantity if pos else 0
    realized_profit = sell_res["realized_pnl"]

    # 3. Cálculo de PnL no Pior Caso (se as ações restantes forem estopadas no novo stop)
    if pos and pos.stop_loss:
        worst_case_remaining_pnl = (pos.stop_loss - avg_price) * remaining_qty
        guaranteed_total_profit = realized_profit + worst_case_remaining_pnl
    else:
        worst_case_remaining_pnl = 0.0
        guaranteed_total_profit = realized_profit

    # 4. Roteiro de Execução Passo a Passo para o Home Broker
    broker_steps = [
        f"1. No Home Broker, vá na aba 'Ordens' e CANCELE o Stop antigo de {initial_qty} ações de {base_ticker}.",
        f"2. Na aba 'Boleta / Ordem', envie uma VENDA a mercado de {quantity} ações a R$ {price:.2f} (Lucro embolsado: R$ {realized_profit:+,.2f}).",
    ]
    if pos and pos.stop_loss:
        broker_steps.append(
            f"3. Na aba 'Stop', cadastre um NOVO STOP para as {remaining_qty} ações restantes no disparo de R$ {pos.stop_loss:.2f} "
            f"(Lucro mínimo garantido no trade: R$ {guaranteed_total_profit:+,.2f})."
        )

    return {
        "ticker": base_ticker,
        "quantity_sold": quantity,
        "sale_price": price,
        "realized_pnl": realized_profit,
        "realized_pnl_pct": sell_res["realized_pnl_pct"],
        "remaining_quantity": remaining_qty,
        "new_stop_loss": pos.stop_loss if pos else None,
        "average_price": avg_price,
        "guaranteed_total_pnl": round(guaranteed_total_profit, 2),
        "broker_instructions": broker_steps,
        "is_simulated": is_simulated,
    }


def simulate_partial_exit(
    session: Session,
    ticker: str,
    target_price: float,
    new_stop_loss: float,
    partial_pct: float = 0.5,
    is_simulated: bool = False,
) -> Dict[str, Any]:
    """Simula matematicamente o resultado de uma realização parcial e elevação de stop sem alterar o banco."""
    base_ticker = get_base_ticker(ticker)
    pos = session.query(Position).filter_by(ticker=base_ticker, is_simulated=is_simulated).first()
    if not pos:
        return {"error": f"Ativo {base_ticker} não está na custódia."}

    total_qty = pos.quantity
    avg_price = pos.average_price
    qty_to_sell = max(1, int(round(total_qty * partial_pct)))
    qty_remaining = total_qty - qty_to_sell

    realized_profit = (target_price - avg_price) * qty_to_sell
    realized_pct = ((target_price - avg_price) / avg_price) * 100

    worst_case_remaining_profit = (new_stop_loss - avg_price) * qty_remaining
    worst_case_remaining_pct = ((new_stop_loss - avg_price) / avg_price) * 100

    guaranteed_total_profit = realized_profit + worst_case_remaining_profit
    guaranteed_total_pct = (guaranteed_total_profit / pos.total_cost) * 100

    return {
        "ticker": base_ticker,
        "total_quantity": total_qty,
        "average_price": avg_price,
        "qty_to_sell": qty_to_sell,
        "qty_remaining": qty_remaining,
        "target_price": target_price,
        "new_stop_loss": new_stop_loss,
        "realized_profit_half": round(realized_profit, 2),
        "realized_pct_half": round(realized_pct, 2),
        "worst_case_remaining_profit": round(worst_case_remaining_profit, 2),
        "worst_case_remaining_pct": round(worst_case_remaining_pct, 2),
        "guaranteed_total_profit": round(guaranteed_total_profit, 2),
        "guaranteed_total_pct": round(guaranteed_total_pct, 2),
    }


def get_portfolio_summary(session: Session, is_simulated: Optional[bool] = False) -> Dict[str, Any]:
    """Retorna o estado consolidado da carteira (Real, Simulada ou Geral) com cotações a mercado."""
    query = session.query(Position)
    if is_simulated is not None:
        query = query.filter_by(is_simulated=is_simulated)
    positions = query.all()

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
            "partial_target": pos.partial_target,
            "partial_quantity": pos.partial_quantity,
            "new_stop_after_partial": pos.new_stop_after_partial,
            "is_partial_executed": pos.is_partial_executed,
            "trailing_stop": pos.trailing_stop,
            "strategy": pos.strategy,
            "entry_date": pos.entry_date.strftime("%d/%m/%Y") if pos.entry_date else "-",
            "is_simulated": pos.is_simulated,
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
        "is_simulated": is_simulated,
    }


def recalculate_position(session: Session, ticker: str, is_simulated: bool = False) -> Optional[Position]:
    """Reconstrói a posição de custódia a partir do histórico cronológico de transações."""
    base_ticker = get_base_ticker(ticker)
    txs = (
        session.query(Transaction)
        .filter_by(ticker=base_ticker, is_simulated=is_simulated)
        .order_by(Transaction.date.asc(), Transaction.id.asc())
        .all()
    )

    pos = session.query(Position).filter_by(ticker=base_ticker, is_simulated=is_simulated).first()

    if not txs:
        if pos:
            session.delete(pos)
            session.commit()
        return None

    current_qty = 0
    total_cost = 0.0
    last_stop = None
    last_target = None
    last_strat = "MANUAL"
    entry_date = None

    for tx in txs:
        if tx.type == "BUY":
            op_cost = (tx.price * tx.quantity) + tx.fees
            new_qty = current_qty + tx.quantity
            if new_qty > 0:
                avg = (total_cost + op_cost) / new_qty
                current_qty = new_qty
                total_cost = avg * current_qty
            if not entry_date:
                entry_date = tx.date
            last_strat = tx.strategy or last_strat
        elif tx.type == "SELL":
            if current_qty > 0:
                avg = total_cost / current_qty
                current_qty = max(0, current_qty - tx.quantity)
                total_cost = avg * current_qty
                if current_qty == 0:
                    entry_date = None

    if current_qty <= 0:
        if pos:
            session.delete(pos)
            session.commit()
        return None

    avg_price = total_cost / current_qty
    if not pos:
        pos = Position(
            ticker=base_ticker,
            quantity=current_qty,
            average_price=round(avg_price, 4),
            total_cost=round(total_cost, 2),
            stop_loss=last_stop,
            take_profit=last_target,
            trailing_stop=last_stop,
            highest_price=avg_price,
            strategy=last_strat,
            entry_date=entry_date or naive_utc_now(),
            is_simulated=is_simulated,
        )
        session.add(pos)
    else:
        pos.quantity = current_qty
        pos.average_price = round(avg_price, 4)
        pos.total_cost = round(total_cost, 2)

    session.commit()
    return pos


def delete_transaction(session: Session, transaction_id: int) -> bool:
    """Exclui uma transação e recalcula a custódia e tributos automaticamente."""
    tx = session.query(Transaction).filter_by(id=transaction_id).first()
    if not tx:
        return False

    ticker = tx.ticker
    is_sim = tx.is_simulated
    tx_type = tx.type
    ym = tx.date.strftime("%Y-%m")

    session.delete(tx)
    session.commit()

    recalculate_position(session, ticker, is_simulated=is_sim)
    if tx_type == "SELL" and not is_sim:
        recalculate_monthly_taxes(session, ym)
    return True

