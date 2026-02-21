"""Tenant (customer/organization) model."""
from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Tenant(Base):
    """Organization/customer using the platform."""

    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Accounting connection (e.g., QuickBooks)
    accounting_platform = Column(String(50), default="quickbooks")
    accounting_realm_id = Column(String(50), unique=True, index=True)  # QBO company ID
    access_token = Column(String(500))
    refresh_token = Column(String(500))
    token_expires_at = Column(DateTime(timezone=True))

    # API authentication
    api_key = Column(String(64), unique=True, index=True)

    # Email alerts
    alert_email = Column(String(255))

    vendors = relationship("Vendor", back_populates="tenant")
    bills = relationship("Bill", back_populates="tenant")
    anomalies = relationship("Anomaly", back_populates="tenant")
