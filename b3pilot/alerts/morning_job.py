"""Rotina Matinal Automática (09:15 BRT) - Avaliação de Saídas e Oportunidades."""

from datetime import datetime
from typing import Dict, Any, List
from rich.console import Console

from b3pilot.ledger.db import get_db_session, AlertLog, init_db
from b3pilot.core.exits import evaluate_open_positions_exits
from b3pilot.core.screener import run_screener
from b3pilot.alerts.notifier import dispatch_alert, send_telegram_message, send_macos_notification

console = Console()


def run_morning_routine(dry_run: bool = False) -> Dict[str, Any]:
    """Executa a rotina consolidada das 09:15 BRT antes da abertura do pregão da B3."""
    init_db()
    session = get_db_session()

    console.print("[bold cyan]Iniciando Rotina Matinal do B3 Ações Pilot...[/bold cyan]")

    # 1. Avalia ordens de VENDA compulsórias nas posições em custódia
    console.print("[yellow]Verificando posições em aberto para saídas...[/yellow]")
    exit_signals = evaluate_open_positions_exits(session)

    # 2. Varre o mercado buscando compras de ALTA CONVICÇÃO (Score >= 8.0)
    console.print("[yellow]Buscando oportunidades de compra com alta confluência...[/yellow]")
    buy_signals = run_screener(high_conviction_only=True, show_progress=False)

    alerts_sent = 0

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
                # Grava no banco
                log = AlertLog(
                    timestamp=datetime.utcnow(),
                    ticker=exit_item["ticker"],
                    alert_type=exit_item["type"],
                    message=msg,
                    channels="TELEGRAM+MACOS",
                )
                session.add(log)
            alerts_sent += 1
    else:
        console.print("[green]✓ Nenhuma posição em custódia atingiu gatilho de saída hoje.[/green]")

    # DISPARO DE COMPRAS MUITO VANTAJOSAS (Filtradas)
    if buy_signals:
        for buy_item in buy_signals[:3]:  # Limita aos top 3 para evitar excesso
            title = f"⭐ OPORTUNIDADE DE COMPRA: {buy_item['ticker']}"
            subtitle = f"Estratégia: {buy_item['name']} (Score: {buy_item['score']}/10)"
            msg = (
                f"• *Ativo:* `{buy_item['ticker']}`\n"
                f"• *Estratégia:* {buy_item['name']}\n"
                f"• *Entrada Ref.:* R$ {buy_item['entry_price']:.2f}\n"
                f"• *Stop Loss:* R$ {buy_item['stop_loss']:.2f}\n"
                f"• *Take Profit:* R$ {buy_item['take_profit']:.2f}\n"
                f"• *Relação R/R:* {buy_item.get('rr_ratio', 'N/A')}x\n"
                f"• *Análise:* {buy_item['reason']}\n\n"
                f"💡 *Ação:* Avaliar entrada nos primeiros 30 min de pregão."
            )

            if not dry_run:
                dispatch_alert(title, subtitle, msg)
                log = AlertLog(
                    timestamp=datetime.utcnow(),
                    ticker=buy_item["ticker"],
                    alert_type="BUY",
                    message=msg,
                    channels="TELEGRAM+MACOS",
                )
                session.add(log)
            alerts_sent += 1
    else:
        console.print("[dim]Nenhuma compra de alta convicção encontrada hoje dentro dos critérios restritivos.[/dim]")

    if not dry_run:
        session.commit()
    session.close()

    console.print(f"[bold green]✓ Rotina matinal concluída. Total de alertas disparados: {alerts_sent}[/bold green]")
    return {
        "exit_signals": exit_signals,
        "buy_signals": buy_signals,
        "alerts_sent": alerts_sent,
    }
