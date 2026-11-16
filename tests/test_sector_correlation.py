"""Testes automatizados para Mapeamento Setorial, Macro-Clusters e Gestão de Correlação Cruzada."""

import pytest
from b3pilot.data.sectors import (
    get_asset_sector_profile,
    are_clusters_correlated,
    CLUSTER_AGRO,
    CLUSTER_BANKS,
    CLUSTER_OIL_GAS,
    CLUSTER_CAPITAL_GOODS,
    CLUSTER_REAL_ESTATE,
    CLUSTER_RETAIL,
)
from b3pilot.core.risk import (
    check_sector_and_cluster_conflict,
    analyze_portfolio_sector_distribution,
    filter_diversified_signals,
)
from b3pilot.ledger.db import init_db, get_db_session, Position, naive_utc_now
from b3pilot.core.chat import analyze_ticker_for_decision


def test_asset_sector_mapping():
    """Valida se o perfil setorial dos ativos essenciais está correto."""
    soja_prof = get_asset_sector_profile("SOJA3")
    assert soja_prof["sector"] == "Agronegócio"
    assert CLUSTER_AGRO in soja_prof["clusters"]

    smto_prof = get_asset_sector_profile("SMTO3F")  # Teste com sufixo fracionário
    assert smto_prof["sector"] == "Agronegócio"
    assert CLUSTER_AGRO in smto_prof["clusters"]

    # Caso Crítico: BBAS3 deve conter CLUSTER_BANKS e CLUSTER_AGRO (crédito rural)
    bbas_prof = get_asset_sector_profile("BBAS3.SA")
    assert bbas_prof["sector"] == "Financeiro"
    assert CLUSTER_BANKS in bbas_prof["clusters"]
    assert CLUSTER_AGRO in bbas_prof["clusters"]
    assert "crédito" in bbas_prof["macro_risk_note"].lower()
    assert "rural" in bbas_prof["macro_risk_note"].lower()


def test_cross_cluster_correlation():
    """Valida correlações cruzadas entre clusters que sobem/caem juntos."""
    assert are_clusters_correlated(CLUSTER_AGRO, CLUSTER_AGRO) is True
    # Real estate e varejo compartilham forte sensibilidade à Selic/juros
    assert are_clusters_correlated(CLUSTER_REAL_ESTATE, CLUSTER_RETAIL) is True
    assert are_clusters_correlated(CLUSTER_RETAIL, CLUSTER_REAL_ESTATE) is True
    # Petróleo e Agronegócio não são correlacionados diretamente
    assert are_clusters_correlated(CLUSTER_OIL_GAS, CLUSTER_AGRO) is False


def test_check_sector_conflict_detection():
    """Testa a detecção de conflitos entre um ativo candidato e a carteira atual."""
    # Cenário 1: Carteira já possui BBAS3 e SOJA3
    current_portfolio = ["BBAS3F", "SOJA3F"]

    # Tentativa de comprar SMTO3 (deve disparar conflito severo de agronegócio)
    conflict_smto = check_sector_and_cluster_conflict("SMTO3", current_portfolio)
    assert conflict_smto["has_conflict"] is True
    assert conflict_smto["risk_level"] == "HIGH"
    assert "SOJA3F" in conflict_smto["conflicting_tickers"]
    assert "BBAS3F" in conflict_smto["conflicting_tickers"]
    assert CLUSTER_AGRO in conflict_smto["shared_clusters"]

    # Tentativa de comprar WEGE3 (Bens Industriais - Descorrelacionado)
    conflict_wege = check_sector_and_cluster_conflict("WEGE3", current_portfolio)
    assert conflict_wege["has_conflict"] is False
    assert conflict_wege["risk_level"] == "LOW"


def test_portfolio_sector_distribution_and_score():
    """Testa a radiografia setorial da carteira e a penalidade por concentração."""
    # Simula a carteira com a falha operacional relatada pelo usuário:
    # BBAS3 + 2 do agronegócio (SOJA3 e SMTO3)
    concentrated_positions = [
        {"ticker": "SOJA3F", "total_cost": 200.0, "quantity": 25, "average_price": 8.0},
        {"ticker": "BBAS3F", "total_cost": 1000.0, "quantity": 40, "average_price": 25.0},
        {"ticker": "SMTO3F", "total_cost": 300.0, "quantity": 15, "average_price": 20.0},
    ]

    audit = analyze_portfolio_sector_distribution(concentrated_positions, total_capital=1500.0)

    # Deve identificar sobreposição no cluster AGRONEGOCIO (3 ativos)
    assert CLUSTER_AGRO in audit["cluster_breakdown"]
    assert len(audit["cluster_breakdown"][CLUSTER_AGRO]["tickers"]) == 3
    assert len(audit["concentration_warnings"]) > 0
    # O score de diversificação deve ser penalizado por essa concentração
    assert audit["diversification_score"] < 80.0


def test_filter_diversified_signals_prevents_cluster_stacking():
    """Testa se o filtro de sinais impede a sugestão de ativos do mesmo setor ou cluster."""
    raw_signals = [
        {"ticker": "PETR4", "score": 9.2, "name": "IFR2 Petrobras", "entry_price": 38.0, "stop_loss": 36.0, "take_profit": 42.0},
        {"ticker": "PRIO3", "score": 8.9, "name": "Trend PRIO", "entry_price": 45.0, "stop_loss": 43.0, "take_profit": 50.0},  # Mesmo cluster de petróleo!
        {"ticker": "SLCE3", "score": 8.7, "name": "IFR2 SLC Agrícola", "entry_price": 18.0, "stop_loss": 17.0, "take_profit": 20.0},  # Agro!
        {"ticker": "WEGE3", "score": 8.5, "name": "Trend WEG", "entry_price": 52.0, "stop_loss": 50.0, "take_profit": 57.0},  # Bens Industriais
        {"ticker": "CPLE3", "score": 8.2, "name": "Reversal Copel", "entry_price": 10.0, "stop_loss": 9.5, "take_profit": 11.2},  # Utilidade Pública
    ]

    # Cenário: Usuário já possui BBAS3 em carteira (portanto já tem exposição a risco rural)
    user_portfolio = ["BBAS3F"]

    diversified = filter_diversified_signals(
        raw_signals,
        current_portfolio_tickers=user_portfolio,
        max_signals=3,
        allow_same_cluster=False,
    )

    selected_tickers = [d["ticker"] for d in diversified]

    # 1. SLCE3 deve ter sido excluído ou despriorizado porque colide com o risco rural de BBAS3
    assert "SLCE3" not in selected_tickers

    # 2. Entre PETR4 e PRIO3 (ambas de petróleo), apenas PETR4 (maior score) deve ter sido selecionada
    assert "PETR4" in selected_tickers
    assert "PRIO3" not in selected_tickers

    # 3. As outras vagas devem ter ido para setores independentes (WEGE3 e CPLE3)
    assert "WEGE3" in selected_tickers
    assert "CPLE3" in selected_tickers
    assert len(selected_tickers) == 3
