"""CLI principal do B3 Ações Pilot (Typer + Rich)."""

import os
import sys
import subprocess
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from b3pilot.ledger.db import init_db, get_db_session
from b3pilot.ledger.portfolio import execute_buy, execute_sell, get_portfolio_summary
from b3pilot.ledger.taxes import get_current_tax_summary
from b3pilot.core.screener import run_screener
from b3pilot.core.regime import analyze_market_regime
from b3pilot.core.risk import audit_option_spread
from b3pilot.data.dividends_feed import scan_upcoming_dividends
from b3pilot.data.universe import get_universe
from b3pilot.alerts.morning_job import run_morning_routine
from b3pilot.alerts.notifier import send_telegram_message, send_macos_notification
from b3pilot.config import PROJECT_ROOT

app = typer.Typer(help="B3 Ações Pilot - Assistente de Swing Trade & Proventos Nativo para Antigravity agy")
console = Console()


@app.command()
def status():
    """Exibe o estado atual da carteira, posições em aberto e rentabilidade a mercado."""
    init_db()
    session = get_db_session()
    summary = get_portfolio_summary(session)

    console.print("\n[bold cyan]=== CUSTÓDIA B3 AÇÕES PILOT ===[/bold cyan]\n")

    pnl_color = "green" if summary["total_unrealized_pnl"] >= 0 else "red"
    console.print(
        f"Investido: [bold]R$ {summary['total_invested']:,.2f}[/bold] | "
        f"Valor a Mercado: [bold]R$ {summary['current_market_value']:,.2f}[/bold] | "
        f"PnL: [{pnl_color}]R$ {summary['total_unrealized_pnl']:,.2f} ({summary['total_unrealized_pnl_pct']:+.2f}%)[/{pnl_color}]"
    )

    if not summary["positions"]:
        console.print("\n[dim]Nenhuma ação em custódia no momento. Use 'b3pilot buy' para registrar compras.[/dim]\n")
        session.close()
        return

    table = Table(title="Posições Ativas", show_header=True, header_style="bold magenta")
    table.add_column("Ticker", style="bold")
    table.add_column("Qtd", justify="right")
    table.add_column("PM (R$)", justify="right")
    table.add_column("Atual (R$)", justify="right")
    table.add_column("PnL (R$)", justify="right")
    table.add_column("PnL (%)", justify="right")
    table.add_column("Stop Loss", justify="right")
    table.add_column("Alvo", justify="right")
    table.add_column("Trailing Stop", justify="right")
    table.add_column("Setup")

    for p in summary["positions"]:
        p_color = "green" if p["unrealized_pnl"] >= 0 else "red"
        table.add_row(
            p["ticker"],
            str(p["quantity"]),
            f"R$ {p['average_price']:.2f}",
            f"R$ {p['current_price']:.2f}",
            f"[{p_color}]R$ {p['unrealized_pnl']:,.2f}[/{p_color}]",
            f"[{p_color}]{p['unrealized_pnl_pct']:+.2f}%[/{p_color}]",
            f"R$ {p['stop_loss']:.2f}" if p["stop_loss"] else "-",
            f"R$ {p['take_profit']:.2f}" if p["take_profit"] else "-",
            f"R$ {p['trailing_stop']:.2f}" if p["trailing_stop"] else "-",
            p["strategy"],
        )

    console.print(table)
    session.close()


