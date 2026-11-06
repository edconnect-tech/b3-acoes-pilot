"""Estratégias Quantitativas de Swing Trade: IFR2, Trend Following (Momentum com Pullback) e Bear Signals."""

from typing import Dict, Any, Optional
import pandas as pd
import pandas_ta as ta

from b3pilot.config import (
    IFR2_OVERSOLD_THRESHOLD,
    IFR2_EXTREME_OVERSOLD,
    IFR2_TREND_SMA,
    IFR2_CATASTROPHIC_STOP_PERCENT,
    IFR2_TIME_STOP_DAYS,
    TREND_EMA_FAST,
    TREND_EMA_SLOW,
    ATR_PERIOD,
    ATR_TRAILING_MULTIPLIER,
    MIN_ADTV_FINANCIAL,
)


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula indicadores técnicos essenciais no DataFrame OHLCV."""
    data = df.copy()

    # Médias Móveis
    data["SMA_200"] = ta.sma(data["Close"], length=IFR2_TREND_SMA)
    data["SMA_50"] = ta.sma(data["Close"], length=50)
    data["SMA_5"] = ta.sma(data["Close"], length=5)
    data["EMA_9"] = ta.ema(data["Close"], length=TREND_EMA_FAST)
    data["EMA_21"] = ta.ema(data["Close"], length=TREND_EMA_SLOW)

    # IFR de 2 períodos (Connors RSI) e IFR padrão 14
    data["RSI_2"] = ta.rsi(data["Close"], length=2)
    data["RSI_14"] = ta.rsi(data["Close"], length=14)

    # Volatilidade ATR
    data["ATR_14"] = ta.atr(data["High"], data["Low"], data["Close"], length=ATR_PERIOD)

    # Máxima dos últimos 2 pregões (alvo do IFR2)
    data["HIGH_2D"] = data["High"].shift(1).rolling(2).max()

    # Mínima dos últimos 3 pregões (suporte de stop)
    data["LOW_3D"] = data["Low"].shift(1).rolling(3).min()

    # Volume de ações e Volume Financeiro Real (ADTV21 em R$)
    data["VOL_MA21"] = data["Volume"].rolling(21).mean()
    data["ADTV_21"] = (data["Close"] * data["Volume"]).rolling(21).mean()

    # Range Anual / 52 Semanas (252 pregões)
    data["HIGH_52W"] = data["High"].rolling(252, min_periods=60).max()
    data["LOW_52W"] = data["Low"].rolling(252, min_periods=60).min()

    return data


def evaluate_ifr2_setup(df: pd.DataFrame, require_extreme_only: bool = False) -> Optional[Dict[str, Any]]:
    """Avalia se o ativo armou setup IFR2 (Reversão à Média Institucional de Larry Connors).
    
    Critérios de Robustez Quantitativa:
      - Tendência Primária: Preço > SMA 200.
      - Sobrevenda Aguda: IFR(2) <= 10.0 (ou <= 5.0 se require_extreme_only for True).
      - Filtro de Liquidez Real: ADTV21 >= R$ 5M/dia.
      - Gestão de Saída: Alvo na superação da máxima de 2 dias (HIGH_2D), Time-Stop no 5º pregão
        e Stop Catastrófico de 10% (evitando paradas por ruído intradiário).
    """
    if len(df) < 210:
        return None

    data = compute_indicators(df)
    last = data.iloc[-1]

    close = float(last["Close"])
    sma200 = float(last["SMA_200"])
    rsi2 = float(last["RSI_2"])
    atr = float(last["ATR_14"]) if pd.notna(last["ATR_14"]) else (close * 0.03)
    target = float(last["HIGH_2D"]) if pd.notna(last["HIGH_2D"]) else (close * 1.04)
    adtv = float(last["ADTV_21"]) if pd.notna(last["ADTV_21"]) else 0.0

    # 1. Filtro Eliminatório de Liquidez Financeira Real (ADTV >= R$ 5M)
    if adtv > 0 and adtv < MIN_ADTV_FINANCIAL:
        return None

    threshold = IFR2_EXTREME_OVERSOLD if require_extreme_only else IFR2_OVERSOLD_THRESHOLD

    if pd.notna(rsi2) and pd.notna(sma200):
        if close > sma200 and rsi2 <= threshold:
            # Stop Catastrófico Dinâmico: protege o capital limitando a perda entre -6% e -10% ancorado no ATR
            # Em papéis de baixa volatilidade não expõe 10% à toa; em alta volatilidade respeita o ruído intradiário.
            stop_dist = max(close * 0.06, min(close * IFR2_CATASTROPHIC_STOP_PERCENT, atr * 2.5))
            stop_loss = round(close - stop_dist, 2)
            risk = close - stop_loss
            reward = target - close
            rr_ratio = round(reward / risk, 2) if risk > 0 else 1.0

            pct_stop = round(((close - stop_loss) / close) * 100, 2)
            pct_target = round(((target - close) / close) * 100, 2)
            pct_sma200 = round(((close - sma200) / sma200) * 100, 2)
            vol_ma = float(last["VOL_MA21"]) if pd.notna(last["VOL_MA21"]) else 1.0
            vol_ratio = round(float(last["Volume"]) / vol_ma, 2) if vol_ma > 0 else 1.0

            high_52w = float(last["HIGH_52W"]) if "HIGH_52W" in last and pd.notna(last["HIGH_52W"]) else close * 1.2
            low_52w = float(last["LOW_52W"]) if "LOW_52W" in last and pd.notna(last["LOW_52W"]) else close * 0.8
            range_52w_pct = round(((close - low_52w) / (high_52w - low_52w)) * 100, 1) if high_52w > low_52w else 50.0
            dist_52w_high_pct = round(((high_52w - close) / close) * 100, 1) if close > 0 else 0.0

            # Pontuação de Confluência
            score = 7.0
            if rsi2 <= 5.0:
                score += 1.5  # Pânico extremo
            elif rsi2 <= 10.0:
                score += 1.0

            if vol_ratio > 1.2:
                score += 1.0  # Exaustão vendedora
            if adtv >= 20_000_000:
                score += 0.5  # Alta liquidez institucional

            reason = (
                f"🟢 Reversão à Média (IFR2 Institucional):\n"
                f"• IFR(2) em {rsi2:.1f} (Sobrevenda aguda com suporte de alta)\n"
                f"• Tendência Primária: +{pct_sma200:.1f}% acima da SMA 200 (R$ {sma200:.2f})\n"
                f"• Posição no Range Anual (52S): {range_52w_pct:.0f}% [Mín R$ {low_52w:.2f} ── Máx R$ {high_52w:.2f}] (Desconto do Topo: -{dist_52w_high_pct:.1f}%)\n"
                f"• Liquidez Financeira Real: R$ {adtv / 1e6:.1f}M/dia (ADTV 21)\n"
                f"• Alvo Imediato: R$ {target:.2f} (+{pct_target:.1f}% na máxima de 2 dias)\n"
                f"• Regra de Saída: Time-Stop estrito no 5º pregão ou Stop Catastrófico de -{pct_stop:.1f}% (R$ {stop_loss:.2f})"
            )

            return {
                "strategy": "IFR2",
                "name": "Reversão à Média (IFR2)",
                "signal": "BUY",
                "entry_price": round(close, 2),
                "stop_loss": stop_loss,
                "take_profit": round(target, 2),
                "rr_ratio": rr_ratio,
                "rsi2": round(rsi2, 1),
                "atr": round(atr, 2),
                "adtv_milhoes": round(adtv / 1e6, 2),
                "high_52w": round(high_52w, 2),
                "low_52w": round(low_52w, 2),
                "range_52w_pct": range_52w_pct,
                "dist_52w_high_pct": dist_52w_high_pct,
                "score": min(round(score, 1), 10.0),
                "reason": reason,
            }

    return None


def evaluate_trend_setup(df: pd.DataFrame) -> Optional[Dict[str, Any]]:
    """Avalia se o ativo armou setup Seguidor de Tendência / Momentum com Pullback nas Médias.
    
    Critérios de Robustez Quantitativa:
      - Alinhamento Altista: Preço > EMA 9 > EMA 21 > SMA 200.
      - Pullback Saudável: Mínima recente testou a região da EMA 9/21 sem romper a estrutura.
      - Gatilho: Candle de retomada compradora saindo da média (evitando compras de topo).
      - Filtro de Liquidez Real: ADTV21 >= R$ 5M/dia.
    """
    if len(df) < 210:
        return None

    data = compute_indicators(df)
    last = data.iloc[-1]
    prev = data.iloc[-2]

    close = float(last["Close"])
    open_p = float(last["Open"])
    ema9 = float(last["EMA_9"])
    prev_ema9 = float(prev["EMA_9"])
    ema21 = float(last["EMA_21"])
    sma200 = float(last["SMA_200"])
    atr = float(last["ATR_14"]) if pd.notna(last["ATR_14"]) else (close * 0.03)
    adtv = float(last["ADTV_21"]) if pd.notna(last["ADTV_21"]) else 0.0

    # 1. Filtro de Liquidez Financeira Real
    if adtv > 0 and adtv < MIN_ADTV_FINANCIAL:
        return None

    if pd.notna(ema9) and pd.notna(ema21) and pd.notna(sma200):
        # 1. Alinhamento de tendência primária e secundária
        is_uptrend = close >= ema9 and ema9 > ema21 and ema21 > sma200 and ema9 > prev_ema9

        # 2. Confirmação de Pullback: o preço testou a proximidade da EMA 9/21
        low_touched_ema = float(last["Low"]) <= (ema9 * 1.015) or float(prev["Low"]) <= (prev_ema9 * 1.015)
        is_green_reversal = close >= open_p or close > float(prev["Close"])
        crossed_up = prev["Close"] <= prev["EMA_9"] and close > ema9

        valid_trigger = is_uptrend and ((low_touched_ema and is_green_reversal) or crossed_up)

        if valid_trigger:
            stop_loss = round(min(float(last["Low"]), float(prev["Low"])) - (atr * 0.5), 2)
            risk = close - stop_loss
            if risk <= 0:
                stop_loss = round(close - (atr * 1.5), 2)
                risk = close - stop_loss

            target = round(close + (risk * 2.5), 2)
            rr_ratio = round((target - close) / risk, 2)

            pct_stop = round(((close - stop_loss) / close) * 100, 2)
            pct_target = round(((target - close) / close) * 100, 2)
            vol_ma = float(last["VOL_MA21"]) if pd.notna(last["VOL_MA21"]) else 1.0
            vol_ratio = round(float(last["Volume"]) / vol_ma, 2) if vol_ma > 0 else 1.0
            rsi14 = float(last["RSI_14"]) if pd.notna(last["RSI_14"]) else 50.0

            high_52w = float(last["HIGH_52W"]) if "HIGH_52W" in last and pd.notna(last["HIGH_52W"]) else close * 1.2
            low_52w = float(last["LOW_52W"]) if "LOW_52W" in last and pd.notna(last["LOW_52W"]) else close * 0.8
            range_52w_pct = round(((close - low_52w) / (high_52w - low_52w)) * 100, 1) if high_52w > low_52w else 50.0
            dist_52w_high_pct = round(((high_52w - close) / close) * 100, 1) if close > 0 else 0.0
            upside_to_res_ratio = round((high_52w - close) / risk, 2) if risk > 0 else 1.0

            # 3. Gatekeeper Anti-Topo Esticado (Filtro de Exaustão de Resistência)
            # Se o ativo está nos 20% superiores do range anual (range >= 80%) com folga < 8%
            # OU se a distância até o topo for inferior a 5% com IFR14 sobrecomprado (>= 65):
            is_overextended_top = (range_52w_pct >= 80.0 and dist_52w_high_pct < 8.0) or (dist_52w_high_pct < 5.0 and rsi14 >= 65.0)
            if is_overextended_top:
                # VETO ESTRITO: Não indica compra cega de seguidor de tendência na cara do topo de 52 semanas
                return None

            # Pontuação de Confluência
            score = 7.0
            if vol_ratio > 1.3:
                score += 1.5  # Retomada com volume expressivo
            if (ema9 - ema21) / ema21 > 0.02:
                score += 1.0  # Divergência e aceleração de médias
            if adtv >= 20_000_000:
                score += 0.5

            # Bonificação por Assimetria / Espaço Livre até o Topo Anual (52 Semanas)
            resistance_note = ""
            if dist_52w_high_pct >= 10.0 and range_52w_pct <= 80.0:
                score += 1.5  # Sweet Spot: Tendência de alta com ampla pista livre
                resistance_note = f"• Pista Livre até Topo Anual: +{dist_52w_high_pct:.1f}% até máxima de 52S (R$ {high_52w:.2f}) | Assimetria favorável ({upside_to_res_ratio:.1f}x do risco)\n"
            elif dist_52w_high_pct >= 6.0:
                score += 0.5
                resistance_note = f"• Margem até Topo Anual: +{dist_52w_high_pct:.1f}% até máxima de 52S (R$ {high_52w:.2f})\n"

            reason = (
                f"🚀 Seguidor de Tendência (Momentum com Pullback Saudável):\n"
                f"• Alinhamento Altista: Preço (R$ {close:.2f}) > EMA 9 > EMA 21 > SMA 200\n"
                f"• Retração Saudável: Testou suporte de médias e retomou força compradora\n"
                f"{resistance_note}"
                f"• Posição no Range Anual (52S): {range_52w_pct:.0f}% [Mín R$ {low_52w:.2f} ── Máx R$ {high_52w:.2f}]\n"
                f"• Liquidez Financeira Real: R$ {adtv / 1e6:.1f}M/dia (ADTV 21)\n"
                f"• Volume Financeiro: {vol_ratio:.1f}x da média de 21 dias\n"
                f"• Assimetria Projetada: Alvo 2.5R em R$ {target:.2f} (+{pct_target:.1f}%) | Stop Técnico em R$ {stop_loss:.2f} (-{pct_stop:.1f}%)"
            )

            return {
                "strategy": "TREND",
                "name": "Seguidor de Tendência (Momentum)",
                "signal": "BUY",
                "entry_price": round(close, 2),
                "stop_loss": stop_loss,
                "take_profit": target,
                "trailing_stop": round(close - (atr * ATR_TRAILING_MULTIPLIER), 2),
                "rr_ratio": rr_ratio,
                "atr": round(atr, 2),
                "adtv_milhoes": round(adtv / 1e6, 2),
                "high_52w": round(high_52w, 2),
                "low_52w": round(low_52w, 2),
                "range_52w_pct": range_52w_pct,
                "dist_52w_high_pct": dist_52w_high_pct,
                "score": min(round(score, 1), 10.0),
                "reason": reason,
            }

    return None


def evaluate_reversal_pivot_setup(df: pd.DataFrame) -> Optional[Dict[str, Any]]:
    """Avalia se o ativo armou setup de Retomada de Fundo / Pivô Concluído (Fundo Duplo / Teste de Suporte).
    
    Critérios de Robustez Quantitativa:
      - Ativo com Desconto Estrutural: Posição no Range 52S <= 75% e folga até a máxima >= 12%.
      - Não está em sobrecompra: IFR(14) <= 63.0.
      - Confirmação de Pivô: Preço cruzou e fechou acima da EMA 9 com candle comprador (Close > Open e Close > Prev Close).
      - Média rápida estabilizando ou virando para cima (EMA 9 >= Prev EMA 9 * 0.998).
      - Risco/Retorno mínimo de 2.0x com alvo na SMA 50/200 ou na projeção de 2.5R.
      - Filtro de Liquidez Real: ADTV21 >= R$ 5M/dia.
    """
    if len(df) < 210:
        return None

    data = compute_indicators(df)
    last = data.iloc[-1]
    prev = data.iloc[-2]
    prev2 = data.iloc[-3] if len(data) >= 3 else prev

    close = float(last["Close"])
    open_p = float(last["Open"])
    ema9 = float(last["EMA_9"])
    prev_ema9 = float(prev["EMA_9"])
    ema21 = float(last["EMA_21"])
    sma200 = float(last["SMA_200"]) if pd.notna(last["SMA_200"]) else None
    atr = float(last["ATR_14"]) if pd.notna(last["ATR_14"]) else (close * 0.03)
    adtv = float(last["ADTV_21"]) if pd.notna(last["ADTV_21"]) else 0.0
    rsi14 = float(last["RSI_14"]) if pd.notna(last["RSI_14"]) else 50.0

    if adtv > 0 and adtv < MIN_ADTV_FINANCIAL:
        return None

    if not (pd.notna(ema9) and pd.notna(ema21)):
        return None

    high_52w = float(last["HIGH_52W"]) if "HIGH_52W" in last and pd.notna(last["HIGH_52W"]) else close * 1.3
    low_52w = float(last["LOW_52W"]) if "LOW_52W" in last and pd.notna(last["LOW_52W"]) else close * 0.7
    range_52w_pct = round(((close - low_52w) / (high_52w - low_52w)) * 100, 1) if high_52w > low_52w else 50.0
    dist_52w_high_pct = round(((high_52w - close) / close) * 100, 1) if close > 0 else 0.0

    # 1. Filtro de Assimetria: NÃO pode estar no topo esticado; deve ter folga >= 12% até a máxima
    if range_52w_pct > 75.0 or dist_52w_high_pct < 12.0 or rsi14 > 63.0:
        return None

    # 2. Gatilho de Reversão de Fundo:
    # Preço retomou acima da EMA 9 com barra compradora
    reclaimed_ema9 = close > ema9 and (float(prev["Close"]) <= float(prev["EMA_9"]) or float(prev2["Close"]) <= float(prev2["EMA_9"]))
    is_bullish_bar = close >= open_p and close > float(prev["Close"])
    has_support_base = float(last["Low"]) >= float(prev["Low"]) * 0.995 or float(prev["Low"]) >= float(prev2["Low"]) * 0.995

    if reclaimed_ema9 and is_bullish_bar and has_support_base:
        recent_low = min(float(last["Low"]), float(prev["Low"]), float(prev2["Low"]))
        stop_loss = round(recent_low - (atr * 0.4), 2)
        risk = close - stop_loss
        if risk <= 0:
            stop_loss = round(close - (atr * 1.2), 2)
            risk = close - stop_loss

        target = round(close + (risk * 2.5), 2)
        rr_ratio = round((target - close) / risk, 2)

        pct_stop = round(((close - stop_loss) / close) * 100, 2)
        pct_target = round(((target - close) / close) * 100, 2)
        vol_ma = float(last["VOL_MA21"]) if pd.notna(last["VOL_MA21"]) else 1.0
        vol_ratio = round(float(last["Volume"]) / vol_ma, 2) if vol_ma > 0 else 1.0

        score = 7.5
        if vol_ratio > 1.2:
            score += 1.0  # Volume de reversão
        if dist_52w_high_pct >= 25.0:
            score += 1.0  # Amplo upside desobstruído
        elif dist_52w_high_pct >= 15.0:
            score += 0.5
        if sma200 and close > sma200:
            score += 0.5  # Reversão dentro de macro tendência altista

        reason = (
            f"🎯 Retomada de Fundo (Pivô Concluído / Teste de Suporte):\n"
            f"• Conclusão de Fundo: Suporte testado e superação da EMA 9 (R$ {ema9:.2f})\n"
            f"• Pista Livre até Máxima: +{dist_52w_high_pct:.1f}% de folga até o topo de 52S (R$ {high_52w:.2f})\n"
            f"• Posição no Range Anual (52S): {range_52w_pct:.0f}% (Ativo com assimetria favorável e sem exaustão)\n"
            f"• Volume de Retomada: {vol_ratio:.1f}x da média diária\n"
            f"• Gestão de Risco: Alvo 2.5R em R$ {target:.2f} (+{pct_target:.1f}%) | Stop Técnico em R$ {stop_loss:.2f} (-{pct_stop:.1f}%)"
        )

        return {
            "strategy": "REVERSAL_PIVOT",
            "name": "Retomada de Fundo (Pivô Concluído)",
            "signal": "BUY",
            "entry_price": round(close, 2),
            "stop_loss": stop_loss,
            "take_profit": target,
            "trailing_stop": round(close - (atr * ATR_TRAILING_MULTIPLIER), 2),
            "rr_ratio": rr_ratio,
            "atr": round(atr, 2),
            "adtv_milhoes": round(adtv / 1e6, 2),
            "high_52w": round(high_52w, 2),
            "low_52w": round(low_52w, 2),
            "range_52w_pct": range_52w_pct,
            "dist_52w_high_pct": dist_52w_high_pct,
            "score": min(round(score, 1), 10.0),
            "reason": reason,
        }

    return None


def evaluate_bear_setup(df: pd.DataFrame) -> Optional[Dict[str, Any]]:
    """Detecta alinhamento de forte pressão vendedora / tendência de baixa estrutural.
    
    Usado para alertas de realização de lucros, cautela ou hedging da carteira.
    """
    if len(df) < 60:
        return None

    data = compute_indicators(df)
    last = data.iloc[-1]
    prev = data.iloc[-2]

    close = float(last["Close"])
    ema9 = float(last["EMA_9"])
    ema21 = float(last["EMA_21"])
    sma200 = float(last["SMA_200"]) if "SMA_200" in data.columns else None

    if pd.notna(ema9) and pd.notna(ema21):
        # Alinhamento baixista: Preço < EMA 9 < EMA 21
        is_bearish = close < ema9 and ema9 < ema21
        lost_recent_low = close < float(prev["Low"])

        if is_bearish and lost_recent_low:
            pct_below_ema9 = round(((ema9 - close) / ema9) * 100, 2)
            reason = (
                f"📉 Pressão Vendedora Detectada (Sinal de Baixa):\n"
                f"• Alinhamento Baixista: Cotação (R$ {close:.2f}) abaixo de EMA 9 e EMA 21\n"
                f"• Perda de Suporte: Fechamento violou a mínima do pregão anterior (R$ {prev['Low']:.2f})\n"
                f"• Orientação: Não comprar; se posicionado, avaliar encerramento preventivo ou proteção."
            )
            return {
                "strategy": "BEAR_PRESSURE",
                "name": "Pressão Vendedora (Sinal de Baixa)",
                "signal": "SELL_OR_HEDGE",
                "price": round(close, 2),
                "ema9": round(ema9, 2),
                "ema21": round(ema21, 2),
                "score": 8.0,
                "reason": reason,
            }

    return None
