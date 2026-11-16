"""Motor Analítico e Conversacional do Chat Operacional (B3 Ações Pilot).

Avalia se é momento de COMPRAR, VENDER ou AGUARDAR determinado ativo,
cruzando Regime de Mercado, Indicadores Técnicos, Setups Quantitativos (IFR2, Trend, 52W Range)
e o estado atual da custódia do usuário (Real ou Simulada).
"""

import re
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
import pandas as pd

from b3pilot.ledger.db import Position
from b3pilot.ledger.portfolio import get_portfolio_summary, simulate_partial_exit
from b3pilot.core.regime import analyze_market_regime
from b3pilot.core.strategies import (
    compute_indicators,
    evaluate_ifr2_setup,
    evaluate_trend_setup,
    evaluate_reversal_pivot_setup,
    evaluate_bear_setup,
)
from b3pilot.core.exits import evaluate_open_positions_exits
from b3pilot.core.screener import run_screener
from b3pilot.core.risk import (
    check_sector_and_cluster_conflict,
    filter_diversified_signals,
    analyze_portfolio_sector_distribution,
)
from b3pilot.data.sectors import get_asset_sector_profile
from b3pilot.data.b3_feed import fetch_ticker_data, get_base_ticker


def extract_tickers_from_text(text: str) -> List[str]:
    """Extrai tickers da B3 presentes na mensagem (ex: PETR4, vale3, ITUB4, BOVA11)."""
    pattern = r"\b([A-Za-z]{4}(?:3|4|5|6|11))\b"
    matches = re.findall(pattern, text)
    seen = set()
    tickers = []
    for m in matches:
        tk = m.upper()
        if tk not in seen:
            seen.add(tk)
            tickers.append(tk)
    return tickers