@app.command()
def scan(
    all_tickers: bool = typer.Option(True, "--all/--top", help="Escanear universo completo (~100 ações) ou apenas Top 20"),
    high_conviction: bool = typer.Option(False, "--high/--all-setups", help="Filtrar apenas Compras Muito Vantajosas (Score >= 8.0 & R/R >= 2.2)"),
    min_score: float = typer.Option(7.0, "--min-score", "-m", help="Score mínimo de confluência (6.0 a 10.0)"),
):
    """Executa o scanner de mercado com filtro de Regime Macro, ADTV e Position Sizing."""
    regime = analyze_market_regime()
    regime_color = "green" if regime["status"] == "BULL" else "yellow" if regime["status"] == "CORRECTION" else "red"
    console.print(
        Panel(
            f"[bold {regime_color}]Regime do IBOVESPA: {regime['name']}[/bold {regime_color}]\n"
            f"• Cotação: R$ {regime['ibov_close'] or 0:,.0f} ({regime['ibov_change_pct']:+.2f}%)\n"
            f"• Diretriz Macro: {regime['description']}",
            title="Gatekeeper de Mercado Institucional",
            border_style=regime_color,
        )
    )

    if regime["status"] == "PANIC":
        console.print("[bold red]Operações suspensas pelo regime de pânico.[/bold red]")
        return

    tickers = get_universe(top_only=not all_tickers)
    results = run_screener(tickers=tickers, min_score=min_score, high_conviction_only=high_conviction, show_progress=True)

    if not results:
        console.print("[dim]Nenhuma oportunidade atendeu aos critérios configurados hoje.[/dim]")
        return

    table = Table(title="Oportunidades de Entrada Identificadas", show_header=True, header_style="bold green")
    table.add_column("Ticker", style="bold")
    table.add_column("Setup")
    table.add_column("Score", justify="center")
    table.add_column("Entrada Ref.", justify="right")
    table.add_column("Stop Loss", justify="right")
    table.add_column("Alvo", justify="right")
    table.add_column("R/R", justify="center")
    table.add_column("Lote Sug.", justify="right")
    table.add_column("ADTV 21", justify="right")
    table.add_column("Justificativa Técnica")

    for r in results:
        adtv_txt = f"R$ {r.get('adtv_milhoes', 0):.1f}M" if "adtv_milhoes" in r else "-"
        shares_txt = f"{r.get('suggested_shares', '-')} ações" if "suggested_shares" in r else "-"
        table.add_row(
            r["ticker"],
            r["name"],
            f"[bold]{r['score']}/10[/bold]",
            f"R$ {r['entry_price']:.2f}",
            f"R$ {r['stop_loss']:.2f}",
            f"R$ {r['take_profit']:.2f}",
            f"{r.get('rr_ratio', 'N/A')}x",
            shares_txt,
            adtv_txt,
            r["reason"],
        )

    console.print(table)


@app.command()
def dividends(
    all_tickers: bool = typer.Option(False, "--all", "-a", help="Escanear universo completo de proventos"),
):
    """Rastreia proventos anunciados (Dividendos e JCP) e próximas Datas COM."""
    tickers = get_universe(top_only=not all_tickers)
    console.print("[yellow]Buscando anúncios de proventos com Data COM próxima...[/yellow]")
    divs = scan_upcoming_dividends(tickers)

    if not divs:
        console.print("[dim]Nenhum anúncio com Data COM nos próximos 15 dias encontrado.[/dim]")
        return

    table = Table(title="Calendário de Proventos e Data COM", show_header=True, header_style="bold blue")
    table.add_column("Ticker", style="bold")
    table.add_column("Data COM (Corte)", justify="center")
    table.add_column("Data EX", justify="center")
    table.add_column("Dias Restantes", justify="center")
    table.add_column("Provento Est. (R$)", justify="right")
    table.add_column("Cotação Atual", justify="right")
    table.add_column("Yield Estimado (%)", justify="right")

    for d in divs:
        table.add_row(
            d["ticker"],
            d["data_com"].strftime("%d/%m/%Y"),
            d["data_ex"].strftime("%d/%m/%Y"),
            f"{d['days_until_com']} dias",
            f"R$ {d['estimated_value']:.2f}",
            f"R$ {d['current_price']:.2f}",
            f"{d['projected_yield_pct']:.2f}%",
        )

    console.print(table)


