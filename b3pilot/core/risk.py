"""Módulo de Engenharia de Risco, Dimensionamento de Posição e Auditoria de Derivativos.

Implementa:
1. Position Sizing Institucional por Paridade de Risco (Risco fixo de 2% do NAV).
2. Auditor de Assimetria de Operações Estruturadas (Travas de Baixa/Alta de Bancos).
"""

from typing import Dict, Any, Optional, List, Set
import math

from b3pilot.config import (
    DEFAULT_CAPITAL,
    RISK_MAX_PER_TRADE_PERCENT,
    MAX_POSITION_ALLOCATION_PERCENT,
    MAX_SECTOR_ALLOCATION_PERCENT,
    MAX_CLUSTER_ACTIVE_TRADES,
)
from b3pilot.data.sectors import (
    get_asset_sector_profile,
    are_clusters_correlated,
    clean_ticker_key,
    CLUSTER_AGRO,
    CLUSTER_BANKS,
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


def check_sector_and_cluster_conflict(
    candidate_ticker: str,
    current_tickers: List[str],
) -> Dict[str, Any]:
    """Audita se um ativo candidato a compra colide com setores ou macro-clusters de posições já em carteira.
    
    Identifica:
      1. Mesmo setor econômico (ex: duas empresas de Agronegócio).
      2. Mesmo macro-cluster de risco (ex: BBAS3 e SOJA3/SMTO3, ambos expostos a risco rural).
      3. Setores intercorrelacionados (ex: Construção Civil e Varejo sensíveis à curva de juros).
    """
    cand_key = clean_ticker_key(candidate_ticker)
    cand_profile = get_asset_sector_profile(cand_key)
    cand_sector = cand_profile.get("sector", "Outros")
    cand_clusters = set(cand_profile.get("clusters", []))

    conflicting_tickers: List[str] = []
    shared_sectors: Set[str] = set()
    shared_clusters: Set[str] = set()
    warning_details: List[str] = []

    for active_t in current_tickers:
        active_key = clean_ticker_key(active_t)
        if active_key == cand_key:
            # Já possui exatamente o mesmo ativo
            conflicting_tickers.append(active_t)
            warning_details.append(f"Você já possui {active_t} em custódia.")
            continue

        active_profile = get_asset_sector_profile(active_key)
        active_sector = active_profile.get("sector", "Outros")
        active_clusters = set(active_profile.get("clusters", []))

        # 1. Checagem de Mesmo Setor
        is_same_sector = (cand_sector == active_sector and cand_sector != "Outros")
        if is_same_sector:
            shared_sectors.add(cand_sector)
            conflicting_tickers.append(active_t)
            warning_details.append(
                f"{active_t} pertence ao mesmo setor ({cand_sector})."
            )

        # 2. Checagem de Mesmo Macro-Cluster Compartilhado
        common_clusters = cand_clusters.intersection(active_clusters)
        if common_clusters:
            shared_clusters.update(common_clusters)
            if active_t not in conflicting_tickers:
                conflicting_tickers.append(active_t)

            # Caso crítico institucional: BBAS3 + Agronegócio
            if CLUSTER_AGRO in common_clusters:
                warning_details.append(
                    f"⚠️ Correlação Rural Crítica: {cand_key} e {active_t} compartilham exposição ao risco do agronegócio/crédito rural. Quedas em safras ou inadimplência rural derrubam ambos."
                )
            else:
                cluster_names = ", ".join(common_clusters)
                warning_details.append(
                    f"{active_t} compartilha o mesmo fator de risco macro ({cluster_names})."
                )

        # 3. Checagem de Clusters Intercorrelacionados que sobem/caem juntos
        for cc in cand_clusters:
            for ac in active_clusters:
                if cc != ac and are_clusters_correlated(cc, ac):
                    if active_t not in conflicting_tickers:
                        conflicting_tickers.append(active_t)
                    warning_details.append(
                        f"Setores correlacionados: {cand_key} ({cc}) e {active_t} ({ac}) respondem ao mesmo ciclo macroeconômico."
                    )

    has_conflict = len(conflicting_tickers) > 0
    if not has_conflict:
        return {
            "has_conflict": False,
            "conflict_type": "NONE",
            "risk_level": "LOW",
            "candidate_ticker": cand_key,
            "candidate_sector": cand_sector,
            "candidate_clusters": list(cand_clusters),
            "conflicting_tickers": [],
            "shared_sectors": [],
            "shared_clusters": [],
            "warning_message": "Ativo descorrelacionado das posições atuais. Excelente para diversificação.",
            "recommendation": "COMPRA DIVERSIFICADA: Reduz a volatilidade global da carteira.",
        }

    # Determina severidade do risco
    is_high_risk = (
        len(conflicting_tickers) >= 2
        or CLUSTER_AGRO in shared_clusters
        or len(shared_sectors) > 0
    )
    risk_level = "HIGH" if is_high_risk else "MEDIUM"

    warning_summary = " | ".join(dict.fromkeys(warning_details))
    recommendation = (
        f"ALERTA DE CONCENTRAÇÃO: Evite apostar novamente no mesmo fator de risco. "
        f"Você já tem exposição através de {', '.join(conflicting_tickers)}. "
        f"Prefira ativos de setores descorrelacionados."
    )

    return {
        "has_conflict": True,
        "conflict_type": "CORRELATED_EXPOSURE",
        "risk_level": risk_level,
        "candidate_ticker": cand_key,
        "candidate_sector": cand_sector,
        "candidate_clusters": list(cand_clusters),
        "conflicting_tickers": conflicting_tickers,
        "shared_sectors": list(shared_sectors),
        "shared_clusters": list(shared_clusters),
        "warning_message": warning_summary,
        "recommendation": recommendation,
    }


def analyze_portfolio_sector_distribution(
    positions: List[Dict[str, Any]],
    total_capital: Optional[float] = None,
) -> Dict[str, Any]:
    """Calcula a distribuição percentual da carteira por Setor e por Macro-Cluster,
    
    detectando concentrações anômalas e gerando pontuação de diversificação institucional.
    """
    if not positions:
        return {
            "total_invested": 0.0,
            "sector_breakdown": {},
            "cluster_breakdown": {},
            "concentration_warnings": [],
            "diversification_score": 100.0,
            "diversification_status": "CARTEIRA_ZERADA",
        }

    total_cost = sum(p.get("total_cost", 0.0) or (p.get("average_price", 0.0) * p.get("quantity", 0)) for p in positions)
    capital_base = total_capital if (total_capital and total_capital > 0) else max(total_cost, DEFAULT_CAPITAL)

    sector_totals: Dict[str, Dict[str, Any]] = {}
    cluster_totals: Dict[str, Dict[str, Any]] = {}

    for p in positions:
        ticker = p.get("ticker", "")
        cost = p.get("total_cost", 0.0) or (p.get("average_price", 0.0) * p.get("quantity", 0))
        profile = get_asset_sector_profile(ticker)
        sec = profile.get("sector", "Outros")
        clusters = profile.get("clusters", ["OUTROS"])

        # Agrupamento por Setor
        if sec not in sector_totals:
            sector_totals[sec] = {"total_cost": 0.0, "tickers": []}
        sector_totals[sec]["total_cost"] += cost
        sector_totals[sec]["tickers"].append(ticker)

        # Agrupamento por Macro-Cluster
        for c in clusters:
            if c not in cluster_totals:
                cluster_totals[c] = {"total_cost": 0.0, "tickers": []}
            cluster_totals[c]["total_cost"] += cost
            if ticker not in cluster_totals[c]["tickers"]:
                cluster_totals[c]["tickers"].append(ticker)

    # Computa percentuais e gera alertas
    sector_breakdown = {}
    warnings: List[str] = []

    for sec, data in sector_totals.items():
        pct = round((data["total_cost"] / capital_base) * 100, 1)
        sector_breakdown[sec] = {
            "total_cost": round(data["total_cost"], 2),
            "allocation_pct": pct,
            "tickers": data["tickers"],
            "count": len(data["tickers"]),
        }
        if pct > (MAX_SECTOR_ALLOCATION_PERCENT * 100):
            warnings.append(
                f"🚨 Concentração Setorial Excessiva: {sec} responde por {pct:.1f}% do capital "
                f"({', '.join(data['tickers'])}). Limite prudencial: {MAX_SECTOR_ALLOCATION_PERCENT*100:.0f}%."
            )

    cluster_breakdown = {}
    for cl, data in cluster_totals.items():
        pct = round((data["total_cost"] / capital_base) * 100, 1)
        cluster_breakdown[cl] = {
            "total_cost": round(data["total_cost"], 2),
            "allocation_pct": pct,
            "tickers": data["tickers"],
            "count": len(data["tickers"]),
        }
        # Se houver mais de MAX_CLUSTER_ACTIVE_TRADES no mesmo cluster
        if len(data["tickers"]) > MAX_CLUSTER_ACTIVE_TRADES:
            warnings.append(
                f"⚠️ Sobreposição no Cluster {cl}: Você possui {len(data['tickers'])} ativos "
                f"compartilhando o mesmo fator de risco ({', '.join(data['tickers'])}). "
                f"Quedas setoriais derrubam essas posições simultaneamente."
            )

    # Score de Diversificação (0 a 100)
    # Penalidades por número de warnings e concentrações
    base_score = 100.0
    for w in warnings:
        if "🚨" in w:
            base_score -= 25.0
        else:
            base_score -= 15.0
    diversification_score = max(10.0, min(100.0, base_score))

    if diversification_score >= 80:
        status_text = "EXCELENTE (Descorrelacionada)"
    elif diversification_score >= 60:
        status_text = "MODERADA (Atenção a sobreposições)"
    else:
        status_text = "CRÍTICA (Alta concentração de risco)"

    return {
        "total_invested": round(total_cost, 2),
        "capital_base": round(capital_base, 2),
        "sector_breakdown": sector_breakdown,
        "cluster_breakdown": cluster_breakdown,
        "concentration_warnings": warnings,
        "diversification_score": round(diversification_score, 1),
        "diversification_status": status_text,
    }


def filter_diversified_signals(
    signals: List[Dict[str, Any]],
    current_portfolio_tickers: Optional[List[str]] = None,
    max_signals: int = 3,
    allow_same_cluster: bool = False,
) -> List[Dict[str, Any]]:
    """Filtra e seleciona oportunidades de compra garantindo descorrelação institucional:
    
    1. Descarta ou penaliza ativos que colidem com clusters/setores já presentes na custódia do usuário.
    2. Garante que a cesta de recomendações NÃO contenha duas ações do mesmo setor ou cluster correlacionado.
    """
    if not signals:
        return []

    portfolio_tickers = current_portfolio_tickers or []
    enriched_signals: List[Dict[str, Any]] = []

    # 1. Enriquecimento de metadados setoriais em cada sinal
    for s in signals:
        tk = s.get("ticker", "")
        profile = get_asset_sector_profile(tk)
        s_copy = dict(s)
        s_copy["sector"] = profile.get("sector", "Outros")
        s_copy["subsector"] = profile.get("subsector", "Geral")
        s_copy["clusters"] = profile.get("clusters", [])
        s_copy["macro_risk_note"] = profile.get("macro_risk_note", "")

        # Checa colisão com a carteira em custódia
        if portfolio_tickers:
            conflict = check_sector_and_cluster_conflict(tk, portfolio_tickers)
            s_copy["has_portfolio_conflict"] = conflict["has_conflict"]
            s_copy["portfolio_conflict_warning"] = conflict["warning_message"]
            s_copy["portfolio_conflict_level"] = conflict["risk_level"]
        else:
            s_copy["has_portfolio_conflict"] = False
            s_copy["portfolio_conflict_warning"] = ""
            s_copy["portfolio_conflict_level"] = "LOW"

        enriched_signals.append(s_copy)

    # Ordena pelo maior score técnico
    enriched_signals.sort(key=lambda x: x.get("score", 0.0), reverse=True)

    # 2. Seleção de Cesta Descorrelacionada
    selected: List[Dict[str, Any]] = []
    seen_sectors: Set[str] = set()
    seen_clusters: Set[str] = set()

    for cand in enriched_signals:
        if len(selected) >= max_signals:
            break

        cand_sec = cand.get("sector", "Outros")
        cand_clusters = set(cand.get("clusters", []))

        # Se não permite colisão com a carteira e o ativo colide criticamente, pula para o próximo
        if not allow_same_cluster and cand.get("has_portfolio_conflict"):
            if cand.get("portfolio_conflict_level") == "HIGH":
                continue

        # Se o setor já foi selecionado na cesta recomendada de hoje
        if not allow_same_cluster and cand_sec in seen_sectors and cand_sec != "Outros":
            continue

        # Se algum cluster já foi selecionado na cesta recomendada de hoje
        has_cluster_clash = False
        if not allow_same_cluster:
            for sc in seen_clusters:
                for cc in cand_clusters:
                    if are_clusters_correlated(sc, cc):
                        has_cluster_clash = True
                        break
                if has_cluster_clash:
                    break

        if has_cluster_clash:
            continue

        # Sinal aprovado com diversificação
        cand["is_diversified_pick"] = True
        selected.append(cand)
        if cand_sec != "Outros":
            seen_sectors.add(cand_sec)
        seen_clusters.update(cand_clusters)

    # Se a filtragem rígida deixou a lista com menos de max_signals, preenche com as melhores restantes
    # marcando como alerta de repetição setorial
    if len(selected) < max_signals:
        for cand in enriched_signals:
            if len(selected) >= max_signals:
                break
            if cand not in selected:
                cand["is_diversified_pick"] = False
                selected.append(cand)

    return selected
