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
            # Stop Catastrófico (10% de folga) para preservar o Win Rate estatístico do setup
            stop_loss = round(close * (1.0 - IFR2_CATASTROPHIC_STOP_PERCENT), 2)
            risk = close - stop_loss
            reward = target - close
            rr_ratio = round(reward / risk, 2) if risk > 0 else 1.0

            pct_stop = round(((close - stop_loss) / close) * 100, 2)
            pct_target = round(((target - close) / close) * 100, 2)
            pct_sma200 = round(((close - sma200) / sma200) * 100, 2)
            vol_ma = float(last["VOL_MA21"]) if pd.notna(last["VOL_MA21"]) else 1.0
            vol_ratio = round(float(last["Volume"]) / vol_ma, 2) if vol_ma > 0 else 1.0

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

            # Pontuação de Confluência
            score = 7.0
            if vol_ratio > 1.3:
                score += 1.5  # Retomada com volume expressivo
            if (ema9 - ema21) / ema21 > 0.02:
                score += 1.0  # Divergência e aceleração de médias
            if adtv >= 20_000_000:
                score += 0.5

            reason = (
                f"🚀 Seguidor de Tendência (Momentum com Pullback):\n"
                f"• Alinhamento Altista: Preço (R$ {close:.2f}) > EMA 9 > EMA 21 > SMA 200\n"
                f"• Retração Saudável: Testou suporte de médias e retomou força compradora\n"
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