@app.command()
def buy(
    ticker: str = typer.Argument(..., help="Ticker da ação (ex: PETR4, VALE3)"),
    quantity: int = typer.Argument(..., help="Quantidade de ações adquiridas"),
    price: float = typer.Argument(..., help="Preço unitário pago (R$)"),
    fees: float = typer.Option(1.50, "--fees", "-f", help="Taxas de corretagem e emolumentos B3 (R$)"),
    stop: Optional[float] = typer.Option(None, "--stop", "-s", help="Preço de Stop Loss"),
    target: Optional[float] = typer.Option(None, "--target", "-t", help="Preço de Take Profit"),
    strategy: str = typer.Option("MANUAL", "--strategy", help="Estratégia (IFR2, TREND, DIVIDEND_COM, MANUAL)"),
    notes: Optional[str] = typer.Option(None, "--notes", "-n", help="Notas ou justificativa"),
):
    """Registra uma ordem de COMPRA, atualizando a custódia e o Preço Médio oficial."""
    init_db()
    session = get_db_session()
    pos = execute_buy(
        session=session,
        ticker=ticker,
        quantity=quantity,
        price=price,
        fees=fees,
        stop_loss=stop,
        take_profit=target,
        strategy=strategy,
        notes=notes,
    )
    session.close()

    console.print(
        f"[bold green]✓ COMPRA REGISTRADA COM SUCESSO![/bold green]\n"
        f"Ativo: [bold]{pos.ticker}[/bold] | Qtd Total: {pos.quantity} ações | "
        f"Novo Preço Médio: [bold]R$ {pos.average_price:.2f}[/bold] | Custo Total: R$ {pos.total_cost:,.2f}"
    )


@app.command()
def sell(
    ticker: str = typer.Argument(..., help="Ticker da ação (ex: PETR4, VALE3)"),
    quantity: int = typer.Argument(..., help="Quantidade de ações vendidas"),
    price: float = typer.Argument(..., help="Preço unitário de venda (R$)"),
    fees: float = typer.Option(1.50, "--fees", "-f", help="Taxas de corretagem e emolumentos B3 (R$)"),
    notes: Optional[str] = typer.Option(None, "--notes", "-n", help="Notas de encerramento"),
):
    """Registra uma ordem de VENDA, apura PnL líquido e atualiza o livro fiscal do mês."""
    init_db()
    session = get_db_session()
    try:
        res = execute_sell(
            session=session,
            ticker=ticker,
            quantity=quantity,
            price=price,
            fees=fees,
            notes=notes,
        )
        session.close()

        pnl_color = "green" if res["realized_pnl"] >= 0 else "red"
        status_mes = "ISENTO (< R$ 20k)" if res["is_exempt_month"] else "TRIBUTÁVEL (> R$ 20k)"

        console.print(
            f"[bold green]✓ VENDA REGISTRADA COM SUCESSO![/bold green]\n"
            f"Ativo: [bold]{res['ticker']}[/bold] | Qtd Vendida: {res['quantity_sold']} | "
            f"PnL Líquido Realizado: [{pnl_color}]R$ {res['realized_pnl']:,.2f} ({res['realized_pnl_pct']:+.2f}%)[/{pnl_color}]\n"
            f"Status Fiscal ({res['tax_year_month']}): [bold]{status_mes}[/bold] | DARF Atual: R$ {res['final_darf_month']:,.2f}"
        )
    except Exception as e:
        session.close()
        console.print(f"[bold red]Erro ao registrar venda: {e}[/bold red]")


@app.command()
def taxes():
    """Exibe o livro fiscal, controle do limite de R$ 20.000 e valor a recolher no DARF."""
    init_db()
    session = get_db_session()
    summary = get_current_tax_summary(session)
    session.close()

    status_tag = "[bold green]MÊS ISENTO[/bold green]" if summary["is_exempt"] else "[bold yellow]MÊS TRIBUTÁVEL[/bold yellow]"
    pnl_color = "green" if summary["net_profit"] >= 0 else "red"

    panel_text = (
        f"Mês de Apuração: [bold]{summary['year_month']}[/bold] ({status_tag})\n\n"
        f"• Vendas Brutas no Mês: R$ {summary['total_sales']:,.2f} / R$ {summary['sales_limit']:,.2f} "
        f"(Margem restante para isenção: R$ {summary['sales_remaining_limit']:,.2f})\n"
        f"• Lucro/Prejuízo Líquido: [{pnl_color}]R$ {summary['net_profit']:,.2f}[/{pnl_color}]\n"
        f"• Prejuízo Compensado de Meses Anteriores: R$ {summary['prior_losses_used']:,.2f}\n"
        f"• Prejuízo Acumulado Restante para o Futuro: R$ {summary['accumulated_loss']:,.2f}\n"
        f"• Base de Cálculo Tributável (15%): R$ {summary['taxable_profit']:,.2f}\n"
        f"• Imposto Bruto Devido: R$ {summary['tax_due']:,.2f}\n"
        f"• IRRF Dedo-Duro Retido na Fonte (0,005%): R$ {summary['irrf_withheld']:,.2f}\n\n"
        f"[bold]Valor Final do DARF a Recolher (Código 6015): R$ {summary['final_darf']:,.2f}[/bold]"
    )

    console.print(Panel(panel_text, title="Gestão Fiscal e DARF - Swing Trade B3", border_style="cyan"))


