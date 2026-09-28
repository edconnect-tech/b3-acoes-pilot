"""Estratégias de Swing Trade: IFR2 (Reversão à Média) e Seguidor de Tendência (Momentum)."""

from typing import Dict, Any, Optional
import pandas as pd
import pandas_ta as ta

from b3pilot.config import (
    IFR2_OVERSOLD_THRESHOLD,
    IFR2_TREND_SMA,
    TREND_EMA_FAST,
    TREND_EMA_SLOW,
    ATR_PERIOD,
    ATR_TRAILING_MULTIPLIER,
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

    # Volume Médio 21 períodos
    data["VOL_MA21"] = data["Volume"].rolling(21).mean()

    return data


def evaluate_ifr2_setup(df: pd.DataFrame) -> Optional[Dict[str, Any]]:
    """Avalia se o ativo armou setup IFR2 (Reversão à Média de Larry Connors)."""
    if len(df) < 210:
        return None

    data = compute_indicators(df)
    last = data.iloc[-1]

    close = float(last["Close"])
    sma200 = float(last["SMA_200"])
    rsi2 = float(last["RSI_2"])
    atr = float(last["ATR_14"]) if pd.notna(last["ATR_14"]) else (close * 0.03)
    target = float(last["HIGH_2D"]) if pd.notna(last["HIGH_2D"]) else (close * 1.04)

    # Regras do setup:
    # 1. Tendência primária de alta: Fechamento acima da SMA 200
    # 2. Sobrevenda aguda: IFR(2) abaixo do patamar configurado (ex: 10 ou 15)
    if pd.notna(rsi2) and pd.notna(sma200):
        if close > sma200 and rsi2 <= IFR2_OVERSOLD_THRESHOLD:
            # Stop de proteção inegociável (2x ATR)
            stop_loss = round(close - (atr * ATR_TRAILING_MULTIPLIER), 2)
            risk = close - stop_loss
            reward = target - close
            rr_ratio = round(reward / risk, 2) if risk > 0 else 1.0

            pct_stop = round(((close - stop_loss) / close) * 100, 2)
            pct_target = round(((target - close) / close) * 100, 2)
            pct_sma200 = round(((close - sma200) / sma200) * 100, 2)
            vol_ma = float(last["VOL_MA21"]) if pd.notna(last["VOL_MA21"]) else 1.0
            vol_ratio = round(float(last["Volume"]) / vol_ma, 2) if vol_ma > 0 else 1.0

            # Score de Confluência (0 a 10)
            score = 7.0
            if rsi2 < 5.0:
                score += 1.5
            elif rsi2 < 10.0:
                score += 1.0

            if vol_ratio > 1.2:
                score += 1.0  # Volume de capitulação/exaustão

            reason = (
                f"🟢 Reversão à Média (IFR2):\n"
                f"• IFR(2) em {rsi2:.1f} (Sobrevenda extrema em tendência de alta)\n"
                f"• Tendência Primária: +{pct_sma200:.1f}% acima da SMA 200 (R$ {sma200:.2f})\n"
                f"• Volume Recente: {vol_ratio:.1f}x da média de 21 pregões\n"
                f"• Alvo: R$ {target:.2f} (+{pct_target:.1f}%) | Stop: R$ {stop_loss:.2f} (-{pct_stop:.1f}%)"
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
                "score": min(round(score, 1), 10.0),
                "reason": reason,
            }

    return None


def evaluate_trend_setup(df: pd.DataFrame) -> Optional[Dict[str, Any]]:
    """Avalia se o ativo armou setup Seguidor de Tendência / Momentum (Larry Williams / Médias)."""
    if len(df) < 210:
        return None

    data = compute_indicators(df)
    last = data.iloc[-1]
    prev = data.iloc[-2]

    close = float(last["Close"])
    ema9 = float(last["EMA_9"])
    prev_ema9 = float(prev["EMA_9"])
    ema21 = float(last["EMA_21"])
    sma200 = float(last["SMA_200"])
    atr = float(last["ATR_14"]) if pd.notna(last["ATR_14"]) else (close * 0.03)

    if pd.notna(ema9) and pd.notna(ema21) and pd.notna(sma200):
        # 1. Alinhamento de tendência: Preço > EMA 9 > EMA 21 > SMA 200
        # 2. Inclinação positiva da média móvel rápida
        is_uptrend = close > ema9 and ema9 > ema21 and ema21 > sma200 and ema9 > prev_ema9

        # Gatilho de rompimento ou pullback na EMA9
        crossed_up = prev["Close"] <= prev["EMA_9"] and close > ema9
        breakout = close > prev["High"]

        if is_uptrend and (crossed_up or breakout):
            stop_loss = round(min(float(last["Low"]), float(prev["Low"])) - (atr * 0.5), 2)
            risk = close - stop_loss
            if risk <= 0:
                risk = atr * 1.5
                stop_loss = round(close - risk, 2)

            # Alvo com assimetria de 2.5R
            target = round(close + (risk * 2.5), 2)
            rr_ratio = round((target - close) / risk, 2)

            pct_stop = round(((close - stop_loss) / close) * 100, 2)
            pct_target = round(((target - close) / close) * 100, 2)
            vol_ma = float(last["VOL_MA21"]) if pd.notna(last["VOL_MA21"]) else 1.0
            vol_ratio = round(float(last["Volume"]) / vol_ma, 2) if vol_ma > 0 else 1.0

            # Score de Confluência
            score = 7.0
            if vol_ratio > 1.3:
                score += 1.5  # Volume expressivo
            if (ema9 - ema21) / ema21 > 0.02:
                score += 1.0  # Boa divergência das médias

            reason = (
                f"🚀 Seguidor de Tendência (Momentum):\n"
                f"• Alinhamento Altista: Preço > EMA 9 > EMA 21 > SMA 200\n"
                f"• Inclinação da Média Rápida: EMA 9 ascendente em R$ {ema9:.2f}\n"
                f"• Volume Financeiro: {vol_ratio:.1f}x da média de 21 dias\n"
                f"• Assimetria Projetada: Alvo 2.5R em R$ {target:.2f} (+{pct_target:.1f}%) | Stop em R$ {stop_loss:.2f} (-{pct_stop:.1f}%)"
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
                "score": min(round(score, 1), 10.0),
                "reason": reason,
            }

    return None
