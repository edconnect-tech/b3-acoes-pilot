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
from b3pilot.ledger.portfolio import execute_buy, execute_sell, execute_partial_sale, get_portfolio_summary
from b3pilot.ledger.taxes import get_current_tax_summary
from b3pilot.core.screener import run_screener
from b3pilot.core.regime import analyze_market_regime
from b3pilot.core.risk import (
    audit_option_spread,
    analyze_portfolio_sector_distribution,
    check_sector_and_cluster_conflict,
)
from b3pilot.data.sectors import get_asset_sector_profile
from b3pilot.core.chat import process_chat_query, process_chat_query_with_ai
from b3pilot.ai.providers import (
    detect_best_provider,
    list_providers_status,
    test_provider_connection,
)
from b3pilot.data.dividends_feed import scan_upcoming_dividends
from b3pilot.data.universe import get_universe
from b3pilot.alerts.morning_job import run_morning_routine
from b3pilot.alerts.price_watcher import run_intraday_price_watcher
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
    table.add_column("Setor")
    table.add_column("Macro-Cluster")
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
        prof = get_asset_sector_profile(p["ticker"])
        table.add_row(
            p["ticker"],
            prof.get("sector", "Outros"),
            ", ".join(prof.get("clusters", [])),
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

    # Diagnóstico de Diversificação Setorial & Concentração
    sec_audit = analyze_portfolio_sector_distribution(
        summary["positions"],
        total_capital=summary["current_market_value"],
    )
    score_color = "green" if sec_audit["diversification_score"] >= 80 else ("yellow" if sec_audit["diversification_score"] >= 60 else "red")
    console.print(
        f"\n[bold]Score de Diversificação da Carteira:[/bold] [{score_color}]{sec_audit['diversification_score']:.0f}/100 "
        f"({sec_audit['diversification_status']})[/{score_color}]"
    )

    if sec_audit.get("concentration_warnings"):
        console.print("[bold yellow]⚠️ Alertas de Concentração Setorial / Correlação Compartilhada:[/bold yellow]")
        for w in sec_audit["concentration_warnings"]:
            console.print(f"  • [yellow]{w}[/yellow]")
    console.print()

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
    table.add_column("Range 52S", justify="center")
    table.add_column("Lote Sug.", justify="right")
    table.add_column("ADTV 21", justify="right")
    table.add_column("Justificativa Técnica")

    for r in results:
        adtv_txt = f"R$ {r.get('adtv_milhoes', 0):.1f}M" if "adtv_milhoes" in r else "-"
        shares_txt = f"{r.get('suggested_shares', '-')} ações" if "suggested_shares" in r else "-"
        range_52s_txt = f"{r.get('range_52w_pct', 0):.0f}%" if "range_52w_pct" in r else "-"
        table.add_row(
            r["ticker"],
            r["name"],
            f"[bold]{r['score']}/10[/bold]",
            f"R$ {r['entry_price']:.2f}",
            f"R$ {r['stop_loss']:.2f}",
            f"R$ {r['take_profit']:.2f}",
            f"{r.get('rr_ratio', 'N/A')}x",
            range_52s_txt,
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
    target: Optional[float] = typer.Option(None, "--target", "-t", help="Preço de Take Profit Final (TP2)"),
    tp1: Optional[float] = typer.Option(None, "--tp1", help="Preço de Realização Parcial (TP1)"),
    tp1_qty: Optional[int] = typer.Option(None, "--tp1-qty", help="Quantidade de ações para realização parcial"),
    new_stop_after_partial: Optional[float] = typer.Option(None, "--new-stop-after-partial", help="Novo Stop Loss após a realização parcial"),
    strategy: str = typer.Option("MANUAL", "--strategy", help="Estratégia (IFR2, TREND, DIVIDEND_COM, MANUAL)"),
    notes: Optional[str] = typer.Option(None, "--notes", "-n", help="Notas ou justificativa"),
    simulated: bool = typer.Option(False, "--simulated", "-s", help="Registrar no Laboratório de Simulação (Paper Trading)"),
):
    """Registra uma ordem de COMPRA, atualizando a custódia e o Preço Médio oficial."""
    init_db()
    session = get_db_session()

    # Auditoria de Conflito de Setor e Risco de Correlação
    from b3pilot.ledger.db import Position
    active_positions = session.query(Position).filter_by(is_simulated=simulated).all()
    active_tickers = [p.ticker for p in active_positions]

    if active_tickers:
        conflict = check_sector_and_cluster_conflict(ticker, active_tickers)
        if conflict.get("has_conflict"):
            console.print(f"\n[bold yellow]⚠️ ALERTA DE CONCENTRAÇÃO SETORIAL:[/bold yellow]")
            console.print(f"  • [yellow]{conflict['warning_message']}[/yellow]")
            console.print(f"  • [dim]{conflict['recommendation']}[/dim]\n")

    pos = execute_buy(
        session=session,
        ticker=ticker,
        quantity=quantity,
        price=price,
        fees=fees,
        stop_loss=stop,
        take_profit=target,
        partial_target=tp1,
        partial_quantity=tp1_qty,
        new_stop_after_partial=new_stop_after_partial,
        strategy=strategy,
        notes=notes,
        is_simulated=simulated,
    )
    session.close()

    env_tag = " [bold magenta](SIMULAÇÃO)[/bold magenta]" if simulated else ""
    console.print(
        f"[bold green]✓ COMPRA REGISTRADA COM SUCESSO!{env_tag}[/bold green]\n"
        f"Ativo: [bold]{pos.ticker}[/bold] | Qtd Total: {pos.quantity} ações | "
        f"Novo Preço Médio: [bold]R$ {pos.average_price:.2f}[/bold] | Custo Total: R$ {pos.total_cost:,.2f}"
    )
    if pos.partial_target:
        console.print(
            f"🎯 Alvo Parcial (TP1): R$ {pos.partial_target:.2f} ({pos.partial_quantity or (pos.quantity // 2)} ações) | "
            f"Novo Stop pós-parcial: R$ {(pos.new_stop_after_partial or pos.average_price):.2f}"
        )


@app.command()
def sell(
    ticker: str = typer.Argument(..., help="Ticker da ação (ex: PETR4, VALE3)"),
    quantity: int = typer.Argument(..., help="Quantidade de ações vendidas"),
    price: float = typer.Argument(..., help="Preço unitário de venda (R$)"),
    fees: float = typer.Option(1.50, "--fees", "-f", help="Taxas de corretagem e emolumentos B3 (R$)"),
    notes: Optional[str] = typer.Option(None, "--notes", "-n", help="Notas de encerramento"),
    simulated: bool = typer.Option(False, "--simulated", "-s", help="Registrar na Carteira Simulada"),
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
            is_simulated=simulated,
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
    """Executa manualmente a rotina matinal das 09:55 BRT com disparo de notificações."""
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


@app.command(name="ask")
def ask_command(
    question: str = typer.Argument(..., help="Pergunta em linguagem natural (ex: 'Posso comprar PETR4?' ou 'Devo vender algo?')"),
    simulated: bool = typer.Option(False, "--simulated", "-s", help="Consultar no contexto da Carteira Simulada"),
    ai: bool = typer.Option(False, "--ai/--no-ai", help="Sintetizar análise determinística com o conector de IA configurado (ou --provider)"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="Provedor de IA (auto, agy, gemini, openai, anthropic, openrouter, groq, deepseek, ollama, gemini_cli, claude_cli, codex_cli)"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Modelo específico do provedor selecionado"),
):
    """Consulta o Assistente Operacional em tempo real sobre compras, vendas e setups da B3."""
    init_db()
    session = get_db_session()
    use_ai = ai or bool(provider)

    with console.status("[bold cyan]Analisando mercado e dados técnicos...[/bold cyan]"):
        if use_ai:
            target_provider = provider or "auto"
            res = process_chat_query_with_ai(
                question,
                session,
                is_simulated=simulated,
                provider=target_provider,
                model=model,
            )
            response = res["response"]
            subtitle = f"Conector: {res['provider']} ({res['model']})"
            warning = res.get("warning")
        else:
            response = process_chat_query(question, session, is_simulated=simulated)
            subtitle = "Motor: deterministic (python-64bit)"
            warning = None

    if warning:
        console.print(f"[yellow]⚠️ {warning}[/yellow]")
    console.print(Panel(response, title="Assistente Operacional B3", subtitle=subtitle, border_style="cyan"))
    session.close()


@app.command(name="ai-status")
def ai_status_command():
    """Lista todos os conectores de IA disponíveis (APIs e CLIs com login Google agy/OAuth)."""
    statuses = list_providers_status()
    active_best = detect_best_provider()

    table = Table(title="Conectores de IA — B3 Ações Pilot", show_header=True, header_style="bold cyan")
    table.add_column("ID", style="bold")
    table.add_column("Provedor")
    table.add_column("Autenticação")
    table.add_column("Status")
    table.add_column("Modelo Padrão")
    table.add_column("Como Configurar")

    for st_item in statuses:
        auth_map = {
            "none": "Nativa (Sem LLM)",
            "cli_oauth": "Login CLI / OAuth",
            "api_key": "API Key / URL",
            "local": "Serviço Local",
        }
        status_str = (
            f"[green]{st_item['status_label']}[/green]"
            if st_item["ready"]
            else f"[yellow]{st_item['status_label']}[/yellow]"
        )
        model_str = st_item["default_model"] or "Padrão da CLI"
        table.add_row(
            st_item["id"],
            st_item["name"],
            auth_map.get(st_item["auth_type"], st_item["auth_type"]),
            status_str,
            model_str,
            st_item["login_hint"],
        )

    console.print()
    console.print(table)
    console.print(
        f"\n[bold]Provedor ativo padrão (`AI_PROVIDER`):[/bold] [cyan]{active_best}[/cyan] "
        f"[dim](use `b3pilot ask --ai -p agy \"...\"` ou configure no .env)[/dim]\n"
    )


@app.command(name="ai-test")
def ai_test_command(
    provider: str = typer.Option("auto", "--provider", "-p", help="ID do provedor a testar (ex: agy, gemini, openai, ollama)"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Modelo opcional para sobrescrever o padrão"),
):
    """Testa a conectividade e autenticação do conector de IA informado."""
    with console.status(f"[bold cyan]Testando conector '{provider}'...[/bold cyan]"):
        result = test_provider_connection(provider=provider, model=model)

    if result["ok"]:
        console.print(
            f"[bold green]✓ {result['provider']} ({result['model']}) pronto:[/bold green] {result['message']}"
        )
    else:
        console.print(
            f"[bold red]✗ Falha no conector {result['provider']}:[/bold red] {result['message']}"
        )
        raise typer.Exit(code=1)


@app.command(name="partial-sale")
def partial_sale_command(
    ticker: str = typer.Argument(..., help="Código da ação (ex: SOJA3, PETR4)"),
    quantity: int = typer.Argument(..., help="Quantidade de ações a vender na parcial"),
    price: float = typer.Argument(..., help="Preço de venda executado em R$"),
    new_stop: Optional[float] = typer.Option(None, "--new-stop", "-ns", help="Novo Stop Loss a cadastrar para as ações restantes"),
    fees: float = typer.Option(0.0, "--fees", "-f", help="Taxas de corretagem e emolumentos em R$"),
    simulated: bool = typer.Option(False, "--simulated", "-s", help="Registrar na Carteira Simulada"),
):
    """Executa a Realização Parcial (Scale-Out) e eleva o Stop Loss das ações restantes."""
    init_db()
    session = get_db_session()
    try:
        res = execute_partial_sale(
            session=session,
            ticker=ticker,
            quantity=quantity,
            price=price,
            new_stop_loss=new_stop,
            fees=fees,
            is_simulated=simulated,
        )
        pnl_color = "green" if res["realized_pnl"] >= 0 else "red"
        output_txt = (
            f"[bold green]✓ Realização Parcial Registrada com Sucesso![/bold green]\n\n"
            f"• Ativo: [bold]{res['ticker']}[/bold]\n"
            f"• Quantidade Vendida: {res['quantity_sold']} ações a R$ {res['sale_price']:.2f}\n"
            f"• Lucro Realizado: [{pnl_color}]R$ {res['realized_pnl']:+,.2f} ({res['realized_pnl_pct']:+.2f}%)[/{pnl_color}]\n"
            f"• Posição Remanescente: {res['remaining_quantity']} ações (PM R$ {res['average_price']:.2f})\n"
            f"• Novo Stop Loss: R$ {res['new_stop_loss']:.2f}\n"
            f"• [bold]Lucro Mínimo Garantido no Pior Caso:[/bold] [bold green]R$ {res['guaranteed_total_pnl']:+,.2f}[/bold green]\n\n"
            f"[bold cyan]📋 Roteiro de Execução no Home Broker:[/bold cyan]\n"
            + "\n".join(res["broker_instructions"])
        )
        console.print(Panel(output_txt, title=f"Realização Parcial - {ticker}", border_style="green"))
    except Exception as e:
        console.print(f"[bold red]Erro ao executar realização parcial: {e}[/bold red]")
    finally:
        session.close()


@app.command(name="watch")
def watch_command(
    interval: int = typer.Option(300, "--interval", "-i", help="Intervalo de verificação em segundos (padrão: 300s / 5min)"),
    max_loops: Optional[int] = typer.Option(None, "--loops", "-l", help="Número máximo de verificações antes de parar"),
):
    """Monitora cotações intradiárias da carteira durante o pregão com alertas no Telegram e Mac."""
    console.print(f"[bold cyan]Iniciando monitor intradiário de preços (intervalo: {interval}s)...[/bold cyan]")
    console.print("[dim]Pressione Ctrl+C para encerrar o monitoramento.[/dim]\n")
    try:
        run_intraday_price_watcher(interval_seconds=interval, max_iterations=max_loops)
    except KeyboardInterrupt:
        console.print("\n[yellow]Monitor intradiário encerrado.[/yellow]")


@app.command(name="check-reversals")
def check_reversals_command():
    """Varre a lista de vigilância (ex: WEGE3, EGIE3) em busca de sinais de reversão e pivô de fundo."""
    init_db()
    session = get_db_session()
    from b3pilot.alerts.price_watcher import check_reversal_watch_list, REVERSAL_WATCH_LIST
    console.print(f"[bold cyan]Verificando radar de reversão para: {', '.join(REVERSAL_WATCH_LIST)}...[/bold cyan]")
    alerts = check_reversal_watch_list(session)
    if not alerts:
        console.print("[dim]Nenhum ativo do radar confirmou reversão acima da EMA 9 hoje. Continua em queda livre / observação.[/dim]")
    else:
        for a in alerts:
            console.print(f"[bold green]🔔 Reversão confirmada em {a['ticker']} a R$ {a['price']:.2f} (superou EMA 9: R$ {a['ema9']:.2f})[/bold green]")
    session.close()


if __name__ == "__main__":
    app()
