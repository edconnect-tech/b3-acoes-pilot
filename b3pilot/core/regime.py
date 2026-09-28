"""Módulo de Classificação do Regime de Mercado via IBOVESPA (^BVSP).

Atua como Gatekeeper Institucional para autorizar ou suspender estratégias
conforme o macroambiente da B3.
"""

from typing import Dict, Any, Optional
import pandas as pd
import pandas_ta as ta

from b3pilot.data.b3_feed import fetch_ibov_data


def analyze_market_regime(df_ibov: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    """Classifica o regime atual do mercado brasileiro a partir do IBOVESPA.
    
    Regimes Possíveis:
      - BULL: IBOV > SMA 200 e EMA 9 >= EMA 21 (Tendência de Alta Confirmada).
      - CORRECTION: IBOV > SMA 200, mas EMA 9 < EMA 21 (Correção em Bull Market).
      - BEAR: IBOV < SMA 200 (Tendência de Baixa Macro).
      - PANIC: Queda intradiária > 2.5% ou sobrevenda extrema de colapso.
    """
    if df_ibov is None:
        df_ibov = fetch_ibov_data(period="1y")

    if df_ibov is None or len(df_ibov) < 50:
        # Fallback de segurança se o Yahoo Finance estiver temporariamente indisponível
        return {
            "status": "NEUTRAL",
            "name": "Neutro / Sem Feed Macro",
            "ibov_close": None,
            "ibov_change_pct": 0.0,
            "sma_200": None,
            "ema_9": None,
            "ema_21": None,
            "allow_momentum": True,
            "allow_ifr2": True,
            "allow_dividends": True,
            "allocation_multiplier": 1.0,
            "description": "Feed do IBOVESPA indisponível no momento; operando em modo neutro padrão.",
        }

    data = df_ibov.copy()
    data["SMA_200"] = ta.sma(data["Close"], length=min(200, len(data)))
    data["EMA_9"] = ta.ema(data["Close"], length=9)
    data["EMA_21"] = ta.ema(data["Close"], length=21)

    last = data.iloc[-1]
    prev = data.iloc[-2]

    close = float(last["Close"])
    prev_close = float(prev["Close"])
    change_pct = round(((close - prev_close) / prev_close) * 100, 2)

    sma200 = float(last["SMA_200"]) if pd.notna(last["SMA_200"]) else close
    ema9 = float(last["EMA_9"]) if pd.notna(last["EMA_9"]) else close
    ema21 = float(last["EMA_21"]) if pd.notna(last["EMA_21"]) else close

    # 1. Checagem de Pânico Sistêmico
    if change_pct <= -2.5:
        return {
            "status": "PANIC",
            "name": "PÂNICO / QUEDA SISTÊMICA",
            "ibov_close": round(close, 2),
            "ibov_change_pct": change_pct,
            "sma_200": round(sma200, 2),
            "ema_9": round(ema9, 2),
            "ema_21": round(ema21, 2),
            "allow_momentum": False,
            "allow_ifr2": False,
            "allow_dividends": False,
            "allocation_multiplier": 0.0,
            "description": f"Queda abrupta de {change_pct}% no IBOVESPA. Modo de preservação total de capital: compras bloqueadas.",
        }

    # 2. Tendência de Baixa Estrutural (Bear Market)
    if close < sma200:
        return {
            "status": "BEAR",
            "name": "BEAR MARKET (TENDÊNCIA DE BAIXA)",
            "ibov_close": round(close, 2),
            "ibov_change_pct": change_pct,
            "sma_200": round(sma200, 2),
            "ema_9": round(ema9, 2),
            "ema_21": round(ema21, 2),
            "allow_momentum": False,
            "allow_ifr2": True,  # Apenas sobrevenda extrema
            "allow_dividends": False,
            "allocation_multiplier": 0.50,  # Reduz exposição para 50%
            "description": f"IBOV (R$ {close:,.0f}) abaixo da SMA 200 (R$ {sma200:,.0f}). Compras de tendência suspensas; apenas repiques extremos autorizados com lote reduzido.",
        }

    # 3. Correção Técnica em Bull Market
    if ema9 < ema21:
        return {
            "status": "CORRECTION",
            "name": "CORREÇÃO TÉCNICA (PULLBACK)",
            "ibov_close": round(close, 2),
            "ibov_change_pct": change_pct,
            "sma_200": round(sma200, 2),
            "ema_9": round(ema9, 2),
            "ema_21": round(ema21, 2),
            "allow_momentum": False,
            "allow_ifr2": True,
            "allow_dividends": True,
            "allocation_multiplier": 0.75,
            "description": f"IBOV sustentado acima da SMA 200, porém com médias curtas cruzadas para baixo. Cenário ideal para reversão à média (IFR2).",
        }

    # 4. Bull Market Pleno
    return {
        "status": "BULL",
        "name": "BULL MARKET (TENDÊNCIA DE ALTA)",
        "ibov_close": round(close, 2),
        "ibov_change_pct": change_pct,
        "sma_200": round(sma200, 2),
        "ema_9": round(ema9, 2),
        "ema_21": round(ema21, 2),
        "allow_momentum": True,
        "allow_ifr2": True,
        "allow_dividends": True,
        "allocation_multiplier": 1.0,
        "description": f"IBOV altista acima da SMA 200 e com médias alinhadas (EMA 9 > EMA 21). Todos os setups operando com 100% de alocação.",
    }
