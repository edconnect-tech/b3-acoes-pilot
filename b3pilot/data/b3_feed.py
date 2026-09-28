"""Módulo de download e cache de cotações diárias da B3 via yfinance."""

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional
import pandas as pd
import yfinance as yf

from b3pilot.config import PROJECT_ROOT

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


def fetch_ticker_data(
    ticker: str,
    period: str = "1y",
    interval: str = "1d",
    use_cache: bool = True,
    max_cache_age_hours: int = 4,
) -> Optional[pd.DataFrame]:
    """Baixa o histórico OHLCV de um ativo com suporte a cache local em parquet/csv."""
    clean_ticker = get_clean_ticker(ticker)
    cache_file = CACHE_DIR / f"{clean_ticker}_{interval}.parquet"

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
        data = yf.download(
            clean_ticker,
            period=period,
            interval=interval,
            progress=False,
            auto_adjust=True,
        )

        if data.empty or len(data) < 20:
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
    except Exception as e:
        print(f"Erro ao baixar {clean_ticker}: {e}")
        return None


def fetch_latest_price(ticker: str) -> Optional[float]:
    """Retorna o último preço de fechamento/negociação de um ativo."""
    df = fetch_ticker_data(ticker, period="5d")
    if df is not None and not df.empty:
        return float(df["Close"].iloc[-1])
    return None
