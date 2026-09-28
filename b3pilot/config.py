import os
from pathlib import Path
from dotenv import load_dotenv

# Carrega variáveis de ambiente de .env se existir
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# Configurações do Banco de Dados SQLite
DB_NAME = os.getenv("DATABASE_PATH", "portfolio.db")
DB_PATH = PROJECT_ROOT / DB_NAME
DATABASE_URL = f"sqlite:///{DB_PATH}"

# Configurações do Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# Notificações macOS nativas
MACOS_NOTIFICATIONS = os.getenv("MACOS_NOTIFICATIONS", "1") == "1"

# Gestão de Risco e Parâmetros da Carteira
DEFAULT_CAPITAL = float(os.getenv("DEFAULT_CAPITAL", "10000.00"))
RISK_MAX_PER_TRADE_PERCENT = float(os.getenv("RISK_MAX_PER_TRADE_PERCENT", "0.02"))  # 2% de risco máx por trade

# Pesos da Estratégia Híbrida
WEIGHT_MEAN_REVERSION = 0.60  # 60% IFR2
WEIGHT_TREND_FOLLOWING = 0.40  # 40% Momentum / Seguidor de Tendência

# Parâmetros Técnicos dos Setups
IFR2_OVERSOLD_THRESHOLD = 10.0   # Nível de sobrevenda extrema no IFR(2)
IFR2_TREND_SMA = 200             # Média de longo prazo para validar tendência
TREND_EMA_FAST = 9               # Média rápida para momentum
TREND_EMA_SLOW = 21              # Média lenta para momentum
ATR_PERIOD = 14                  # Período para volatilidade ATR
ATR_TRAILING_MULTIPLIER = 2.0    # Múltiplo de ATR para Trailing Stop
TIME_STOP_DAYS = 10              # Número máx de pregões estagnados antes do time-stop

# Regras Fiscais da B3 (Receita Federal)
TAX_EXEMPTION_LIMIT_MONTHLY = 20000.00  # Limite de R$ 20.000 em vendas para isenção
TAX_RATE_SWING_TRADE = 0.15             # 15% sobre o ganho líquido tributável
IRRF_RATE_SALES = 0.00005               # 0,005% dedo-duro sobre alienação
MIN_DARF_PAYMENT = 10.00                # Valor mínimo para recolhimento de DARF
