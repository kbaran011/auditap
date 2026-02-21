"""Payment model."""
from sqlalchemy import Column, Integer, Float, ForeignKey, DateTime, Date, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Payment(Base):
    """Bill payment linked to a bill."""

    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    bill_id = Column(Integer, ForeignKey("bills.id"), nullable=False, index=True)
    external_id = Column(String(100), nullable=False, unique=True, index=True)
    total_amt = Column(Float, nullable=False)
    txn_date = Column(Date, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    sync_at = Column(DateTime(timezone=True), server_default=func.now())

    bill = relationship("Bill", back_populates="payments")
