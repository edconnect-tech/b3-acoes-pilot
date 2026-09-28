"""Motor fiscal para apuração de IR em Swing Trade de Ações na B3 (Receita Federal)."""

from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, extract

from b3pilot.ledger.db import Transaction, MonthlyTaxRecord
from b3pilot.config import (
    TAX_EXEMPTION_LIMIT_MONTHLY,
    TAX_RATE_SWING_TRADE,
    IRRF_RATE_SALES,
    MIN_DARF_PAYMENT,
)


def get_or_create_monthly_record(session: Session, year_month: str) -> MonthlyTaxRecord:
    """Busca ou cria o registro fiscal para o mês de apuração informado (formato 'YYYY-MM')."""
    record = session.query(MonthlyTaxRecord).filter_by(year_month=year_month).first()
    if not record:
        # Busca o prejuízo acumulado do mês anterior
        prior_record = (
            session.query(MonthlyTaxRecord)
            .filter(MonthlyTaxRecord.year_month < year_month)
            .order_by(MonthlyTaxRecord.year_month.desc())
            .first()
        )
        carried_loss = prior_record.accumulated_loss if prior_record else 0.0

        record = MonthlyTaxRecord(
            year_month=year_month,
            total_sales=0.0,
            net_profit=0.0,
            is_exempt=True,
            taxable_profit=0.0,
            prior_losses_used=0.0,
            accumulated_loss=carried_loss,
            tax_due=0.0,
            irrf_withheld=0.0,
            final_darf=0.0,
            is_paid=False,
        )
        session.add(record)
        session.commit()
    return record


def recalculate_monthly_taxes(session: Session, year_month: str) -> MonthlyTaxRecord:
    """Recalcula integralmente o status tributário de um determinado mês."""
    year, month = map(int, year_month.split("-"))

    # Busca todas as transações de VENDA ocorridas no mês
    sells = (
        session.query(Transaction)
        .filter(
            Transaction.type == "SELL",
            extract("year", Transaction.date) == year,
            extract("month", Transaction.date) == month,
        )
        .all()
    )

    total_sales = sum(s.price * s.quantity for s in sells)
    net_profit = sum(s.realized_pnl for s in sells)

    # Busca prejuízo acumulado herdado de meses anteriores
    prior_record = (
        session.query(MonthlyTaxRecord)
        .filter(MonthlyTaxRecord.year_month < year_month)
        .order_by(MonthlyTaxRecord.year_month.desc())
        .first()
    )
    inherited_loss = prior_record.accumulated_loss if prior_record else 0.0

    record = get_or_create_monthly_record(session, year_month)
    record.total_sales = round(total_sales, 2)
    record.net_profit = round(net_profit, 2)

    # Regra de Isenção: vendas totais <= R$ 20.000 no mês
    is_exempt = total_sales <= TAX_EXEMPTION_LIMIT_MONTHLY
    record.is_exempt = is_exempt

    current_accumulated_loss = inherited_loss
    prior_losses_used = 0.0
    taxable_profit = 0.0
    tax_due = 0.0
    irrf_withheld = round(total_sales * IRRF_RATE_SALES, 2)
    final_darf = 0.0

    if is_exempt:
        # Se for isento e houve lucro: não paga IR e o lucro não consome prejuízo acumulado!
        # Se for isento e houve PREJUÍZO: o prejuízo é adicionado para abater lucros futuros!
        if net_profit < 0:
            current_accumulated_loss += abs(net_profit)
    else:
        # Vendas > R$ 20.000: operações são tributáveis
        if net_profit > 0:
            if current_accumulated_loss > 0:
                if net_profit >= current_accumulated_loss:
                    prior_losses_used = current_accumulated_loss
                    taxable_profit = net_profit - current_accumulated_loss
                    current_accumulated_loss = 0.0
                else:
                    prior_losses_used = net_profit
                    taxable_profit = 0.0
                    current_accumulated_loss -= net_profit
            else:
                taxable_profit = net_profit

            tax_due = round(taxable_profit * TAX_RATE_SWING_TRADE, 2)
            # Abate o dedo-duro (IRRF) retido na fonte
            darf_val = tax_due - irrf_withheld
            final_darf = round(darf_val, 2) if darf_val >= MIN_DARF_PAYMENT else 0.0
        else:
            # Houve prejuízo no mês tributável: acumula para o futuro
            current_accumulated_loss += abs(net_profit)

    record.taxable_profit = round(taxable_profit, 2)
    record.prior_losses_used = round(prior_losses_used, 2)
    record.accumulated_loss = round(current_accumulated_loss, 2)
    record.tax_due = round(tax_due, 2)
    record.irrf_withheld = round(irrf_withheld, 2)
    record.final_darf = round(final_darf, 2)

    session.commit()
    return record


def get_current_tax_summary(session: Session) -> Dict[str, Any]:
    """Retorna um resumo fiscal consolidado do mês atual."""
    current_ym = datetime.utcnow().strftime("%Y-%m")
    record = recalculate_monthly_taxes(session, current_ym)

    return {
        "year_month": record.year_month,
        "total_sales": record.total_sales,
        "sales_limit": TAX_EXEMPTION_LIMIT_MONTHLY,
        "sales_remaining_limit": max(0.0, TAX_EXEMPTION_LIMIT_MONTHLY - record.total_sales),
        "is_exempt": record.is_exempt,
        "net_profit": record.net_profit,
        "taxable_profit": record.taxable_profit,
        "prior_losses_used": record.prior_losses_used,
        "accumulated_loss": record.accumulated_loss,
        "tax_due": record.tax_due,
        "irrf_withheld": record.irrf_withheld,
        "final_darf": record.final_darf,
        "darf_code": "6015",
        "is_paid": record.is_paid,
    }
