"""Módulo de Engenharia de Risco, Dimensionamento de Posição e Auditoria de Derivativos.

Implementa:
1. Position Sizing Institucional por Paridade de Risco (Risco fixo de 2% do NAV).
2. Auditor de Assimetria de Operações Estruturadas (Travas de Baixa/Alta de Bancos).
"""

from typing import Dict, Any, Optional
import math

from b3pilot.config import (
    DEFAULT_CAPITAL,
    RISK_MAX_PER_TRADE_PERCENT,
    MAX_POSITION_ALLOCATION_PERCENT,
)


def calculate_position_size(
    entry_price: float,
    stop_loss: float,
    capital: float = DEFAULT_CAPITAL,
    risk_pct: float = RISK_MAX_PER_TRADE_PERCENT,
    max_allocation_pct: float = MAX_POSITION_ALLOCATION_PERCENT,
    allocation_multiplier: float = 1.0,
    round_lot: bool = True,
) -> Dict[str, Any]:
    """Calcula a quantidade ideal de ações a comprar com base no risco monetário máximo.
    
    Fórmula:
      Risco em R$ = Capital * risk_pct * allocation_multiplier
      Risco por Ação = entry_price - stop_loss
      Qtd Base = Risco em R$ / Risco por Ação
      Teto por Alocação = (Capital * max_allocation_pct) / entry_price
      Qtd Final = min(Qtd Base, Teto por Alocação)
    """
    if entry_price <= 0:
        return {"shares": 0, "total_value": 0.0, "risk_value": 0.0, "risk_pct": 0.0}

    # Se stop_loss for igual ou superior ao preço de entrada (anomalia), adota stop padrão de 5%
    if stop_loss >= entry_price or stop_loss <= 0:
        stop_loss = round(entry_price * 0.95, 2)

    risk_per_share = entry_price - stop_loss
    max_risk_money = capital * risk_pct * max_allocation_pct_multiplier(allocation_multiplier)

    # Quantidade de ações para atingir exatamente o risco máximo em R$
    raw_shares_by_risk = max_risk_money / risk_per_share

    # Teto prudencial por ativo (evita colocar mais de 25% da carteira em um papel só)
    max_money_allocation = capital * max_allocation_pct
    max_shares_by_capital = max_money_allocation / entry_price

    calculated_shares = min(raw_shares_by_risk, max_shares_by_capital)

    # Arredondamento para Lote Padrão da B3 (múltiplos de 100) se o capital permitir
    if round_lot and calculated_shares >= 100:
        final_shares = int(math.floor(calculated_shares / 100.0) * 100)
    else:
        # Lote fracionário (mínimo 1 ação)
        final_shares = max(1, int(math.floor(calculated_shares)))

    total_value = round(final_shares * entry_price, 2)
    total_risk_money = round(final_shares * risk_per_share, 2)
    actual_risk_pct = round((total_risk_money / capital) * 100, 2) if capital > 0 else 0.0
    allocation_pct = round((total_value / capital) * 100, 2) if capital > 0 else 0.0

    return {
        "shares": final_shares,
        "entry_price": round(entry_price, 2),
        "stop_loss": round(stop_loss, 2),
        "risk_per_share": round(risk_per_share, 2),
        "total_value": total_value,
        "total_risk_money": total_risk_money,
        "actual_risk_pct": actual_risk_pct,
        "allocation_pct": allocation_pct,
        "capital_base": capital,
    }


def max_allocation_pct_multiplier(mult: float) -> float:
    return max(0.1, min(1.0, mult))


