"""Testes unitários de Engenharia de Risco, Position Sizing, Auditoria de Opções e Regime Macro."""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime

from b3pilot.core.risk import calculate_position_size, audit_option_spread
from b3pilot.core.regime import analyze_market_regime
from b3pilot.data.b3_feed import compute_adtv_21


def test_position_sizing_respects_max_risk():
    """Valida que o cálculo de dimensionamento não ultrapassa o risco estipulado de 2%."""
    capital = 10000.00
    entry_price = 20.00
    stop_loss = 18.00  # Risco de R$ 2,00 por ação
    # Risco máx monetário: 10.000 * 0.02 = R$ 200,00
    # Qtd base pelo risco = 200 / 2 = 100 ações
    # Teto de alocação 25%: R$ 2.500 / 20 = 125 ações
    # min(100, 125) = 100 ações

    res = calculate_position_size(
        entry_price=entry_price,
        stop_loss=stop_loss,
        capital=capital,
        risk_pct=0.02,
        max_allocation_pct=0.25,
    )

    assert res["shares"] == 100
    assert res["total_value"] == 2000.00
    assert res["total_risk_money"] == 200.00
    assert res["actual_risk_pct"] == 2.0


def test_position_sizing_respects_allocation_ceiling():
    """Valida que o tamanho do lote é podado se violar o teto de 25% de capital por ativo."""
    capital = 10000.00
    entry_price = 50.00
    stop_loss = 49.50  # Risco minúsculo de R$ 0,50 por ação
    # Pelo risco: 200 / 0.50 = 400 ações (R$ 20.000 -> 200% do capital!)
    # Pelo teto de 25%: máx R$ 2.500 -> 2.500 / 50 = 50 ações

    res = calculate_position_size(
        entry_price=entry_price,
        stop_loss=stop_loss,
        capital=capital,
        risk_pct=0.02,
        max_allocation_pct=0.25,
        round_lot=False,
    )

    assert res["total_value"] <= 2500.00
    assert res["shares"] <= 50


def test_audit_option_spread_detects_retail_trap():
    """Valida a detecção de armadilha matemática em travas de baixa com payoff desfavorável."""
    # Exemplo típico de banco em MCDC34:
    # Compra Put 54, Vende Put 50 por R$ 2.80 de prêmio (Largura = 4.00)
    # Ganho máx = 4.00 - 2.80 = R$ 1.20
    # Perda máx = R$ 2.80
    # R/R = 1.20 / 2.80 = 0.43x -> Perde mais que ganha!
    res = audit_option_spread(
        underlying="MCDC34",
        spread_type="BEAR_PUT",
        strike_long=54.00,
        strike_short=50.00,
        net_premium=2.80,
        contracts_qty=100,
    )

    assert res["is_retail_trap"] is True
    assert res["risk_reward_ratio"] < 0.8
    assert res["max_loss_total"] == 280.00
    assert res["max_profit_total"] == 120.00
    assert res["required_win_rate_pct"] > 65.0
    assert "🚨 ASSIMETRIA CRÍTICA DESFAVORÁVEL" in res["verdict_tags"]


def test_audit_option_spread_favorable():
    """Valida que uma trava de baixa com assimetria favorável é aprovada."""
    # Compra Put 60, Vende Put 50 por R$ 2.00 de prêmio (Largura = 10.00)
    # Ganho máx = 8.00, Perda máx = 2.00 -> R/R de 4.0x
    res = audit_option_spread(
        underlying="PETR4",
        spread_type="BEAR_PUT",
        strike_long=60.00,
        strike_short=50.00,
        net_premium=2.00,
        contracts_qty=100,
    )

    assert res["is_retail_trap"] is False
    assert res["risk_reward_ratio"] == 4.0
    assert "✓ ASSIMETRIA FAVORÁVEL" in res["verdict_tags"]


def test_market_regime_classification_synthetic():
    """Valida a classificação dos regimes Macro (Bull, Bear e Panic)."""
    # 1. Cria série simulada de alta sustentada
    dates = pd.date_range(end=datetime.now(), periods=250, freq="B")
    prices_bull = [100000 + (i * 200) for i in range(250)]
    df_bull = pd.DataFrame(
        {"Close": prices_bull, "High": prices_bull, "Low": prices_bull, "Volume": [1000] * 250},
        index=dates,
    )

    reg_bull = analyze_market_regime(df_bull)
    assert reg_bull["status"] == "BULL"
    assert reg_bull["allow_momentum"] is True
    assert reg_bull["allocation_multiplier"] == 1.0

    # 2. Série simulada em pânico (-3% no último dia)
    df_panic = df_bull.copy()
    df_panic.loc[df_panic.index[-1], "Close"] = df_panic["Close"].iloc[-2] * 0.965  # Queda de 3.5%
    reg_panic = analyze_market_regime(df_panic)
    assert reg_panic["status"] == "PANIC"
    assert reg_panic["allow_momentum"] is False
    assert reg_panic["allow_ifr2"] is False
    assert reg_panic["allocation_multiplier"] == 0.0

    # 3. Série simulada em Bear Market (cotação abaixo da SMA 200)
    prices_bear = [150000 - (i * 250) for i in range(250)]
    df_bear = pd.DataFrame(
        {"Close": prices_bear, "High": prices_bear, "Low": prices_bear, "Volume": [1000] * 250},
        index=dates,
    )
    reg_bear = analyze_market_regime(df_bear)
    assert reg_bear["status"] == "BEAR"
    assert reg_bear["allow_momentum"] is False
    assert reg_bear["allocation_multiplier"] == 0.50


def test_compute_adtv_21():
    """Valida o cálculo do Volume Financeiro Médio Diário em Reais."""
    df = pd.DataFrame({
        "Close": [10.0] * 25,
        "Volume": [100000] * 25,
    })
    # 10.0 * 100.000 = 1.000.000,00 por dia
    adtv = compute_adtv_21(df)
    assert adtv == 1000000.0
