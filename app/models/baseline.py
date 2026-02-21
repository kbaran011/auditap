"""Vendor baseline stats for anomaly detection."""
from sqlalchemy import Column, Integer, Float, ForeignKey, DateTime, Date, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class VendorBaseline(Base):
    """Per-vendor rolling baseline stats (e.g., 90-day window)."""

    __tablename__ = "vendor_baselines"

    id = Column(Integer, primary_key=True, index=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=False, index=True)
    window_start = Column(Date, nullable=False)
    window_end = Column(Date, nullable=False)

    avg_amount = Column(Float)
    std_amount = Column(Float)
    min_amount = Column(Float)
    max_amount = Column(Float)
    payment_count = Column(Integer, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("vendor_id", "window_start", "window_end", name="uq_baseline_vendor_window"),
    )