@app.command()
def alert():
    """Executa manualmente a rotina matinal das 09:15 BRT com disparo de notificações."""
    run_morning_routine(dry_run=False)


@app.command()
def web():
    """Inicia a interface visual no navegador (Streamlit Dashboard)."""
    app_file = PROJECT_ROOT / "b3pilot" / "web" / "app.py"
    console.print(f"[bold cyan]Iniciando B3 Ações Pilot Dashboard em http://localhost:8501...[/bold cyan]")
    # Roda streamlit usando o executável do venv
    venv_streamlit = PROJECT_ROOT / ".venv" / "bin" / "streamlit"
    cmd = [str(venv_streamlit) if venv_streamlit.exists() else "streamlit", "run", str(app_file)]
    subprocess.run(cmd)


@app.command(name="test-telegram")
def test_telegram():
    """Envia uma mensagem de teste para o Telegram configurado no .env."""
    ok = send_telegram_message("🚀 *B3 Ações Pilot*: Conexão com Telegram funcionando com sucesso!")
    if ok:
        console.print("[bold green]✓ Notificação enviada com sucesso para o Telegram![/bold green]")
    else:
        console.print("[bold red]Falha ao enviar mensagem no Telegram. Verifique TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID no .env.[/bold red]")


@app.command(name="audit-trava")
def audit_trava_command(
    ticker: str = typer.Argument("MCDC34", help="Ticker do ativo (ex: MCDC34 ou PETR4)"),
    strike_alto: float = typer.Option(..., "--strike-alto", "-sa", help="Strike superior (K_high)"),
    strike_baixo: float = typer.Option(..., "--strike-baixo", "-sb", help="Strike inferior (K_low)"),
    premio: float = typer.Option(..., "--premio", "-p", help="Prêmio líquido por ação em R$"),
    tipo: str = typer.Option("BEAR_PUT", "--tipo", "-t", help="Tipo: BEAR_PUT (Trava de Baixa c/ Put) ou BEAR_CALL (c/ Call)"),
    qtd: int = typer.Option(100, "--qtd", "-q", help="Quantidade de opções (ex: 100)"),
):
    """Audita a assimetria risco/retorno de uma Trava de Baixa recomendada por banco/corretora."""
    res = audit_option_spread(
        underlying=ticker,
        spread_type=tipo,
        strike_long=strike_alto,
        strike_short=strike_baixo,
        net_premium=premio,
        contracts_qty=qtd,
    )

    border_color = "red" if res["is_retail_trap"] else "green"
    verdict_str = " | ".join(res["verdict_tags"])

    panel_text = (
        f"[bold cyan]{res['strategy_desc']}[/bold cyan]\n"
        f"• Quantidade: {res['contracts_qty']} opções\n"
        f"• Break-even (Preço de Equilíbrio): R$ {res['break_even']:.2f}\n"
        f"• Ganho Máximo Total: [bold green]R$ {res['max_profit_total']:,.2f}[/bold green]\n"
        f"• Perda Máxima Total: [bold red]R$ {res['max_loss_total']:,.2f}[/bold red]\n"
        f"• Assimetria Risco x Retorno: [bold]{res['risk_reward_ratio']:.2f}x[/bold]\n"
        f"• Taxa de Acerto Mínima Necessária: [bold]{res['required_win_rate_pct']:.1f}%[/bold]\n\n"
        f"[bold {border_color}]{verdict_str}[/bold {border_color}]\n"
        f"{res['recommendation']}\n\n"
        f"[dim]{res['tax_warning']}[/dim]"
    )

    console.print(Panel(panel_text, title=f"Auditoria Quantitativa de Opções - {ticker}", border_style=border_color))


if __name__ == "__main__":
    app()
