"""Testes unitários para o módulo de Realização Parcial (Scale-Out) e Elevação de Stop."""

import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from b3pilot.ledger.db import Base, Position, naive_utc_now
from b3pilot.ledger.portfolio import execute_buy, execute_partial_sale, simulate_partial_exit
from b3pilot.core.exits import evaluate_open_positions_exits
from tests.test_core import generate_synthetic_ohlcv


def setup_in_memory_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    return Session()


def test_execute_partial_sale_scale_out():
    """Valida a realização de 50% da posição com elevação de stop das ações restantes."""
    session = setup_in_memory_db()

    # Cria posição de 62 ações de SOJA3 a R$ 8,00 com stop inicial em R$ 7,50
    pos = execute_buy(
        session=session,
        ticker="SOJA3",
        quantity=62,
        price=8.00,
        fees=0.0,
        stop_loss=7.50,
        take_profit=9.50,
        partial_target=8.60,
        partial_quantity=31,
        new_stop_after_partial=8.25,
        is_simulated=True,
    )
    assert pos.quantity == 62
    assert pos.average_price == 8.00

    # Executa a realização parcial de 31 ações a R$ 8,60 com novo stop em R$ 8,25
    res = execute_partial_sale(
        session=session,
        ticker="SOJA3",
        quantity=31,
        price=8.60,
        new_stop_loss=8.25,
        fees=0.0,
        is_simulated=True,
    )

    # 1. Validações da venda parcial
    assert res["quantity_sold"] == 31
    assert res["sale_price"] == 8.60
    assert res["realized_pnl"] == 18.60  # (8.60 - 8.00) * 31
    assert res["remaining_quantity"] == 31
    assert res["new_stop_loss"] == 8.25
    assert res["average_price"] == 8.00  # PM original preservado!
    # Lucro garantido no pior caso: 18.60 + ((8.25 - 8.00) * 31) = 18.60 + 7.75 = 26.35
    assert res["guaranteed_total_pnl"] == 26.35
    assert len(res["broker_instructions"]) == 3

    # 2. Validações no banco de dados da posição remanescente
    pos_updated = session.query(Position).filter_by(ticker="SOJA3", is_simulated=True).first()
    assert pos_updated.quantity == 31
    assert pos_updated.average_price == 8.00
    assert pos_updated.stop_loss == 8.25
    assert pos_updated.is_partial_executed is True

    session.close()


def test_simulate_partial_exit_math():
    """Valida a simulação matemática sem alterar o banco de dados."""
    session = setup_in_memory_db()

    execute_buy(
        session=session,
        ticker="SOJA3",
        quantity=62,
        price=8.00,
        is_simulated=True,
    )

    sim = simulate_partial_exit(
        session=session,
        ticker="SOJA3",
        target_price=8.60,
        new_stop_loss=8.25,
        partial_pct=0.5,
        is_simulated=True,
    )

    assert sim["total_quantity"] == 62
    assert sim["qty_to_sell"] == 31
    assert sim["qty_remaining"] == 31
    assert sim["realized_profit_half"] == 18.60
    assert sim["worst_case_remaining_profit"] == 7.75
    assert sim["guaranteed_total_profit"] == 26.35

    session.close()


def test_exits_trigger_partial_take_profit(monkeypatch):
    """Valida que o motor de saídas detecta quando o preço atinge o alvo parcial."""
    session = setup_in_memory_db()

    pos = Position(
        ticker="SOJA3",
        quantity=62,
        average_price=8.00,
        total_cost=496.00,
        stop_loss=7.50,
        take_profit=9.50,
        partial_target=8.60,
        partial_quantity=31,
        new_stop_after_partial=8.25,
        is_partial_executed=False,
        strategy="MANUAL",
        entry_date=naive_utc_now(),
        is_simulated=True,
    )
    session.add(pos)
    session.commit()

    # Mock de fetch_ticker_data retornando fechamento em R$ 8,62 (acima do alvo parcial de 8.60)
    df_mock = generate_synthetic_ohlcv(250, base_price=8.62)
    df_mock.loc[df_mock.index[-1], "Close"] = 8.62
    import b3pilot.core.exits as exits_mod
    monkeypatch.setattr(exits_mod, "fetch_ticker_data", lambda *args, **kwargs: df_mock)

    exits = evaluate_open_positions_exits(session, is_simulated=True)
    assert len(exits) == 1
    assert exits[0]["type"] == "PARTIAL_TAKE_PROFIT"
    assert exits[0]["ticker"] == "SOJA3"
    assert exits[0]["partial_quantity"] == 31
    assert exits[0]["remaining_quantity"] == 31
    assert exits[0]["new_stop"] == 8.25
    assert "Roteiro:" in exits[0]["reason"]

    session.close()
