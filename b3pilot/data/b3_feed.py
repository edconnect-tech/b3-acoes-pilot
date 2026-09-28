"""Módulo de download, cache e análise multitemporal de cotações B3 via yfinance."""

import os
import sys
import logging
import contextlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Any
import pandas as pd
import yfinance as yf

from b3pilot.config import PROJECT_ROOT

# Silencia mensagens de erro/aviso ruidosas da biblioteca yfinance
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

CACHE_DIR = PROJECT_ROOT / ".cache_data"
CACHE_DIR.mkdir(exist_ok=True)


def get_clean_ticker(ticker: str) -> str:
    """Garante que o ticker termine com .SA para o Yahoo Finance."""
    ticker = ticker.strip().upper()
    if not ticker.endswith(".SA"):
        return f"{ticker}.SA"
    return ticker


def get_base_ticker(ticker: str) -> str:
    """Remove o .SA para exibição limpa."""
    ticker = ticker.strip().upper()
    if ticker.endswith(".SA"):
        return ticker[:-3]
    return ticker


def get_statusinvest_url(ticker: str) -> str:
    """Retorna o link direto para a ficha fundamentalista e dados da empresa no StatusInvest."""
    base = get_base_ticker(ticker).lower()
    return f"https://statusinvest.com.br/acoes/{base}"


def get_tradingview_url(ticker: str) -> str:
    """Retorna o link direto para o gráfico avançado no TradingView Brasil."""
    base = get_base_ticker(ticker).upper()
    return f"https://br.tradingview.com/symbols/BMFBOVESPA-{base}/"


def fetch_ticker_data(
    ticker: str,
    period: str = "2y",
    interval: str = "1d",
    use_cache: bool = True,
    max_cache_age_hours: int = 4,
) -> Optional[pd.DataFrame]:
    """Baixa o histórico OHLCV de um ativo com suporte a cache local em parquet."""
    clean_ticker = get_clean_ticker(ticker)
    cache_file = CACHE_DIR / f"{clean_ticker}_{period}_{interval}.parquet"

    # Checa se o cache é recente
    if use_cache and cache_file.exists():
        file_mod_time = datetime.fromtimestamp(cache_file.stat().st_mtime)
        if datetime.now() - file_mod_time < timedelta(hours=max_cache_age_hours):
            try:
                df = pd.read_parquet(cache_file)
                if not df.empty:
                    return df
            except Exception:
                pass

    try:
        # Suprime prints ruidosos de 404/delisted do yfinance no stderr
        with open(os.devnull, "w") as devnull, contextlib.redirect_stderr(devnull):
            data = yf.download(
                clean_ticker,
                period=period,
                interval=interval,
                progress=False,
                auto_adjust=True,
            )

        if data is None or data.empty or len(data) < 15:
            return None

        # Corrige colunas se vierem com MultiIndex do yfinance
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = [col[0] for col in data.columns]

        # Normaliza nomes de colunas
        data.index.name = "Date"
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            if col not in data.columns:
                return None

        # Salva em cache
        try:
            data.to_parquet(cache_file)
        except Exception:
            pass

        return data
    except Exception:
        return None


def fetch_latest_price(ticker: str) -> Optional[float]:
    """Retorna o último preço de fechamento/negociação de um ativo."""
    df = fetch_ticker_data(ticker, period="5d")
    if df is not None and not df.empty:
        return float(df["Close"].iloc[-1])
    return None


def compute_multi_timeframe_variations(ticker: str) -> Dict[str, Optional[float]]:
    """Calcula as variações percentuais em múltiplos horizontes de tempo:
    
    1D (Diário), 1S (Semanal), 1M (Mensal), 3M (Trimestral),
    6M (Semestral), 1A (Anual), 5A (5 Anos) e 10A (10 Anos).
    """
    clean_ticker = get_clean_ticker(ticker)
    df = fetch_ticker_data(clean_ticker, period="10y", use_cache=True, max_cache_age_hours=12)

    if df is None or len(df) < 2:
        return {
            "1D": None, "1S": None, "1M": None, "3M": None,
            "6M": None, "1A": None, "5A": None, "10A": None,
        }

    close = df["Close"].dropna()
    current = float(close.iloc[-1])
    total_bars = len(close)

    def calc_pct(bars_ago: int) -> Optional[float]:
        if total_bars > bars_ago:
            past_val = float(close.iloc[-(bars_ago + 1)])
            if past_val > 0:
                return round(((current - past_val) / past_val) * 100, 2)
        elif total_bars > 1 and bars_ago >= total_bars:
            # Retorno desde o início da série se for menor que o período
            initial_val = float(close.iloc[0])
            if initial_val > 0:
                return round(((current - initial_val) / initial_val) * 100, 2)
        return None

    return {
        "1D": calc_pct(1),        # 1 pregão
        "1S": calc_pct(5),        # 1 semana (~5 pregões)
        "1M": calc_pct(21),       # 1 mês (~21 pregões)
        "3M": calc_pct(63),       # 1 trimestre (~63 pregões)
        "6M": calc_pct(126),      # 1 semestre (~126 pregões)
        "1A": calc_pct(252),      # 1 ano (~252 pregões)
        "5A": calc_pct(1260),     # 5 anos (~1260 pregões)
        "10A": calc_pct(2520),    # 10 anos (~2520 pregões)
    }
