#!/usr/bin/env python3
"""Popula o Laboratório Simulado (Paper Trading) com carteira fictícia segura para testes e prints.

Garantia Zero Trust:
- Opera exclusivamente com `is_simulated=True`.
- Nunca altera, apaga ou consulta posições reais (`is_simulated=False`) nem registros fiscais (`MonthlyTaxRecord`).
"""

from __future__ import annotations

import argparse
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Garante execução direta via `python scripts/seed_demo_portfolio.py`
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from b3pilot.data.b3_feed import fetch_latest_price
from b3pilot.data.sectors import get_asset_sector_profile
from b3pilot.ledger.db import Base, Position, Transaction, get_db_session, init_db, naive_utc_now
from b3pilot.ledger.portfolio import execute_buy, execute_sell

FALLBACK_PRICES: Dict[str, float] = {
    "WEGE3": 52.00,
    "ITUB4": 35.00,
    "PETR4": 38.00,
    "TAEE11": 35.50,
    "TOTS3": 32.00,
    "VALE3": 62.00,
    "LREN3": 18.00,
}

OPEN_POSITIONS_SPEC: List[Dict[str, Any]] = [
    {
        "ticker": "WEGE3",
        "quantity": 80,
        "entry_mult": 0.940,
        "stop_mult": 0.950,
        "tp1_mult": 1.070,
        "new_stop_mult": 1.015,
        "target_mult": 1.140,
        "strategy": "TREND",
        "days_ago": 12,
        "notes": "[DEMO] Pullback na EMA9 com tendência primária de alta",
    },
    {
        "ticker": "ITUB4",
        "quantity": 120,
        "entry_mult": 0.955,
        "stop_mult": 0.940,
        "tp1_mult": None,
        "new_stop_mult": None,
        "target_mult": 1.080,
        "strategy": "IFR2",
        "days_ago": 4,
        "notes": "[DEMO] Reversão à média IFR(2) sobrevendido acima da SMA200",
    },
    {
        "ticker": "PETR4",
        "quantity": 110,
        "entry_mult": 0.948,
        "stop_mult": 0.940,
        "tp1_mult": 1.060,
        "new_stop_mult": 1.010,
        "target_mult": 1.120,
        "strategy": "DIVIDEND_COM",
        "days_ago": 9,
        "notes": "[DEMO] Captura pré-Data COM com alinhamento comprador",
    },
    {
        "ticker": "TAEE11",
        "quantity": 110,
        "entry_mult": 0.975,
        "stop_mult": 0.950,
        "tp1_mult": None,
        "new_stop_mult": None,
        "target_mult": 1.100,
        "strategy": "DIVIDEND_COM",
        "days_ago": 6,
        "notes": "[DEMO] Utilidade pública defensiva pré-proventos",
    },
    {
        "ticker": "TOTS3",
        "quantity": 120,
        "entry_mult": 1.018,
        "stop_mult": 0.940,
        "tp1_mult": None,
        "new_stop_mult": None,
        "target_mult": 1.150,
        "strategy": "REVERSAL_PIVOT",
        "days_ago": 3,
        "notes": "[DEMO] Retomada de fundo com stop técnico posicionado",
    },
]


def _resolve_reference_price(ticker: str, use_live_prices: bool) -> float:
    """Obtém cotação atual via feed ou retorna o preço estático de referência."""
    if use_live_prices:
        try:
            live = fetch_latest_price(ticker)
            if live and live > 0:
                return float(live)
        except Exception:
            pass
    return FALLBACK_PRICES[ticker]


