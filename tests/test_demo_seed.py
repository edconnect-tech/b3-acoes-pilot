"""Testes unitários do seed de carteira simulada (Paper Trading) com isolamento Zero Trust."""

from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from b3pilot.ledger.db import Base, MonthlyTaxRecord, Position, Transaction
from scripts.seed_demo_portfolio import seed_demo_portfolio


def _create_memory_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    return Session()


def test_seed_demo_portfolio_creates_diversified_simulated_positions():
    """Garante criação de 5 posições simuladas em 5 setores/clusters distintos + 2 trades fechados."""
    session = _create_memory_session()
    try:
        res = seed_demo_portfolio(session, reset=True, use_live_prices=False)
        assert res["skipped"] is False
        assert res["open_positions"] == 5
        assert res["closed_trades"] == 2
        assert len(set(res["sectors"])) == 5
        assert len(set(res["clusters"])) == 5

        sim_positions = session.query(Position).filter_by(is_simulated=True).all()
        assert len(sim_positions) == 5

        sim_sells = session.query(Transaction).filter_by(is_simulated=True, type="SELL").all()
        assert len(sim_sells) == 2
        pnls = {tx.ticker: tx.realized_pnl for tx in sim_sells}
        assert pnls["VALE3"] > 0
        assert pnls["LREN3"] < 0
    finally:
        session.close()


def test_seed_demo_portfolio_zero_trust_preserves_real_custody():
    """Garante que --reset nunca apaga nem altera custódia real nem registros fiscais de DARF."""
    session = _create_memory_session()
    try:
        # Pré-popula dados reais que NÃO podem ser tocados
        real_pos = Position(
            ticker="BBAS3",
            quantity=100,
            average_price=26.50,
            total_cost=2650.00,
            stop_loss=24.00,
            take_profit=31.00,
            strategy="MANUAL",
            is_simulated=False,
        )
        real_tx = Transaction(
            date=datetime(2026, 10, 15, 10, 0),
            ticker="BBAS3",
            type="BUY",
            quantity=100,
            price=26.50,
            fees=1.50,
            total_value=2651.50,
            realized_pnl=0.0,
            strategy="MANUAL",
            is_simulated=False,
        )
        tax_rec = MonthlyTaxRecord(
            year_month="2026-10",
            total_sales=25000.00,
            net_profit=2000.00,
            is_exempt=False,
            taxable_profit=2000.00,
            tax_due=300.00,
            irrf_withheld=1.25,
            final_darf=298.75,
        )
        session.add_all([real_pos, real_tx, tax_rec])
        session.commit()

        # Executa --reset duas vezes para validar idempotência e isolamento absoluto
        seed_demo_portfolio(session, reset=True, use_live_prices=False)
        seed_demo_portfolio(session, reset=True, use_live_prices=False)

        assert session.query(Position).filter_by(is_simulated=False).count() == 1
        kept_pos = session.query(Position).filter_by(ticker="BBAS3", is_simulated=False).first()
        assert kept_pos is not None
        assert kept_pos.quantity == 100
        assert kept_pos.average_price == 26.50

        assert session.query(Transaction).filter_by(is_simulated=False).count() == 1
        assert session.query(MonthlyTaxRecord).count() == 1
        kept_tax = session.query(MonthlyTaxRecord).filter_by(year_month="2026-10").first()
        assert kept_tax.final_darf == 298.75

        assert session.query(Position).filter_by(is_simulated=True).count() == 5
        assert session.query(Transaction).filter_by(is_simulated=True).count() == 9
    finally:
        session.close()


def test_seed_demo_portfolio_skips_without_reset():
    """Garante que sem --reset o seed aborta com segurança caso já existam posições simuladas."""
    session = _create_memory_session()
    try:
        first = seed_demo_portfolio(session, reset=False, use_live_prices=False)
        assert first["skipped"] is False

        second = seed_demo_portfolio(session, reset=False, use_live_prices=False)
        assert second["skipped"] is True
        assert second["open_positions"] == 5
        assert session.query(Position).filter_by(is_simulated=True).count() == 5
        assert session.query(Transaction).filter_by(is_simulated=True).count() == 9
    finally:
        session.close()
