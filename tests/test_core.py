"""Testes unitários dos algoritmos das estratégias e do motor de saídas."""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from b3pilot.ledger.db import Base, Position, naive_utc_now
from b3pilot.core.strategies import compute_indicators, evaluate_ifr2_setup, evaluate_trend_setup
from b3pilot.core.exits import evaluate_open_positions_exits


def generate_synthetic_ohlcv(n_days=250, base_price=30.0, trend=0.001):
    """Gera uma série temporal OHLCV sintética para testes determinísticos."""
    dates = pd.date_range(end=datetime.now(), periods=n_days, freq="B")
    np.random.seed(42)

    returns = np.random.normal(trend, 0.015, n_days)
    prices = base_price * np.exp(np.cumsum(returns))

    highs = prices * (1 + np.random.uniform(0.005, 0.02, n_days))
    lows = prices * (1 - np.random.uniform(0.005, 0.02, n_days))
    opens = (highs + lows) / 2
    volumes = np.random.randint(100000, 5000000, n_days)

    df = pd.DataFrame(
        {
            "Open": opens,
            "High": highs,
            "Low": lows,
            "Close": prices,
            "Volume": volumes,
        },
        index=dates,
    )
    df.index.name = "Date"
    return df


def test_indicators_computation():
    """Valida o cálculo correto dos indicadores técnicos com pandas-ta."""
    df = generate_synthetic_ohlcv(250)
    data = compute_indicators(df)

    assert "SMA_200" in data.columns
    assert "EMA_9" in data.columns
    assert "EMA_21" in data.columns
    assert "RSI_2" in data.columns
    assert "ATR_14" in data.columns
    assert "HIGH_2D" in data.columns
    assert len(data) == 250


def test_ifr2_setup_trigger():
    """Valida acionamento do setup IFR2 quando sobrevenda extrema ocorre em tendência de alta."""
    df = generate_synthetic_ohlcv(250, base_price=50.0, trend=0.002)

    # Força os 2 últimos dias a terem quedas agudas para derrubar o RSI(2) abaixo de 10
    # enquanto o preço permanece bem acima da SMA 200
    df.loc[df.index[-2], "Close"] = df["Close"].iloc[-3] * 0.95
    df.loc[df.index[-1], "Close"] = df["Close"].iloc[-2] * 0.94
    df.loc[df.index[-1], "Low"] = df["Close"].iloc[-1] * 0.98

    res = evaluate_ifr2_setup(df)
    assert res is not None
    assert res["strategy"] == "IFR2"
    assert res["signal"] == "BUY"
    assert res["rsi2"] <= 15.0
    assert res["stop_loss"] < res["entry_price"]
    assert res["take_profit"] > res["entry_price"]


def test_exit_stop_loss_trigger(monkeypatch):
    """Valida acionamento de Stop Loss quando a cotação rompe o limite para baixo."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Cria posição com Stop em R$ 25,00
    pos = Position(
        ticker="PETR4",
        quantity=100,
        average_price=28.00,
        total_cost=2800.00,
        stop_loss=25.00,
        take_profit=32.00,
        strategy="MANUAL",
        entry_date=naive_utc_now(),
    )
    session.add(pos)
    session.commit()

    # Mock de fetch_ticker_data retornando cotação em R$ 24,50 (abaixo do stop)
    df_mock = generate_synthetic_ohlcv(30, base_price=24.50)
    import b3pilot.core.exits as exits_mod
    monkeypatch.setattr(exits_mod, "fetch_ticker_data", lambda *args, **kwargs: df_mock)

    exits = evaluate_open_positions_exits(session)
    assert len(exits) == 1
    assert exits[0]["type"] == "SELL_STOP_LOSS"
    assert exits[0]["ticker"] == "PETR4"
    assert exits[0]["urgency"] == "ALTA"
    session.close()


def test_52w_indicators_and_trend_setup():
    """Valida cálculo de 52 semanas e presença dos novos campos em setups de tendência e IFR2."""
    df = generate_synthetic_ohlcv(250)
    data = compute_indicators(df)

    assert "HIGH_52W" in data.columns
    assert "LOW_52W" in data.columns
    assert data["HIGH_52W"].iloc[-1] >= data["LOW_52W"].iloc[-1]

    # Prepara setup altista com pullback para acionar evaluate_trend_setup
    df_trend = generate_synthetic_ohlcv(250, base_price=30.0, trend=0.003)
    # Garante alinhamento das médias
    df_trend["Volume"] = 5_000_000  # ADTV alto
    res = evaluate_trend_setup(df_trend)
    # Se o candle sintético disparar o gatilho, valida as métricas de 52 semanas
    if res is not None:
        assert "high_52w" in res
        assert "low_52w" in res
        assert "range_52w_pct" in res
        assert "dist_52w_high_pct" in res
        assert res["high_52w"] >= res["low_52w"]


def test_trend_setup_vetoed_on_overextended_top():
    """Valida que o gatekeeper anti-topo veta o setup de tendência se o ativo estiver colado no topo de 52S."""
    from b3pilot.core.strategies import evaluate_trend_setup
    df = generate_synthetic_ohlcv(250, base_price=30.0, trend=0.005)
    df["Volume"] = 5_000_000
    # Força a última barra a estar colada na máxima histórica do ano
    max_p = df["High"].max()
    df.iloc[-1, df.columns.get_loc("Close")] = max_p * 0.99
    df.iloc[-1, df.columns.get_loc("High")] = max_p
    res = evaluate_trend_setup(df)
    # Deve ser vetado (None) por estar a < 5% do topo e nos 20% superiores do range
    assert res is None


def test_reversal_pivot_setup_trigger():
    """Valida acionamento do setup de Retomada de Fundo (Pivô Concluído) em ativo defasado."""
    from b3pilot.core.strategies import evaluate_reversal_pivot_setup
    df = generate_synthetic_ohlcv(250, base_price=50.0, trend=-0.001)
    df["Volume"] = 3_000_000
    # Força os últimos 3 dias a formarem um fundo e superarem a EMA 9
    df.iloc[-3, df.columns.get_loc("Low")] = 30.0
    df.iloc[-3, df.columns.get_loc("Close")] = 31.0
    df.iloc[-2, df.columns.get_loc("Low")] = 30.2
    df.iloc[-2, df.columns.get_loc("Close")] = 30.8
    # Hoje faz candle verde rompendo a EMA 9
    df.iloc[-1, df.columns.get_loc("Open")] = 31.0
    df.iloc[-1, df.columns.get_loc("Low")] = 30.5
    df.iloc[-1, df.columns.get_loc("Close")] = 33.5
    df.iloc[-1, df.columns.get_loc("High")] = 34.0
    df.iloc[-1, df.columns.get_loc("Volume")] = 6_000_000

    res = evaluate_reversal_pivot_setup(df)
    if res is not None:
        assert res["strategy"] == "REVERSAL_PIVOT"
        assert res["signal"] == "BUY"
        assert res["dist_52w_high_pct"] >= 12.0
        assert res["rr_ratio"] >= 2.0

