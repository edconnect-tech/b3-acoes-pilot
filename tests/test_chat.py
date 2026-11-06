"""Testes unitários do motor do Chat Operacional."""

import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from b3pilot.ledger.db import Base, Position
from b3pilot.core.chat import extract_tickers_from_text, process_chat_query
from tests.test_core import generate_synthetic_ohlcv


def test_extract_tickers_from_text():
    """Valida a extração correta de tickers B3 em mensagens de texto."""
    text1 = "Posso comprar petr4 ou vale3 agora?"
    assert extract_tickers_from_text(text1) == ["PETR4", "VALE3"]

    text2 = "Como está a situação de ITUB4? E bbdc4?"
    assert extract_tickers_from_text(text2) == ["ITUB4", "BBDC4"]

    text3 = "Não tem nenhum ticker aqui, apenas uma pergunta genérica."
    assert extract_tickers_from_text(text3) == []

    text4 = "PETR4 petr4 PETR4 repetido"
    assert extract_tickers_from_text(text4) == ["PETR4"]


def test_chat_query_market_regime():
    """Valida resposta quando o usuário pergunta sobre o Ibovespa ou mercado."""
    engine = create_engine("sqlite:///:memory:")
    Session = sessionmaker(bind=engine)
    session = Session()

    response = process_chat_query("Como está o ibovespa hoje?", session)
    assert "Diagnóstico do Mercado (IBOVESPA)" in response
    assert "Status:" in response
    session.close()


def test_chat_query_exits_without_positions():
    """Valida resposta quando o usuário pergunta se deve vender e não há saídas disparadas."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    response = process_chat_query("Devo vender alguma posição da minha carteira?", session)
    assert "Auditoria de Saídas" in response
    assert "Nenhuma posição atingiu Stop Loss" in response
    session.close()


def test_chat_query_with_stop_loss_hit(monkeypatch):
    """Valida alerta vermelho de venda imediata quando a ação rompeu o stop cadastrado."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    pos = Position(
        ticker="PETR4",
        quantity=100,
        average_price=38.00,
        total_cost=3800.00,
        stop_loss=35.00,
        take_profit=44.00,
        strategy="TREND",
        is_simulated=False,
    )
    session.add(pos)
    session.commit()

    # Mock de fetch_ticker_data com fechamento final em 33.50 (abaixo do stop de 35.00)
    df_mock = generate_synthetic_ohlcv(250, base_price=34.00)
    df_mock.loc[df_mock.index[-1], "Close"] = 33.50
    import b3pilot.core.chat as chat_mod
    monkeypatch.setattr(chat_mod, "fetch_ticker_data", lambda *args, **kwargs: df_mock)

    response = process_chat_query("Posso vender PETR4?", session, is_simulated=False)
    assert "VENDA OBRIGATÓRIA (STOP LOSS ATINGIDO)" in response
    assert "R$ 35.00" in response
    session.close()


def test_chat_query_generic_help():
    """Valida mensagem de instrução/ajuda quando a pergunta é neutra."""
    engine = create_engine("sqlite:///:memory:")
    Session = sessionmaker(bind=engine)
    session = Session()

    response = process_chat_query("olá, boa tarde", session)
    assert "Assistente Operacional da B3" in response
    session.close()


def test_chat_query_simulate_partial():
    """Valida a simulação de realização parcial com garantia de lucro no chat."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    pos = Position(
        ticker="SOJA3",
        quantity=62,
        average_price=8.00,
        total_cost=496.00,
        stop_loss=7.50,
        take_profit=9.50,
        is_simulated=False,
    )
    session.add(pos)
    session.commit()

    query = "Simular parcial de SOJA3 a 8.60 com novo stop a 8.25"
    response = process_chat_query(query, session, is_simulated=False)

    assert "Simulação de Realização Parcial — **SOJA3**" in response
    assert "31 ações" in response
    assert "R$ 8.60" in response
    assert "R$ 8.25" in response
    assert "R$ +26.35" in response
    assert "Passo a Passo para Executar no seu Home Broker" in response
    session.close()
