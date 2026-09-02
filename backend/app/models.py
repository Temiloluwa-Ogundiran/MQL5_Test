from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from .db import Base


class Intent(Base):
    __tablename__ = "intents"
    id = Column(Integer, primary_key=True)
    signal_id = Column(String, nullable=False)
    account_id = Column(BigInteger, nullable=False)
    symbol = Column(String, nullable=False)
    direction = Column(String, nullable=False)
    lots = Column(Float, nullable=False)
    sl = Column(Float, default=0)
    tp = Column(Float, default=0)
    generated_at = Column(DateTime(timezone=True), nullable=False)
    magic_number = Column(Integer, nullable=False)
    comment = Column(String, nullable=False)
    status = Column(String, default="PENDING")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    sent_at = Column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        UniqueConstraint("signal_id", "account_id", name="uq_signal_account"),
    )


class Report(Base):
    __tablename__ = "reports"
    id = Column(Integer, primary_key=True)
    signal_id = Column(String, nullable=False)
    account_id = Column(BigInteger, nullable=False)
    magic = Column(Integer, nullable=False)
    order_ticket = Column(BigInteger, default=0)
    deal_ticket = Column(BigInteger, default=0)
    position_ticket = Column(BigInteger, default=0)
    fill_price = Column(Float, default=0)
    filled_volume = Column(Float, default=0)
    retcode = Column(Integer, default=0)
    retcode_description = Column(String, default="")
    status = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
