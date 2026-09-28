"""Testes unitários rigorosos do motor fiscal para Swing Trade na B3."""

import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from b3pilot.ledger.db import Base, Transaction, Position, MonthlyTaxRecord
from b3pilot.ledger.portfolio import execute_buy, execute_sell
from b3pilot.ledger.taxes import recalculate_monthly_taxes, get_current_tax_summary


@pytest.fixture
def test_db():
    """Cria um banco SQLite temporário em memória para testes."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_preco_medio_ponderado_com_taxas(test_db):
    """Valida o cálculo oficial do Preço Médio Ponderado incluindo custos de corretagem."""
    # 1ª Compra: 100 ações a R$ 20,00 + R$ 10,00 de taxas -> Custo = R$ 2010 -> PM = R$ 20,10
    pos1 = execute_buy(
        session=test_db,
        ticker="PETR4",
        quantity=100,
        price=20.00,
        fees=10.00,
    )
    assert pos1.quantity == 100
    assert pos1.average_price == 20.10
    assert pos1.total_cost == 2010.00

    # 2ª Compra: 100 ações a R$ 22,00 + R$ 10,00 de taxas -> Custo = R$ 2210 -> Novo PM = (2010 + 2210) / 200 = R$ 21,10
    pos2 = execute_buy(
        session=test_db,
        ticker="PETR4",
        quantity=100,
        price=22.00,
        fees=10.00,
    )
    assert pos2.quantity == 200
    assert pos2.average_price == 21.10
    assert pos2.total_cost == 4220.00


def test_isencao_vendas_abaixo_de_20k(test_db):
    """Valida que vendas até R$ 20.000 no mês são isentas de IR."""
    tx_date = datetime(2026, 8, 10)

    # Compra 500 ações a R$ 30,00 (Total R$ 15.000)
    execute_buy(test_db, "VALE3", 500, 30.00, fees=0.0, date=tx_date)

    # Vende 500 ações a R$ 35,00 (Total Venda = R$ 17.500 <= R$ 20.000)
    # Lucro bruto = R$ 2.500
    res = execute_sell(test_db, "VALE3", 500, 35.00, fees=0.0, date=tx_date)

    assert res["realized_pnl"] == 2500.00
    assert res["is_exempt_month"] is True

    record = recalculate_monthly_taxes(test_db, "2026-08")
    assert record.is_exempt is True
    assert record.net_profit == 2500.00
    assert record.tax_due == 0.0
    assert record.final_darf == 0.0


def test_tributacao_vendas_acima_de_20k(test_db):
    """Valida aplicação de 15% de IR sobre vendas que ultrapassam R$ 20.000."""
    tx_date = datetime(2026, 9, 15)

    # Compra 1.000 ações a R$ 25,00 (R$ 25.000)
    execute_buy(test_db, "WEGE3", 1000, 25.00, fees=0.0, date=tx_date)

    # Vende 1.000 ações a R$ 30,00 (Total Venda = R$ 30.000 > R$ 20.000)
    # Lucro líquido = R$ 5.000,00
    res = execute_sell(test_db, "WEGE3", 1000, 30.00, fees=0.0, date=tx_date)

    assert res["is_exempt_month"] is False
    assert res["realized_pnl"] == 5000.00

    record = recalculate_monthly_taxes(test_db, "2026-09")
    assert record.is_exempt is False
    assert record.taxable_profit == 5000.00
    # IR 15% = R$ 750,00
    assert record.tax_due == 750.00
    # IRRF dedo-duro = 30.000 * 0.00005 = R$ 1,50
    assert record.irrf_withheld == 1.50
    # DARF = 750.00 - 1.50 = R$ 748,50
    assert record.final_darf == 748.50


def test_compensacao_prejuizo_acumulado(test_db):
    """Valida compensação automática de prejuízos de meses anteriores."""
    # Mês 1 (Julho/2026): Operação com PREJUÍZO de R$ 3.000,00
    date_jul = datetime(2026, 7, 5)
    execute_buy(test_db, "CSNA3", 1000, 15.00, date=date_jul)
    execute_sell(test_db, "CSNA3", 1000, 12.00, date=date_jul)  # Perda de R$ 3.000

    rec_jul = recalculate_monthly_taxes(test_db, "2026-07")
    assert rec_jul.accumulated_loss == 3000.00

    # Mês 2 (Agosto/2026): Operação com LUCRO TRIBUTÁVEL de R$ 5.000,00 (Venda R$ 25k)
    date_aug = datetime(2026, 8, 10)
    execute_buy(test_db, "PRIO3", 1000, 20.00, date=date_aug)
    execute_sell(test_db, "PRIO3", 1000, 25.00, date=date_aug)  # Lucro de R$ 5.000, Venda R$ 25.000

    rec_aug = recalculate_monthly_taxes(test_db, "2026-08")
    assert rec_aug.prior_losses_used == 3000.00
    # Base tributável deve ser R$ 5.000 - R$ 3.000 = R$ 2.000
    assert rec_aug.taxable_profit == 2000.00
    assert rec_aug.accumulated_loss == 0.0
    # 15% de R$ 2.000 = R$ 300,00
    assert rec_aug.tax_due == 300.00
