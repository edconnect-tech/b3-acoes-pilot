"""Rotina Matinal Automática (09:55 BRT - Horário de Brasília) - Avaliação de Saídas, Oportunidades e Regime Macro."""

from datetime import datetime
from typing import Dict, Any, List
from rich.console import Console

from b3pilot.ledger.db import get_db_session, AlertLog, init_db, naive_utc_now
from b3pilot.core.exits import evaluate_open_positions_exits
from b3pilot.core.screener import run_screener
from b3pilot.core.regime import analyze_market_regime
from b3pilot.alerts.notifier import dispatch_alert

console = Console()


def run_morning_routine(dry_run: bool = False) -> Dict[str, Any]:
    """Executa a rotina consolidada das 09:55 BRT (Horário de Brasília) antes da abertura do pregão da B3."""
    init_db()
    session = get_db_session()

    console.print("[bold cyan]Iniciando Rotina Matinal do B3 Ações Pilot...[/bold cyan]")

    # 0. Avaliação do Regime de Mercado Macro (IBOVESPA)
    regime = analyze_market_regime()
    console.print(f"[bold yellow]Regime de Mercado IBOVESPA:[/bold yellow] [bold]{regime['name']}[/bold]")
    console.print(f"[dim]{regime['description']}[/dim]")

    alerts_sent = 0

    if regime["status"] == "PANIC":
        panic_title = "🚨 ALERTA MACRO: IBOVESPA EM PÂNICO"
        panic_msg = (
            f"• *Status:* {regime['name']}\n"
            f"• *Variação IBOV:* {regime['ibov_change_pct']}%\n"
            f"• *Diretriz Institucional:* Novas compras de Swing Trade 100% SUSPENSAS hoje para proteção de capital.\n"
            f"• *Ação:* Monitorar apenas encerramento de posições ativas."
        )
        if not dry_run:
            dispatch_alert(panic_title, "Preservação de Capital", panic_msg)
            alerts_sent += 1

    # 1. Avalia ordens de VENDA compulsórias nas posições em custódia
    console.print("[yellow]Verificando posições em aberto para saídas...[/yellow]")
    exit_signals = evaluate_open_positions_exits(session)

    # DISPARO COMPULSÓRIO DE VENDAS (100% Notificadas)
    if exit_signals:
        for exit_item in exit_signals:
            title = f"🚨 ALERTA DE VENDA: {exit_item['ticker']}"
            subtitle = f"Gatilho: {exit_item['type']} (PnL: {exit_item['pnl_pct']:+.2f}%)"
            msg = (
                f"• *Ativo:* `{exit_item['ticker']}`\n"
                f"• *Quantidade:* {exit_item['quantity']} ações\n"
                f"• *Preço Atual:* R$ {exit_item['price']:.2f}\n"
                f"• *Preço de Entrada:* R$ {exit_item['entry_price']:.2f}\n"
                f"• *Motivo:* {exit_item['reason']}\n\n"
                f"⚠️ *Ação Recomendada:* Enviar ordem de VENDA na abertura da B3 às 10:00."
            )

            if not dry_run:
                dispatch_alert(title, subtitle, msg)
                log = AlertLog(
                    timestamp=naive_utc_now(),
                    ticker=exit_item["ticker"],
                    alert_type=exit_item["type"],
                    message=msg,
                    channels="TELEGRAM+MACOS",
                )
                session.add(log)
            alerts_sent += 1
    else:
        console.print("[green]✓ Nenhuma posição em custódia atingiu gatilho de saída hoje.[/green]")

    # 2. Varre o mercado buscando compras de ALTA CONVICÇÃO (Score >= 8.0)
    buy_signals = []
    if regime["status"] != "PANIC":
        console.print("[yellow]Buscando oportunidades de compra com alta confluência...[/yellow]")
        buy_signals = run_screener(high_conviction_only=True, show_progress=False)

    # DISPARO DE COMPRAS MUITO VANTAJOSAS (Filtradas com Position Sizing)
    if buy_signals:
        for buy_item in buy_signals[:3]:  # Top 3
            title = f"⭐ COMPRA VANTAJOSA: {buy_item['ticker']}"
            subtitle = f"{buy_item['name']} (Score: {buy_item['score']}/10)"
            suggested_shares = buy_item.get("suggested_shares", 100)
            suggested_capital = buy_item.get("suggested_capital", buy_item["entry_price"] * 100)
            actual_risk_pct = buy_item.get("actual_risk_pct", 2.0)

            msg = (
                f"• *Ativo:* `{buy_item['ticker']}` ({buy_item['name']})\n"
                f"• *Regime Macro:* {buy_item.get('regime_name', regime['name'])}\n"
                f"• *Entrada Ref.:* R$ {buy_item['entry_price']:.2f}\n"
                f"• *Stop Loss:* R$ {buy_item['stop_loss']:.2f}\n"
                f"• *Take Profit:* R$ {buy_item['take_profit']:.2f} (R/R: {buy_item.get('rr_ratio', 'N/A')}x)\n"
                f"• *Dimensionamento Sugerido:* {suggested_shares} ações (~R$ {suggested_capital:,.2f} | Risco: {actual_risk_pct}%)\n"
                f"• *Liquidez Real:* R$ {buy_item.get('adtv_milhoes', 'N/A')}M/dia\n"
                f"• *Tese Técnica:*\n{buy_item['reason']}\n\n"
                f"🛡️ *Guardrail de Gap:* Se abrir com gap > +1.0% ou afastar do stop, NÃO perseguir o preço."
            )

            if not dry_run:
                dispatch_alert(title, subtitle, msg)
                log = AlertLog(
                    timestamp=naive_utc_now(),
                    ticker=buy_item["ticker"],
                    alert_type="BUY",
                    message=msg,
                    channels="TELEGRAM+MACOS",
                )
                session.add(log)
            alerts_sent += 1
    else:
        console.print("[dim]Nenhuma compra de alta convicção autorizada pelo regime hoje.[/dim]")

    if not dry_run:
        session.commit()
    session.close()

    console.print(f"[bold green]✓ Rotina matinal concluída. Total de alertas disparados: {alerts_sent}[/bold green]")
    return {
        "regime": regime,
        "exit_signals": exit_signals,
        "buy_signals": buy_signals,
        "alerts_sent": alerts_sent,
    }
