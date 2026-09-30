"""Testes unitários de isolamento fiscal e operacional do Modo Simulação (Paper Trading)."""

import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from b3pilot.ledger.db import Base, Transaction, Position, MonthlyTaxRecord
from b3pilot.ledger.portfolio import execute_buy, execute_sell, get_portfolio_summary
from b3pilot.ledger.taxes import recalculate_monthly_taxes
from b3pilot.core.exits import evaluate_open_positions_exits


@pytest.fixture
def test_db():
    """Cria um banco SQLite temporário em memória para testes."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_coexistencia_mesmo_ticker_real_e_simulado(test_db):
    """Valida que o usuário pode possuir custódia Real e Simulada no mesmo ticker simultaneamente."""
    # Compra Real: 100 PETR4 a R$ 30,00
    pos_real = execute_buy(
        session=test_db,
        ticker="PETR4",
        quantity=100,
        price=30.00,
        fees=10.00,
        is_simulated=False,
    )
    assert pos_real.is_simulated is False
    assert pos_real.quantity == 100
    assert pos_real.average_price == 30.10

    # Compra Simulada: 300 PETR4 a R$ 25,00
    pos_sim = execute_buy(
        session=test_db,
        ticker="PETR4",
        quantity=300,
        price=25.00,
        fees=0.00,
        is_simulated=True,
    )
    assert pos_sim.is_simulated is True
    assert pos_sim.quantity == 300
    assert pos_sim.average_price == 25.00

    # Validar que a posição real permanece inalterada
    test_db.refresh(pos_real)
    assert pos_real.quantity == 100
    assert pos_real.average_price == 30.10

    # Validar resumos separados de carteira
    summary_real = get_portfolio_summary(test_db, is_simulated=False)
    summary_sim = get_portfolio_summary(test_db, is_simulated=True)

    assert len(summary_real["positions"]) == 1
    assert summary_real["positions"][0]["quantity"] == 100
    assert summary_real["total_invested"] == 3010.00

    assert len(summary_sim["positions"]) == 1
    assert summary_sim["positions"][0]["quantity"] == 300
    assert summary_sim["total_invested"] == 7500.00


def test_isolamento_fiscal_venda_simulada_nao_gera_darf(test_db):
    """Valida com rigor que vendas simuladas jamais geram fatos geradores fiscais ou DARF."""
    tx_date = datetime(2026, 9, 15)

    # 1. Compra Simulada de 1.000 ações a R$ 50,00 (R$ 50.000)
    execute_buy(test_db, "VALE3", 1000, 50.00, fees=0.0, date=tx_date, is_simulated=True)

    # 2. Venda Simulada com lucro massivo: Venda a R$ 80,00 (Total R$ 80.000 > R$ 20k, Lucro R$ 30.000)
    res_sell_sim = execute_sell(
        test_db, "VALE3", 1000, 80.00, fees=0.0, date=tx_date, is_simulated=True
    )
    assert res_sell_sim["realized_pnl"] == 30000.00

    # 3. Verificar que nenhum registro fiscal de imposto foi gravado
    tax_records = test_db.query(MonthlyTaxRecord).all()
    assert len(tax_records) == 0

    # Mesmo forçando recálculo do mês, vendas simuladas devem ser completamente ignoradas
    recalc = recalculate_monthly_taxes(test_db, "2026-09")
    assert recalc.total_sales == 0.0
    assert recalc.taxable_profit == 0.0
    assert recalc.tax_due == 0.0
    assert recalc.final_darf == 0.0


def test_venda_real_vs_simulada_coexistentes_calculo_ir(test_db):
    """Garante que operações simuladas não contaminam o limite de R$ 20k de vendas reais."""
    tx_date = datetime(2026, 9, 20)

    # Real: Compra 500 ITUB4 a R$ 30 (R$ 15.000)
    execute_buy(test_db, "ITUB4", 500, 30.00, fees=0.0, date=tx_date, is_simulated=False)
    # Simulado: Compra 1.000 ITUB4 a R$ 30 (R$ 30.000)
    execute_buy(test_db, "ITUB4", 1000, 30.00, fees=0.0, date=tx_date, is_simulated=True)

    # Venda Real: R$ 15.000 (Dentro do limite de isenção de R$ 20k) -> 500 ações a R$ 30 -> Lucro 0
    execute_sell(test_db, "ITUB4", 500, 30.00, fees=0.0, date=tx_date, is_simulated=False)

    # Venda Simulada: R$ 40.000 (Se fosse somada com a real, passaria de R$ 20k)
    execute_sell(test_db, "ITUB4", 1000, 40.00, fees=0.0, date=tx_date, is_simulated=True)

    # Recalcula e valida tributação oficial
    recalc = recalculate_monthly_taxes(test_db, "2026-09")

    # Vendas reais registradas devem ser exatamente R$ 15.000 (e não R$ 55.000)
    assert recalc.total_sales == 15000.00
    assert recalc.is_exempt is True
    assert recalc.tax_due == 0.0
    assert recalc.final_darf == 0.0


def test_exits_evaluation_com_flag_simulada(test_db):
    """Testa que a avaliação de saídas respeita o filtro de posições reais e simuladas."""
    # Cria posição real em PETR4 e simulada em VALE3
    execute_buy(test_db, "PETR4", 100, 30.00, fees=0.0, is_simulated=False)
    execute_buy(test_db, "VALE3", 200, 60.00, fees=0.0, is_simulated=True)

    alerts_real = evaluate_open_positions_exits(test_db, is_simulated=False)
    alerts_sim = evaluate_open_positions_exits(test_db, is_simulated=True)

    assert isinstance(alerts_real, list)
    assert isinstance(alerts_sim, list)