def seed_demo_portfolio(
    session: Session,
    reset: bool = False,
    use_live_prices: bool = True,
) -> Dict[str, Any]:
    """Popula 5 posições simuladas descorrelacionadas e 2 trades simulados encerrados."""
    existing_count = session.query(Position).filter_by(is_simulated=True).count()
    if existing_count > 0 and not reset:
        return {
            "skipped": True,
            "reason": (
                f"Já existem {existing_count} posições simuladas no banco. "
                "Execute novamente com --reset para recriar a carteira fictícia sem afetar a carteira real."
            ),
            "open_positions": existing_count,
            "closed_trades": 0,
            "tickers": [],
        }

    if reset:
        session.query(Position).filter_by(is_simulated=True).delete()
        session.query(Transaction).filter_by(is_simulated=True).delete()
        session.commit()

    now = naive_utc_now()
    created_summary: List[Dict[str, Any]] = []
    sectors: List[str] = []
    clusters: List[str] = []

    for spec in OPEN_POSITIONS_SPEC:
        ticker = spec["ticker"]
        ref_price = _resolve_reference_price(ticker, use_live_prices=use_live_prices)
        entry_price = round(ref_price * spec["entry_mult"], 2)
        stop_loss = round(entry_price * spec["stop_mult"], 2)
        take_profit = round(entry_price * spec["target_mult"], 2)
        partial_target = round(entry_price * spec["tp1_mult"], 2) if spec["tp1_mult"] else None
        new_stop_after_partial = (
            round(entry_price * spec["new_stop_mult"], 2) if spec["new_stop_mult"] else None
        )

        pos = execute_buy(
            session=session,
            ticker=ticker,
            quantity=spec["quantity"],
            price=entry_price,
            fees=1.50,
            stop_loss=stop_loss,
            take_profit=take_profit,
            partial_target=partial_target,
            new_stop_after_partial=new_stop_after_partial,
            strategy=spec["strategy"],
            notes=spec["notes"],
            date=now - timedelta(days=spec["days_ago"]),
            is_simulated=True,
        )

        profile = get_asset_sector_profile(ticker)
        sectors.append(profile.get("sector", "Outros"))
        clusters.extend(profile.get("clusters", []))
        created_summary.append(
            {
                "ticker": pos.ticker,
                "sector": profile.get("sector", "Outros"),
                "clusters": profile.get("clusters", []),
                "quantity": pos.quantity,
                "average_price": pos.average_price,
                "ref_price": ref_price,
                "stop_loss": pos.stop_loss,
                "take_profit": pos.take_profit,
                "strategy": pos.strategy,
            }
        )

    # 2 trades simulados encerrados para popular "Histórico & Performance"
    vale_ref = _resolve_reference_price("VALE3", use_live_prices=use_live_prices)
    vale_buy_price = round(vale_ref * 0.9225, 2)
    vale_sell_price = round(vale_buy_price * 1.084, 2)
    execute_buy(
        session=session,
        ticker="VALE3",
        quantity=100,
        price=vale_buy_price,
        fees=1.50,
        stop_loss=round(vale_buy_price * 0.94, 2),
        take_profit=round(vale_buy_price * 1.12, 2),
        strategy="TREND",
        notes="[DEMO] Swing trade vencedor encerrado no alvo",
        date=now - timedelta(days=25),
        is_simulated=True,
    )
    vale_sell = execute_sell(
        session=session,
        ticker="VALE3",
        quantity=100,
        price=vale_sell_price,
        fees=1.50,
        notes="[DEMO] Realização de lucro (+8,4%)",
        date=now - timedelta(days=14),
        is_simulated=True,
    )

    lren_ref = _resolve_reference_price("LREN3", use_live_prices=use_live_prices)
    lren_buy_price = round(lren_ref, 2)
    lren_sell_price = round(lren_buy_price * 0.958, 2)
    execute_buy(
        session=session,
        ticker="LREN3",
        quantity=150,
        price=lren_buy_price,
        fees=1.50,
        stop_loss=lren_sell_price,
        take_profit=round(lren_buy_price * 1.10, 2),
        strategy="IFR2",
        notes="[DEMO] Entrada IFR2 com controle estrito de risco",
        date=now - timedelta(days=20),
        is_simulated=True,
    )
    lren_sell = execute_sell(
        session=session,
        ticker="LREN3",
        quantity=150,
        price=lren_sell_price,
        fees=1.50,
        notes="[DEMO] Saída disciplinada no Stop Loss (-4,2%)",
        date=now - timedelta(days=10),
        is_simulated=True,
    )

    return {
        "skipped": False,
        "reset_applied": reset,
        "open_positions": len(created_summary),
        "closed_trades": 2,
        "tickers": [item["ticker"] for item in created_summary],
        "sectors": sectors,
        "clusters": clusters,
        "positions": created_summary,
        "closed_summary": [vale_sell, lren_sell],
    }


def _open_session_for_path(db_path: Optional[str]) -> Session:
    """Abre sessão no banco padrão do projeto ou em um SQLite customizado."""
    if not db_path:
        init_db()
        return get_db_session()

    resolved = Path(db_path).expanduser().resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    custom_engine = create_engine(f"sqlite:///{resolved}", echo=False)
    Base.metadata.create_all(bind=custom_engine)
    SessionCls = sessionmaker(autocommit=False, autoflush=False, bind=custom_engine)
    return SessionCls()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Popula o Laboratório Simulado (Paper Trading) do B3 Ações Pilot para demonstração e prints."
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Remove apenas posições/transações simuladas anteriores antes de recriar a carteira demo.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Usa preços estáticos de referência sem consultar cotações online no Yahoo Finance.",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Caminho alternativo de banco SQLite isolado (padrão: portfolio.db do projeto).",
    )
    args = parser.parse_args()

    session = _open_session_for_path(args.db_path)
    try:
        result = seed_demo_portfolio(
            session=session,
            reset=args.reset,
            use_live_prices=not args.offline,
        )

        if result["skipped"]:
            print(f"⚠️  {result['reason']}")
            return 0

        print("\n=== LABORATÓRIO SIMULADO (PAPER TRADING) POPULADO COM SUCESSO ===")
        print(
            f"Posições abertas (is_simulated=True): {result['open_positions']} | "
            f"Trades encerrados: {result['closed_trades']}\n"
        )
        for pos in result["positions"]:
            print(
                f"  • {pos['ticker']:<6} | {pos['sector']:<18} | {pos['quantity']:>3} un "
                f"@ R$ {pos['average_price']:>6.2f} (Ref: R$ {pos['ref_price']:.2f}) | "
                f"Stop: R$ {pos['stop_loss']:.2f} | Alvo: R$ {pos['take_profit']:.2f} | {pos['strategy']}"
            )
        print("\nTrades encerrados no histórico simulado:")
        for closed in result["closed_summary"]:
            print(
                f"  • {closed['ticker']:<6} | {closed['quantity_sold']:>3} un @ R$ {closed['sale_price']:.2f} | "
                f"PnL: R$ {closed['realized_pnl']:+,.2f} ({closed['realized_pnl_pct']:+.2f}%)"
            )
        print(
            "\n🛡️ Custódia real (is_simulated=False) e apuração DARF preservadas intactas."
            "\n💡 Rode `b3pilot web` e selecione '🧪 Laboratório Simulado (Paper Trading)' para capturar prints seguros.\n"
        )
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