def audit_option_spread(
    underlying: str,
    spread_type: str,  # 'BEAR_PUT' (Trava de Baixa c/ Put) ou 'BEAR_CALL' (Trava de Baixa c/ Call)
    strike_long: float,
    strike_short: float,
    net_premium: float,
    contracts_qty: int = 100,
    current_stock_price: Optional[float] = None,
) -> Dict[str, Any]:
    """Audita a assimetria quantitativa de uma Trava de Baixa (Bear Spread) sugerida por banco/corretora.
    
    Retorna métricas de Payoff, relação Ganho/Perda, Taxa de Acerto Mínima (Win Rate Necessário)
    e alerta de assimetria desfavorável de varejo.
    """
    underlying = underlying.upper().strip()
    spread_type = spread_type.upper().strip()

    if spread_type in ["BEAR_PUT", "TRAVA_DE_BAIXA_PUT"]:
        # Compra Put Strike Alto (K_high), Vende Put Strike Baixo (K_low)
        k_high = max(strike_long, strike_short)
        k_low = min(strike_long, strike_short)
        spread_width = k_high - k_low

        max_loss_per_share = net_premium
        max_profit_per_share = spread_width - net_premium
        break_even = k_high - net_premium
        strategy_desc = f"Trava de Baixa com PUT em {underlying}: Compra Put {k_high:.2f} e Vende Put {k_low:.2f}"

    else:
        # BEAR_CALL (Trava de Baixa com Call - Crédito)
        # Vende Call Strike Baixo (K_low), Compra Call Strike Alto (K_high)
        k_high = max(strike_long, strike_short)
        k_low = min(strike_long, strike_short)
        spread_width = k_high - k_low

        max_profit_per_share = net_premium
        max_loss_per_share = spread_width - net_premium
        break_even = k_low + net_premium
        strategy_desc = f"Trava de Baixa com CALL em {underlying}: Vende Call {k_low:.2f} e Compra Call {k_high:.2f}"

    max_loss_total = round(max_loss_per_share * contracts_qty, 2)
    max_profit_total = round(max_profit_per_share * contracts_qty, 2)

    # Relação Risco x Retorno (Payoff Ratio: Ganho Máximo / Perda Máxima)
    risk_reward_ratio = (
        round(max_profit_per_share / max_loss_per_share, 2)
        if max_loss_per_share > 0
        else 0.0
    )

    # Taxa mínima de acerto necessária para a estratégia não sangrar capital no longo prazo
    # WinRate_min = Perda / (Ganho + Perda)
    total_swing = max_profit_per_share + max_loss_per_share
    required_win_rate = (
        round((max_loss_per_share / total_swing) * 100, 1)
        if total_swing > 0
        else 100.0
    )

    # Diagnóstico Institucional
    is_retail_trap = False
    verdict_tags = []
    recommendation = ""

    if risk_reward_ratio < 0.8:
        is_retail_trap = True
        verdict_tags.append("🚨 ASSIMETRIA CRÍTICA DESFAVORÁVEL")
        recommendation = (
            f"REJEITAR OPERAÇÃO: Você está arriscando perder R$ {max_loss_total:,.2f} para tentar ganhar apenas "
            f"R$ {max_profit_total:,.2f} (R/R de {risk_reward_ratio:.2f}x). É matematicamente insustentável para varejo."
        )
    elif risk_reward_ratio < 1.2:
        is_retail_trap = True
        verdict_tags.append("⚠️ RISCO ELEVADO / GANHO ESTREITO")
        recommendation = (
            f"ALERTA DE CAUTELA: O ganho potencial mal compensa a perda total. Você precisa de {required_win_rate:.0f}% "
            f"de taxa de acerto contínua apenas para empatar no longo prazo."
        )
    else:
        verdict_tags.append("✓ ASSIMETRIA FAVORÁVEL")
        recommendation = (
            f"ESTRUTURA ACEITÁVEL: Potencial de retorno compensa o risco assumido (R/R de {risk_reward_ratio:.2f}x)."
        )

    tax_warning = (
        "⚖️ REGRA FISCAL RFB: Ganhos com opções NÃO possuem a isenção de R$ 20.000 de ações. "
        "Incide 15% de IR sobre o lucro líquido via DARF (Cód 6015)."
    )

    return {
        "underlying": underlying,
        "strategy_desc": strategy_desc,
        "spread_type": spread_type,
        "contracts_qty": contracts_qty,
        "max_profit_total": max_profit_total,
        "max_loss_total": max_loss_total,
        "break_even": round(break_even, 2),
        "risk_reward_ratio": risk_reward_ratio,
        "required_win_rate_pct": required_win_rate,
        "is_retail_trap": is_retail_trap,
        "verdict_tags": verdict_tags,
        "recommendation": recommendation,
        "tax_warning": tax_warning,
    }
