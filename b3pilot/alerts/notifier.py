"""Módulo de envio de alertas multicanal: macOS Notification Center e Telegram Bot."""

import subprocess
import requests
from typing import Optional

from b3pilot.config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    MACOS_NOTIFICATIONS,
)


def send_macos_notification(title: str, subtitle: str, message: str) -> bool:
    """Dispara um banner nativo no Notification Center do macOS com som."""
    if not MACOS_NOTIFICATIONS:
        return False

    # Escapa aspas para o AppleScript
    clean_title = title.replace('"', '\\"')
    clean_subtitle = subtitle.replace('"', '\\"')
    clean_msg = message.replace('"', '\\"')

    script = (
        f'display notification "{clean_msg}" '
        f'with title "{clean_title}" '
        f'subtitle "{clean_subtitle}" '
        f'sound name "Glass"'
    )

    try:
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True)
        return True
    except Exception as e:
        print(f"Erro ao disparar notificação macOS: {e}")
        return False


def send_telegram_message(message: str, parse_mode: str = "Markdown") -> bool:
    """Envia uma mensagem formatada para o bot privado do Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"Erro ao disparar mensagem no Telegram: {e}")
        return False


def dispatch_alert(title: str, subtitle: str, message: str) -> None:
    """Dispara o alerta nos canais ativos (macOS e Telegram)."""
    # 1. macOS Banner
    send_macos_notification(title=title, subtitle=subtitle, message=message)

    # 2. Telegram Message
    telegram_text = f"*{title}*\n_{subtitle}_\n\n{message}"
    send_telegram_message(telegram_text)
