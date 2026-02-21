"""Anomaly detection result."""
from sqlalchemy import Column, Integer, Float, String, ForeignKey, DateTime, Text, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


# Note: bill_id nullable for anomalies that span multiple bills (e.g., duplicate pairs)


class Anomaly(Base):
    """Flagged anomaly (duplicate, price creep, suspicious total, etc.)."""

    __tablename__ = "anomalies"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    bill_id = Column(Integer, ForeignKey("bills.id"), nullable=True, index=True)

    anomaly_type = Column(String(50), nullable=False)  # duplicate, price_creep, round_number, scope_drift
    severity = Column(String(20), default="medium")  # low, medium, high
    amount = Column(Float)
    confidence_score = Column(Float)  # 0-1, for alert threshold
    description = Column(Text)
    metadata_json = Column(Text)  # JSON: related_bill_id, z_score, etc.

    # Only alert (email/push) if True — avoid fatigue
    should_alert = Column(Boolean, default=False)

    # Status management
    status = Column(String(20), default="open")  # open, acknowledged, dismissed
    resolution_notes = Column(Text)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    acknowledged_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    tenant = relationship("Tenant", back_populates="anomalies")
