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
MAX_POSITION_ALLOCATION_PERCENT = float(os.getenv("MAX_POSITION_ALLOCATION_PERCENT", "0.25"))  # Máx 25% do capital em um ativo
MIN_ADTV_FINANCIAL = float(os.getenv("MIN_ADTV_FINANCIAL", "5000000.00"))  # Mínimo R$ 5M/dia em volume financeiro real

# Gestão de Concentração e Correlação Setorial (Proteção contra apostas concentradas)
MAX_SECTOR_ALLOCATION_PERCENT = float(os.getenv("MAX_SECTOR_ALLOCATION_PERCENT", "0.35"))  # Máximo 35% da carteira em um mesmo setor
MAX_CLUSTER_ACTIVE_TRADES = int(os.getenv("MAX_CLUSTER_ACTIVE_TRADES", "1"))  # Máximo 1 trade simultâneo no mesmo cluster de risco
ENABLE_SECTOR_DIVERSIFICATION = os.getenv("ENABLE_SECTOR_DIVERSIFICATION", "1") == "1"

# Pesos da Estratégia Híbrida
WEIGHT_MEAN_REVERSION = 0.60  # 60% IFR2
WEIGHT_TREND_FOLLOWING = 0.40  # 40% Momentum / Seguidor de Tendência

# Parâmetros Técnicos dos Setups
IFR2_OVERSOLD_THRESHOLD = 10.0   # Nível de sobrevenda extrema no IFR(2)
IFR2_EXTREME_OVERSOLD = 5.0      # Sobrevenda de pânico
IFR2_TREND_SMA = 200             # Média de longo prazo para validar tendência
IFR2_CATASTROPHIC_STOP_PERCENT = 0.10  # Stop catastrófico de 10% para não ser violado por ruído
IFR2_TIME_STOP_DAYS = 5          # Saída no 5º pregão se não atingir a máxima
TREND_EMA_FAST = 9               # Média rápida para momentum
TREND_EMA_SLOW = 21              # Média lenta para momentum
ATR_PERIOD = 14                  # Período para volatilidade ATR
ATR_TRAILING_MULTIPLIER = 2.0    # Múltiplo de ATR para Trailing Stop
TIME_STOP_DAYS = 10              # Número máx de pregões estagnados antes do time-stop geral

# Regras Fiscais da B3 (Receita Federal)
TAX_EXEMPTION_LIMIT_MONTHLY = 20000.00  # Limite de R$ 20.000 em vendas para isenção
TAX_RATE_SWING_TRADE = 0.15             # 15% sobre o ganho líquido tributável
IRRF_RATE_SALES = 0.00005               # 0,005% dedo-duro sobre alienação
MIN_DARF_PAYMENT = 10.00                # Valor mínimo para recolhimento de DARF

# Conectores de IA (APIs REST e CLIs com login OAuth como Google agy)
AI_PROVIDER = os.getenv("AI_PROVIDER", "deterministic").strip().lower()
AI_MODEL = os.getenv("AI_MODEL", "").strip()
AI_BASE_URL = os.getenv("AI_BASE_URL", "").strip()
AI_API_KEY = os.getenv("AI_API_KEY", "").strip()
AI_TIMEOUT_SECONDS = int(os.getenv("AI_TIMEOUT_SECONDS", "60"))

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip()
