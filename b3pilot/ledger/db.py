"""Camada de persistência local SQLite e schemas do SQLAlchemy."""

from datetime import datetime, date
from typing import Optional
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    Date,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from b3pilot.config import DATABASE_URL

Base = declarative_base()


class Transaction(Base):
    """Registro imutável de ordens executadas de compra e venda."""
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(DateTime, default=datetime.utcnow, nullable=False)
    ticker = Column(String(20), nullable=False, index=True)
    type = Column(String(10), nullable=False)  # 'BUY' ou 'SELL'
    quantity = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)
    fees = Column(Float, default=0.0)  # Emolumentos + Corretagem
    total_value = Column(Float, nullable=False)  # (price * quantity) +/- fees
    realized_pnl = Column(Float, default=0.0)    # PnL líquido (preenchido na venda)
    strategy = Column(String(50), default="MANUAL")
    notes = Column(Text, nullable=True)
    is_simulated = Column(Boolean, default=False, nullable=False, index=True)


class Position(Base):
    """Posição ativa em custódia (carteira atual)."""
    __tablename__ = "positions"
    __table_args__ = (
        UniqueConstraint("ticker", "is_simulated", name="uix_ticker_simulated"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(20), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    average_price = Column(Float, nullable=False)  # Preço Médio Ponderado oficial
    total_cost = Column(Float, nullable=False)     # average_price * quantity
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    trailing_stop = Column(Float, nullable=True)
    highest_price = Column(Float, nullable=True)   # Maior máxima desde a entrada
    strategy = Column(String(50), default="MANUAL")
    entry_date = Column(DateTime, default=datetime.utcnow)
    is_simulated = Column(Boolean, default=False, nullable=False, index=True)


class MonthlyTaxRecord(Base):
    """Livro fiscal mensal para apuração de IR e emissão de DARF (Swing Trade B3)."""
    __tablename__ = "monthly_tax_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    year_month = Column(String(7), unique=True, nullable=False, index=True)  # 'YYYY-MM'
    total_sales = Column(Float, default=0.0)        # Alienações totais no mês
    net_profit = Column(Float, default=0.0)         # Lucro ou prejuízo líquido realizado
    is_exempt = Column(Boolean, default=True)       # True se total_sales <= 20.000
    taxable_profit = Column(Float, default=0.0)     # Base de cálculo após compensar perdas
    prior_losses_used = Column(Float, default=0.0)  # Prejuízo pregresso compensado
    accumulated_loss = Column(Float, default=0.0)   # Prejuízo acumulado remanescente
    tax_due = Column(Float, default=0.0)            # 15% sobre o lucro tributável
    irrf_withheld = Column(Float, default=0.0)      # 0,005% dedo-duro retido na fonte
    final_darf = Column(Float, default=0.0)         # Valor a pagar no DARF (se >= R$ 10,00)
    is_paid = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DividendRecord(Base):
    """Controle de proventos (Dividendos e Juros sobre Capital Próprio - JCP)."""
    __tablename__ = "dividend_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(20), nullable=False, index=True)
    event_type = Column(String(20), nullable=False)  # 'DIVIDENDO' ou 'JCP'
    date_com = Column(Date, nullable=False)
    date_ex = Column(Date, nullable=False)
    date_payment = Column(Date, nullable=True)
    value_per_share = Column(Float, nullable=False)
    quantity_held = Column(Integer, default=0)
    gross_amount = Column(Float, default=0.0)
    net_amount = Column(Float, default=0.0)  # Descontado 15% IRRF no caso de JCP
    is_received = Column(Boolean, default=False)


class AlertLog(Base):
    """Histórico de alertas disparados pelo sistema."""
    __tablename__ = "alert_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    ticker = Column(String(20), nullable=False)
    alert_type = Column(String(30), nullable=False)  # 'BUY', 'SELL', 'DATA_COM'
    message = Column(Text, nullable=False)
    channels = Column(String(50), default="TELEGRAM+MACOS")


# Gerenciador da conexão SQLite
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Cria as tabelas no SQLite se não existirem e aplica migrações de campos novos."""
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        for tbl in ["transactions", "positions"]:
            try:
                cols = [c[1] for c in conn.exec_driver_sql(f"PRAGMA table_info({tbl})").fetchall()]
                if "is_simulated" not in cols:
                    conn.exec_driver_sql(f"ALTER TABLE {tbl} ADD COLUMN is_simulated BOOLEAN DEFAULT 0 NOT NULL")
                    conn.commit()
            except Exception:
                pass


def get_db_session() -> Session:
    """Retorna uma nova sessão com o banco de dados."""
    return SessionLocal()