def analyze_ticker_for_decision(
    ticker: str,
    session: Session,
    is_simulated: bool = False,
) -> Dict[str, Any]:
    """Realiza a radiografia técnica e de custódia completa de um ativo para tomada de decisão."""
    base_ticker = get_base_ticker(ticker)
    regime = analyze_market_regime()

    # 1. Checa se o usuário já possui o papel em custódia
    pos = (
        session.query(Position)
        .filter_by(ticker=base_ticker, is_simulated=is_simulated)
        .first()
    )

    df = fetch_ticker_data(base_ticker)
    if df is None or len(df) < 50:
        return {
            "ticker": base_ticker,
            "status": "NOT_FOUND",
            "message": f"Não foi possível obter dados históricos recentes para **{base_ticker}**. Verifique se o ticker está correto na B3.",
        }

    data = compute_indicators(df)
    last = data.iloc[-1]

    close = float(last["Close"])
    sma200 = float(last["SMA_200"]) if "SMA_200" in last and pd.notna(last["SMA_200"]) else None
    ema9 = float(last["EMA_9"]) if "EMA_9" in last and pd.notna(last["EMA_9"]) else None
    ema21 = float(last["EMA_21"]) if "EMA_21" in last and pd.notna(last["EMA_21"]) else None
    rsi2 = float(last["RSI_2"]) if "RSI_2" in last and pd.notna(last["RSI_2"]) else None
    rsi14 = float(last["RSI_14"]) if "RSI_14" in last and pd.notna(last["RSI_14"]) else 50.0

    high_52w = float(last["HIGH_52W"]) if "HIGH_52W" in last and pd.notna(last["HIGH_52W"]) else close * 1.2
    low_52w = float(last["LOW_52W"]) if "LOW_52W" in last and pd.notna(last["LOW_52W"]) else close * 0.8
    range_52w_pct = round(((close - low_52w) / (high_52w - low_52w)) * 100, 1) if high_52w > low_52w else 50.0
    dist_52w_high_pct = round(((high_52w - close) / close) * 100, 1) if close > 0 else 0.0

    # Avaliação de setups
    ifr2_setup = evaluate_ifr2_setup(df)
    trend_setup = evaluate_trend_setup(df)
    reversal_setup = evaluate_reversal_pivot_setup(df)
    bear_setup = evaluate_bear_setup(df)

    # =========================================================================
    # CASO 1: USUÁRIO JÁ POSSUI O PAPEL NA CARTEIRA (DECISÃO DE GESTÃO / VENDA)
    # =========================================================================
    if pos:
        qty = pos.quantity
        avg_price = pos.average_price
        unrealized_pnl = (close - avg_price) * qty
        unrealized_pct = ((close - avg_price) / avg_price) * 100

        # Checagem de Stop Loss
        if pos.stop_loss and close <= pos.stop_loss:
            return {
                "ticker": base_ticker,
                "action": "SELL_STOP",
                "badge": "🔴 VENDA OBRIGATÓRIA (STOP LOSS ATINGIDO)",
                "price": close,
                "pos_data": {
                    "quantity": qty,
                    "avg_price": avg_price,
                    "pnl_pct": unrealized_pct,
                    "stop_loss": pos.stop_loss,
                    "take_profit": pos.take_profit,
                },
                "summary": (
                    f"A cotação atual (R$ {close:.2f}) violou o seu Stop Loss cadastrado em **R$ {pos.stop_loss:.2f}** "
                    f"(Variação: {unrealized_pct:+.2f}%).\n\n"
                    f"**Orientação:** Não hesite nem espere repique. No Swing Trade disciplinado, respeitar o stop "
                    f"imediatamente é a regra de ouro que preserva seu patrimônio de perdas descontroladas."
                ),
            }

        # Checagem de Alvo de Realização Parcial (TP1)
        if pos.partial_target and not pos.is_partial_executed and close >= pos.partial_target:
            qty_part = pos.partial_quantity or (qty // 2 if qty > 1 else 1)
            rem_qty = qty - qty_part
            new_stop = pos.new_stop_after_partial or avg_price
            realized_half = (close - avg_price) * qty_part
            worst_case_profit = realized_half + ((new_stop - avg_price) * rem_qty)
            return {
                "ticker": base_ticker,
                "action": "PARTIAL_TARGET",
                "badge": "🎯 HORA DA REALIZAÇÃO PARCIAL (ALVO ATINGIDO)",
                "price": close,
                "pos_data": {
                    "quantity": qty,
                    "avg_price": avg_price,
                    "pnl_pct": unrealized_pct,
                    "stop_loss": pos.stop_loss,
                    "take_profit": pos.take_profit,
                },
                "summary": (
                    f"A cotação atingiu o seu Alvo Parcial em **R$ {pos.partial_target:.2f}** (Atual: R$ {close:.2f} | {unrealized_pct:+.2f}%).\n\n"
                    f"💰 **Resultado da Parcial:**\n"
                    f"• Venda de **{qty_part} ações** ({qty_part/qty*100:.0f}% da posição) a R$ {close:.2f} $\\to$ **R$ {realized_half:+,.2f} no bolso**.\n"
                    f"• Subida do Stop das **{rem_qty} ações** para **R$ {new_stop:.2f}**.\n"
                    f"• **Lucro Mínimo Garantido no Pior Caso:** **R$ {worst_case_profit:+,.2f}** (trade 100% blindado sem risco de perda).\n\n"
                    f"📋 **Roteiro no seu Home Broker:**\n"
                    f"1. Na aba 'Ordens', **cancele o stop antigo** de {qty} ações de {base_ticker}.\n"
                    f"2. Na aba 'Ordem/Boleta', **venda {qty_part} ações** a mercado.\n"
                    f"3. Na aba 'Stop', **cadastre novo stop de {rem_qty} ações** em R$ {new_stop:.2f}."
                ),
            }

        # Checagem de Alvo (Take Profit)
        if pos.take_profit and close >= pos.take_profit:
            return {
                "ticker": base_ticker,
                "action": "SELL_PROFIT",
                "badge": "🟢 REALIZAR LUCROS (ALVO DE LUCRO ATINGIDO)",
                "price": close,
                "pos_data": {
                    "quantity": qty,
                    "avg_price": avg_price,
                    "pnl_pct": unrealized_pct,
                    "stop_loss": pos.stop_loss,
                    "take_profit": pos.take_profit,
                },
                "summary": (
                    f"A cotação atingiu ou superou seu Alvo de Lucro projetado em **R$ {pos.take_profit:.2f}** "
                    f"(Lucro não realizado de **{unrealized_pct:+.2f}%** | R$ {unrealized_pnl:+,.2f})!\n\n"
                    f"**Orientação:** Realize o lucro total ou ao menos uma saída parcial (50%), subindo o stop loss "
                    f"do restante da posição para o seu preço de entrada (R$ {avg_price:.2f}) para garantir o ganho."
                ),
            }

        # Alerta de Pressão Vendedora na posição aberta
        if bear_setup:
            return {
                "ticker": base_ticker,
                "action": "CAUTION_SELL",
                "badge": "⚠️ ATENÇÃO: PRESSÃO VENDEDORA DETECTADA",
                "price": close,
                "pos_data": {
                    "quantity": qty,
                    "avg_price": avg_price,
                    "pnl_pct": unrealized_pct,
                    "stop_loss": pos.stop_loss,
                    "take_profit": pos.take_profit,
                },
                "summary": (
                    f"O papel armou estrutura de baixa de curto prazo (Preço abaixo da EMA 9 e EMA 21 com perda de mínima).\n"
                    f"• Seu P&L atual: **{unrealized_pct:+.2f}%**\n"
                    f"• Stop cadastrado: R$ {pos.stop_loss if pos.stop_loss else 'Não definido'}\n\n"
                    f"**Orientação:** Se você estiver com lucro, avalie antecipar a saída ou subir o stop para a mínima recente. "
                    f"Se estiver próximo do stop, mantenha a disciplina e não faça preço médio para trás."
                ),
            }

        # Posição saudável
        return {
            "ticker": base_ticker,
            "action": "HOLD",
            "badge": "🟡 MANTER POSIÇÃO (EM ANDAMENTO)",
            "price": close,
            "pos_data": {
                "quantity": qty,
                "avg_price": avg_price,
                "pnl_pct": unrealized_pct,
                "stop_loss": pos.stop_loss,
                "take_profit": pos.take_profit,
            },
            "summary": (
                f"Sua posição em **{base_ticker}** segue dentro dos parâmetros técnicos normais.\n"
                f"• Preço Atual: R$ {close:.2f} | Preço Médio: R$ {avg_price:.2f} ({unrealized_pct:+.2f}%)\n"
                f"• Stop Loss: R$ {pos.stop_loss if pos.stop_loss else 'Não definido'} | Alvo: R$ {pos.take_profit if pos.take_profit else 'Não definido'}\n"
                f"• Médias: {'Acima da EMA 9' if ema9 and close >= ema9 else 'Abaixo da EMA 9'}\n\n"
                f"**Orientação:** Mantenha o trade sem ansiedade até o toque no Alvo ou no Stop Loss."
            ),
        }

    # =========================================================================
    # CASO 2: USUÁRIO NÃO POSSUI O PAPEL (AVALIAÇÃO DE NOVA COMPRA)
    # =========================================================================

    # Bloqueio de Pânico Sistêmico
    if regime["status"] == "PANIC":
        return {
            "ticker": base_ticker,
            "action": "BLOCKED_PANIC",
            "badge": "🚨 COMPRA PROIBIDA (PÂNICO NO IBOVESPA)",
            "price": close,
            "summary": (
                f"O Ibovespa está em regime de **PÂNICO SISTÊMICO** ({regime['description']}).\n"
                f"Novas entradas em ações estão bloqueadas pelo gatekeeper de risco para preservar o capital."
            ),
        }

    # Auditoria de Concentração Setorial e Correlação Cruzada contra a Carteira do Usuário
    open_positions = session.query(Position).filter_by(is_simulated=is_simulated).all()
    open_tickers = [p.ticker for p in open_positions]
    sec_conflict = check_sector_and_cluster_conflict(base_ticker, open_tickers) if open_tickers else {"has_conflict": False}

    sec_profile = get_asset_sector_profile(base_ticker)
    sector_info_str = f"Setor: **{sec_profile.get('sector', 'Diversificado')}** ({sec_profile.get('subsector', '')})"

    conflict_addon = ""
    if sec_conflict.get("has_conflict"):
        conflict_addon = (
            f"\n\n⚠️ **ALERTA INSTITUCIONAL DE CORRELAÇÃO SETORIAL:**\n"
            f"• {sec_conflict['warning_message']}\n"
            f"• **Risco:** {sec_conflict['recommendation']}"
        )

    # 1. Setup IFR2 Ativo (Oportunidade de Reversão à Média)
    if ifr2_setup:
        badge = "🟢 COMPRA RECOMENDADA (Setup IFR2 Ativo)"
        if sec_conflict.get("has_conflict") and sec_conflict.get("risk_level") == "HIGH":
            badge = "⚠️ COMPRA COM RESSALVA (Sobreposição com Ativos em Custódia)"

        return {
            "ticker": base_ticker,
            "action": "BUY_IFR2",
            "badge": badge,
            "price": close,
            "setup": ifr2_setup,
            "sector": sec_profile.get("sector"),
            "summary": (
                f"**Oportunidade de Reversão à Média identificada!** ({sector_info_str})\n"
                f"• **Gatilho:** IFR(2) em **{ifr2_setup['rsi2']:.1f}** (sobrevenda aguda) acima da SMA 200.\n"
                f"• **Preço de Referência:** R$ {ifr2_setup['entry_price']:.2f}\n"
                f"• **Alvo Imediato:** R$ {ifr2_setup['take_profit']:.2f} (Máxima dos últimos 2 pregões)\n"
                f"• **Stop Catastrófico Dinâmico:** R$ {ifr2_setup['stop_loss']:.2f}\n"
                f"• **Regra Estrita de Saída:** Time-Stop compulsório no 5º pregão se não bater alvo.\n"
                f"• **Posição no Range de 52S:** {range_52w_pct:.0f}% (Desconto de -{dist_52w_high_pct:.1f}% da máxima anual)\n"
                f"• **Score de Confluência:** {ifr2_setup['score']:.1f} / 10\n\n"
                f"**Orientação:** Compra confluente na abertura ou leilão, respeitando rigorosamente o limite de risco de 2%."
                f"{conflict_addon}"
            ),
        }

    # 2. Setup Retomada de Fundo (Pivô Concluído / Teste de Suporte)
    if reversal_setup:
        return {
            "ticker": base_ticker,
            "action": "BUY_REVERSAL_PIVOT",
            "badge": "🟢 COMPRA RECOMENDADA (Retomada de Fundo / Pivô Concluído)",
            "price": close,
            "setup": reversal_setup,
            "summary": (
                f"**Oportunidade de Retomada de Fundo Concluída!**\n"
                f"• **Conclusão de Suporte:** Ativo testou fundo e superou a EMA 9 com candle comprador.\n"
                f"• **Ampla Pista Livre:** +{dist_52w_high_pct:.1f}% de espaço desobstruído até o topo anual (R$ {high_52w:.2f})\n"
                f"• **Posição no Range 52S:** {range_52w_pct:.0f}% (Ativo defasado com excelente assimetria)\n"
                f"• **Preço Entrada:** R$ {reversal_setup['entry_price']:.2f}\n"
                f"• **Stop Técnico no Fundo:** R$ {reversal_setup['stop_loss']:.2f}\n"
                f"• **Alvo Projetado (2.5R):** R$ {reversal_setup['take_profit']:.2f}\n"
                f"• **Relação Risco/Retorno:** {reversal_setup['rr_ratio']}x | Score: {reversal_setup['score']:.1f} / 10\n\n"
                f"**Orientação:** Excelente compra em ativo defasado que já confirmou reversão técnica após estancar queda."
            ),
        }

    # 3. Setup Seguidor de Tendência Ativo (Momentum com Pullback Saudável no Sweet Spot)
    if trend_setup:
        return {
            "ticker": base_ticker,
            "action": "BUY_TREND",
            "badge": "🟢 COMPRA RECOMENDADA (Seguidor de Tendência - Sweet Spot)",
            "price": close,
            "setup": trend_setup,
            "summary": (
                f"**Oportunidade de Seguidor de Tendência com Pullback Saudável!**\n"
                f"• **Alinhamento:** Preço (R$ {close:.2f}) > EMA 9 > EMA 21 > SMA 200\n"
                f"• **Pista Livre até Máxima:** +{dist_52w_high_pct:.1f}% de folga até o topo de 52S (R$ {high_52w:.2f})\n"
                f"• **Preço Entrada:** R$ {trend_setup['entry_price']:.2f}\n"
                f"• **Stop Técnico:** R$ {trend_setup['stop_loss']:.2f}\n"
                f"• **Alvo Assimétrico (2.5R):** R$ {trend_setup['take_profit']:.2f}\n"
                f"• **Relação Risco/Retorno:** {trend_setup['rr_ratio']}x\n"
                f"• **Score de Confluência:** {trend_setup['score']:.1f} / 10\n\n"
                f"**Orientação:** Ponto de entrada confluente saindo de suporte de médias sem barreira de topo esticado."
            ),
        }

    # 4. Papel Esticado no Topo de 52 Semanas (Risco de Exaustão de Resistência)
    if (range_52w_pct >= 80.0 and dist_52w_high_pct < 8.0) or (dist_52w_high_pct < 5.0 and rsi14 >= 65.0):
        return {
            "ticker": base_ticker,
            "action": "AVOID_OVEREXTENDED",
            "badge": "🟡 AGUARDAR: RISCO DE EXAUSTÃO NO TOPO ANUAL",
            "price": close,
            "summary": (
                f"O papel está a apenas **{dist_52w_high_pct:.1f}% da máxima de 52 semanas** (R$ {high_52w:.2f}) "
                f"e ocupando **{range_52w_pct:.0f}% do range anual**, com **IFR(14) em {rsi14:.1f}**.\n\n"
                f"**Diagnóstico de Risco:** Comprar na cara do topo histórico oferece relação Risco/Retorno invertida "
                f"(arrisca-se um recuo de 8% a 12% para tentar capturar 2% a 4% antes da máxima). "
                f"Além disso, em eventos ou datas marcadas, a chegada ao topo costuma ser gatilho de realização institucional (*sell the news*).\n"
                f"• **Orientação:** Aguarde um pullback saudável até as médias (EMA 9 ou 21) para entrar com stop barato."
            ),
        }

    # 5. Papel em Tendência de Baixa Primária (Abaixo da SMA 200 - Faca Caindo sem Suporte)
    if sma200 and close < sma200:
        pct_below = ((sma200 - close) / sma200) * 100
        return {
            "ticker": base_ticker,
            "action": "AVOID_BEAR",
            "badge": "🔴 NÃO COMPRAR (TENDÊNCIA DE BAIXA / FACA CAINDO)",
            "price": close,
            "summary": (
                f"O ativo está cotado a **R$ {close:.2f}**, operando **{pct_below:.1f}% abaixo da média de 200 dias (SMA 200: R$ {sma200:.2f})** sem pivô de reversão confirmado.\n\n"
                f"**Diagnóstico de Risco:** 'Estar barato' ou 'ter caído muito' não é sinal de compra. "
                f"Comprar ativo em queda livre abaixo da SMA 200 é a clássica armadilha de tentar pegar a faca caindo.\n"
                f"• **Orientação:** Não compre agora. Aguarde o papel estancar a queda, fazer suporte duplo e fechar acima da **EMA 9** com candle de reversão antes de considerar entrada."
            ),
        }

    # 6. Papel em Tendência mas sem Pullback ou Gatilho no Momento
    if ema9 and ema21 and close > ema9 and ema9 > ema21:
        return {
            "ticker": base_ticker,
            "action": "WAIT_PULLBACK",
            "badge": "🟡 AGUARDAR PULLBACK (TENDÊNCIA DE ALTA SEM GATILHO)",
            "price": close,
            "summary": (
                f"O papel está em tendência de alta estrutural (acima de EMA 9 e EMA 21), mas **não há gatilho de entrada armado hoje**.\n"
                f"• Preço Atual: R$ {close:.2f} | EMA 9: R$ {ema9:.2f} | EMA 21: R$ {ema21:.2f}\n"
                f"• Posição no Range Anual (52S): {range_52w_pct:.0f}%\n\n"
                f"**Orientação:** Aguarde o preço testar o suporte das médias (EMA 9/21) com candle de reversão para ter um stop técnico barato."
            ),
        }

    # 6. Neutro / Sem Setup Confluente
    return {
        "ticker": base_ticker,
        "action": "NEUTRAL",
        "badge": "🟡 AGUARDAR (SEM SETUP CONFLUENTE NO MOMENTO)",
        "price": close,
        "summary": (
            f"O ativo **{base_ticker}** (R$ {close:.2f}) não apresenta sinal claro de compra nem de venda no momento.\n"
            f"• IFR(2): {rsi2:.1f if rsi2 else '-'} (neutro)\n"
            f"• Posição no Range Anual: {range_52w_pct:.0f}% [Mín R$ {low_52w:.2f} ── Máx R$ {high_52w:.2f}]\n\n"
            f"**Orientação:** Aguarde uma oportunidade confluente de Reversão à Média (IFR2 <= 10) ou Seguidor de Tendência."
        ),
    }


def process_chat_query(
    user_message: str,
    session: Session,
    is_simulated: bool = False,
) -> str:
    """Interpreta a mensagem do usuário e gera uma resposta técnica contextualizada."""
    msg_clean = user_message.strip()
    msg_lower = msg_clean.lower()
    tickers = extract_tickers_from_text(msg_clean)
    env_name = "Simulada (Paper Trading)" if is_simulated else "Real"

    # 1. Se o usuário perguntou sobre simulação de realização parcial de um papel
    if any(k in msg_lower for k in ["parcial", "scale-out", "metade"]) and tickers:
        tk = tickers[0]
        pos = session.query(Position).filter_by(ticker=tk, is_simulated=is_simulated).first()
        if not pos:
            return (
                f"### 🧮 Simulação de Realização Parcial — **{tk}**\n\n"
                f"Você ainda não possui **{tk}** em sua custódia {env_name} para simular uma realização parcial. "
                f"Cadastre primeiro a compra para podermos calcular o lucro garantido e elevação de stop."
            )

        # Extrai números de preço e stop na mensagem
        num_matches = re.findall(r"\b(\d+[.,]\d{1,2}|\d+)\b", msg_clean)
        nums = []
        for n in num_matches:
            try:
                val = float(n.replace(",", "."))
                # Filtra números irrelevantes como ano ou dígito do ticker
                tk_digit = int(tk[4:]) if len(tk) > 4 and tk[4:].isdigit() else -1
                if val < 500 and val != tk_digit:
                    nums.append(val)
            except ValueError:
                pass

        target_p = nums[0] if len(nums) >= 1 else (pos.partial_target or pos.take_profit or round(pos.average_price * 1.08, 2))
        new_st = nums[1] if len(nums) >= 2 else (pos.new_stop_after_partial or round(pos.average_price * 1.02, 2))

        sim = simulate_partial_exit(session, tk, target_price=target_p, new_stop_loss=new_st, is_simulated=is_simulated)
        if "error" in sim:
            return f"❌ {sim['error']}"

        return (
            f"### 🧮 Simulação de Realização Parcial — **{tk}**\n\n"
            f"• **Posição Atual:** {sim['total_quantity']} ações a Preço Médio de R$ {sim['average_price']:.2f}\n"
            f"• **Preço de Saída da Parcial:** R$ {sim['target_price']:.2f} ({sim['realized_pct_half']:+.2f}%)\n"
            f"• **Venda de 50%:** {sim['qty_to_sell']} ações $\\to$ **Lucro Embolsado de R$ {sim['realized_profit_half']:+,.2f}**\n"
            f"• **Novo Stop das {sim['qty_remaining']} ações:** R$ {sim['new_stop_loss']:.2f} ({sim['worst_case_remaining_pct']:+.2f}%)\n\n"
            f"🛡️ **Garantia de Lucro no Pior Cenário:**\n"
            f"Se as {sim['qty_remaining']} ações restantes baterem no novo stop em R$ {sim['new_stop_loss']:.2f}, seu resultado final consolidado ainda será de **R$ {sim['guaranteed_total_profit']:+,.2f}** ({sim['guaranteed_total_pct']:+.2f}% do capital investido)!\n\n"
            f"📋 **Passo a Passo para Executar no seu Home Broker:**\n"
            f"1. Cancele a ordem de Stop atual de {sim['total_quantity']} ações de {tk}.\n"
            f"2. Venda a mercado {sim['qty_to_sell']} ações a R$ {sim['target_price']:.2f}.\n"
            f"3. Cadastre novo Stop de {sim['qty_remaining']} ações no valor de disparo de R$ {sim['new_stop_loss']:.2f}."
        )

    # 2. Se o usuário mencionou um ou mais tickers específicos (análise geral)
    if tickers:
        responses = []
        for tk in tickers[:3]:  # Analisa até 3 tickers por mensagem para performance
            analysis = analyze_ticker_for_decision(tk, session, is_simulated=is_simulated)
            if analysis.get("status") == "NOT_FOUND":
                responses.append(f"### 🔍 {tk}\n{analysis['message']}")
            else:
                responses.append(
                    f"### 📈 Parecer Operacional para **{analysis['ticker']}**\n"
                    f"**Veredito:** `{analysis['badge']}`\n\n"
                    f"{analysis['summary']}"
                )
        return "\n\n---\n\n".join(responses)

    # 2. Dúvida sobre o IBOVESPA / Mercado geral
    if any(k in msg_lower for k in ["ibov", "ibovespa", "mercado", "regime", "bolsa"]):
        regime = analyze_market_regime()
        return (
            f"### 🏛️ Diagnóstico do Mercado (IBOVESPA)\n\n"
            f"• **Status:** `{regime['name']}` ({regime['status']})\n"
            f"• **Fechamento Atual:** R$ {regime.get('ibov_close', 0):,.0f} ({regime.get('ibov_change_pct', 0):+.2f}%)\n"
            f"• **Multiplicador de Capital Autorizado:** `{regime['allocation_multiplier'] * 100:.0f}%` do lote padrão\n"
            f"• **Estratégias Liberadas:**\n"
            f"  - Reversão à Média (IFR2): {'✅ Sim' if regime['allow_ifr2'] else '❌ Pausado'}\n"
            f"  - Seguidor de Tendência (Momentum): {'✅ Sim' if regime['allow_momentum'] else '❌ Pausado'}\n"
            f"  - Captura de Proventos: {'✅ Sim' if regime['allow_dividends'] else '❌ Pausado'}\n\n"
            f"**Diagnóstico Técnico:** {regime['description']}"
        )

    # 3. Dúvida sobre Vender ou Saídas da Carteira
    if any(k in msg_lower for k in ["vender", "saída", "saida", "stop", "alvo", "encerrar"]):
        exits = evaluate_open_positions_exits(session, is_simulated=is_simulated)
        if not exits:
            summary = get_portfolio_summary(session, is_simulated=is_simulated)
            total_pos = len(summary["positions"])
            return (
                f"### 🛡️ Auditoria de Saídas — Custódia {env_name}\n\n"
                f"✅ **Nenhuma posição atingiu Stop Loss, Alvo ou Time-Stop hoje.**\n\n"
                f"Você possui **{total_pos} posições abertas** e todas continuam operando dentro dos parâmetros de risco planejados. "
                f"Mantenha a paciência operacional."
            )
        else:
            alert_items = []
            for ex in exits:
                alert_items.append(
                    f"• **{ex['ticker']}** ({ex['type']}): {ex['reason']} (Urgência: `{ex['urgency']}`)"
                )
            return (
                f"### 🚨 Alertas Críticos de Saída — Custódia {env_name}\n\n"
                f"Foram identificados **{len(exits)} disparos de saída** obrigatórios:\n\n"
                + "\n".join(alert_items)
                + "\n\n**Recomendação:** Execute essas ordens no início do pregão para honrar seu plano de trade."
            )

    # 4. Dúvida sobre Compras / Oportunidades no radar
    if any(k in msg_lower for k in ["comprar", "compro", "oportunidade", "oportunidades", "radar", "entrar", "qual ação"]):
        opps = run_screener(min_score=7.0, high_conviction_only=True, show_progress=False)
        if not opps:
            opps = run_screener(min_score=7.0, high_conviction_only=False, show_progress=False)

        if not opps:
            return (
                f"### 🎯 Radar de Compras\n\n"
                f"Nenhuma oportunidade atingiu a nota mínima de confluência hoje no universo da B3.\n"
                f"Quando o mercado não oferece risco/retorno favorável, **ficar em caixa é uma decisão ativa de trade**."
            )

        open_positions = session.query(Position).filter_by(is_simulated=is_simulated).all()
        open_tickers = [p.ticker for p in open_positions]

        # Seleção descorrelacionada que protege contra apostas no mesmo setor ou setores cruzados
        top_opps = filter_diversified_signals(
            opps,
            current_portfolio_tickers=open_tickers,
            max_signals=3,
            allow_same_cluster=False,
        )

        opp_lines = []
        for op in top_opps:
            sec_label = f"[{op.get('sector', 'Ações')} — {op.get('subsector', '')}]"
            div_status = "✓ Descorrelacionado" if op.get("is_diversified_pick", True) else "⚠️ Risco de Sobreposição"
            opp_lines.append(
                f"• **{op['ticker']}** ({op['name']}) {sec_label} — **Nota {op['score']}/10**\n"
                f"  - **Diversificação:** {div_status}\n"
                f"  - Entrada Ref.: R$ {op['entry_price']:.2f} | Stop: R$ {op['stop_loss']:.2f} | Alvo: R$ {op['take_profit']:.2f} (R/R: {op.get('rr_ratio', 'N/A')}x)\n"
                f"  - Range 52S: {op.get('range_52w_pct', 0):.0f}% do canal anual"
            )

        diversification_note = ""
        if open_tickers:
            diversification_note = (
                f"\n\n🛡️ *Filtro Institucional Ativo:* As sugestões acima excluem empresas do mesmo setor "
                f"ou com correlação cruzada com seus ativos em custódia ({', '.join(open_tickers)})."
            )

        return (
            f"### 🎯 Top Oportunidades Descorrelacionadas no Radar\n\n"
            + "\n\n".join(opp_lines)
            + diversification_note
            + f"\n\n*Para ver a análise detalhada de qualquer uma, digite por exemplo: `Analisar {top_opps[0]['ticker']}`.*"
        )

    # 5. Resposta Guia / Instruções de uso
    return (
        f"Olá! Sou o seu **Assistente Operacional da B3**.\n\n"
        f"Posso orientar suas decisões antes da abertura ou durante o pregão. Exemplos do que você pode me perguntar:\n\n"
        f"• *\"Posso comprar PETR4 agora?\"* ou *\"Vale a pena comprar BBAS3?\"*\n"
        f"• *\"Devo vender alguma posição da minha carteira hoje?\"*\n"
        f"• *\"Como está o IBOVESPA hoje?\"*\n"
        f"• *\"Quais são as melhores oportunidades de compra no radar?\"*\n\n"
        f"Digite o código de qualquer ação da B3 para receber uma análise instantânea de compra, venda ou espera."
    )
