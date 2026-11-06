"""Monitor de Cotação Intradiária e Disparador de Alertas de Preço (Telegram + macOS).

Monitora posições em aberto durante o pregão, detectando:
- Toque no Alvo de Realização Parcial (com roteiro de execução)
- Toque no Stop Loss
- Toque no Alvo Final (Take Profit)
"""

import time
from datetime import datetime, date
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from b3pilot.ledger.db import get_db_session, Position, AlertLog
from b3pilot.data.b3_feed import fetch_latest_price, fetch_ticker_data
from b3pilot.core.strategies import compute_indicators
from b3pilot.alerts.notifier import dispatch_alert, send_telegram_message

REVERSAL_WATCH_LIST = ["WEGE3", "EGIE3"]


def check_positions_price_alerts(session: Session, is_simulated: bool = False) -> List[Dict[str, Any]]:
    """Varre as posições ativas em busca de gatilhos de preço atingidos (Parcial, Stop ou Alvo)."""
    positions = session.query(Position).filter_by(is_simulated=is_simulated).all()
    triggered_alerts = []
    today_str = date.today().isoformat()

    for pos in positions:
        ticker = pos.ticker
        current_price = fetch_latest_price(ticker)
        if not current_price:
            continue

        # 1. Alvo de Realização Parcial
        if (
            pos.partial_target
            and not pos.is_partial_executed
            and current_price >= pos.partial_target
        ):
            alert_key = f"PARTIAL_{ticker}_{pos.partial_target}_{today_str}"
            already_sent = session.query(AlertLog).filter_by(alert_type=alert_key).first()
            if not already_sent:
                qty_sell = pos.partial_quantity or (pos.quantity // 2 if pos.quantity > 1 else 1)
                rem_qty = pos.quantity - qty_sell
                new_stop = pos.new_stop_after_partial or pos.average_price

                msg = (
                    f"🎯 *ALVO PARCIAL ATINGIDO: {ticker} a R$ {current_price:.2f}* (Meta: R$ {pos.partial_target:.2f})\n\n"
                    f"📋 *Roteiro de Execução no Home Broker:*\n"
                    f"1. Cancele o Stop antigo de {pos.quantity} ações de {ticker}.\n"
                    f"2. Envie VENDA a mercado de {qty_sell} ações (Lucro parcial no bolso).\n"
                    f"3. Cadastre NOVO STOP para as {rem_qty} ações restantes em R$ {new_stop:.2f} (lucro travado)."
                )

                dispatch_alert(
                    title=f"🎯 Alvo Parcial: {ticker} a R$ {current_price:.2f}",
                    subtitle="Hora de embolsar 50% e subir o stop",
                    message=f"Venda {qty_sell} ações e suba o stop das {rem_qty} restantes para R$ {new_stop:.2f}.",
                )
                send_telegram_message(msg)

                log = AlertLog(ticker=ticker, alert_type=alert_key, message=msg)
                session.add(log)
                session.commit()

                triggered_alerts.append({
                    "ticker": ticker,
                    "type": "PARTIAL_TARGET",
                    "price": current_price,
                    "target": pos.partial_target,
                    "qty_sell": qty_sell,
                    "rem_qty": rem_qty,
                    "new_stop": new_stop,
                })

        # 2. Stop Loss rompido
        if pos.stop_loss and current_price <= pos.stop_loss:
            alert_key = f"STOP_{ticker}_{pos.stop_loss}_{today_str}"
            already_sent = session.query(AlertLog).filter_by(alert_type=alert_key).first()
            if not already_sent:
                msg = (
                    f"🛑 *STOP LOSS ROMPIDO: {ticker} a R$ {current_price:.2f}* (Limite: R$ {pos.stop_loss:.2f})\n\n"
                    f"⚠️ Ação imediata: Venda suas {pos.quantity} ações a mercado para preservar capital."
                )
                dispatch_alert(
                    title=f"🛑 Stop Loss: {ticker} a R$ {current_price:.2f}",
                    subtitle="Limite violado",
                    message=f"Encerre as {pos.quantity} ações imediatamente.",
                )
                send_telegram_message(msg)

                log = AlertLog(ticker=ticker, alert_type=alert_key, message=msg)
                session.add(log)
                session.commit()

                triggered_alerts.append({
                    "ticker": ticker,
                    "type": "STOP_LOSS",
                    "price": current_price,
                    "stop": pos.stop_loss,
                    "quantity": pos.quantity,
                })

        # 3. Take Profit Final atingido
        if pos.take_profit and current_price >= pos.take_profit:
            alert_key = f"TP_{ticker}_{pos.take_profit}_{today_str}"
            already_sent = session.query(AlertLog).filter_by(alert_type=alert_key).first()
            if not already_sent:
                msg = (
                    f"🏆 *TAKE PROFIT FINAL ATINGIDO: {ticker} a R$ {current_price:.2f}* (Alvo: R$ {pos.take_profit:.2f})\n\n"
                    f"🎉 Encerre a posição de {pos.quantity} ações e comemore o lucro realizado!"
                )
                dispatch_alert(
                    title=f"🏆 Alvo Final: {ticker} a R$ {current_price:.2f}",
                    subtitle="Meta atingida com sucesso",
                    message=f"Realize o lucro das {pos.quantity} ações.",
                )
                send_telegram_message(msg)

                log = AlertLog(ticker=ticker, alert_type=alert_key, message=msg)
                session.add(log)
                session.commit()

                triggered_alerts.append({
                    "ticker": ticker,
                    "type": "TAKE_PROFIT",
                    "price": current_price,
                    "target": pos.take_profit,
                    "quantity": pos.quantity,
                })

    return triggered_alerts


def check_reversal_watch_list(session: Session, tickers: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Monitora ativos em observação de queda livre (ex: WEGE3, EGIE3) em busca de pivô de reversão acima da EMA 9."""
    import pandas as pd
    watch_tickers = tickers or REVERSAL_WATCH_LIST
    triggered = []
    today_str = date.today().isoformat()

    for ticker in watch_tickers:
        df = fetch_ticker_data(ticker)
        if df is None or len(df) < 50:
            continue
        data = compute_indicators(df)
        last = data.iloc[-1]
        prev = data.iloc[-2]

        close = float(last["Close"])
        open_p = float(last["Open"])
        ema9 = float(last["EMA_9"])
        prev_ema9 = float(prev["EMA_9"])
        rsi2 = float(last["RSI_2"]) if pd.notna(last["RSI_2"]) else 50.0

        # Sinal de Reversão:
        # Preço fecha acima da EMA 9 com candle verde após período de sobrevenda
        crossed_ema9 = close > ema9 and float(prev["Close"]) <= float(prev["EMA_9"])
        is_green = close >= open_p and close > float(prev["Close"])

        if crossed_ema9 and is_green:
            alert_key = f"REVERSAL_{ticker}_{today_str}"
            already_sent = session.query(AlertLog).filter_by(alert_type=alert_key).first()
            if not already_sent:
                msg = (
                    f"🔔 *SINAL DE REVERSÃO DETECTADO: {ticker} a R$ {close:.2f}*\n\n"
                    f"• O papel superou a EMA 9 (R$ {ema9:.2f}) com candle comprador após ciclo de queda.\n"
                    f"• IFR(2): {rsi2:.1f}\n"
                    f"• Setup: Fundo provável formado. Avalie entrada com stop na mínima recente."
                )
                dispatch_alert(
                    title=f"🔔 Reversão: {ticker} a R$ {close:.2f}",
                    subtitle="Superação da EMA 9",
                    message=f"Ativo superou EMA 9 (R$ {ema9:.2f}) com candle comprador.",
                )
                send_telegram_message(msg)

                log = AlertLog(ticker=ticker, alert_type=alert_key, message=msg)
                session.add(log)
                session.commit()

                triggered.append({
                    "ticker": ticker,
                    "type": "REVERSAL_TRIGGER",
                    "price": close,
                    "ema9": ema9,
                })

    return triggered


def run_intraday_price_watcher(interval_seconds: int = 300, max_iterations: Optional[int] = None) -> None:
    """Loop contínuo de monitoramento intradiário de cotações da carteira e radar de reversão."""
    iteration = 0
    while True:
        session = get_db_session()
        try:
            alerts = check_positions_price_alerts(session, is_simulated=False)
            reversal_alerts = check_reversal_watch_list(session)
            total = len(alerts) + len(reversal_alerts)
            if total > 0:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] {total} alerta(s) disparado(s)!")
        except Exception as e:
            print(f"Erro no watcher: {e}")
        finally:
            session.close()

        iteration += 1
        if max_iterations and iteration >= max_iterations:
            break
        time.sleep(interval_seconds)
