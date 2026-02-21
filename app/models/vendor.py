"""Vendor model."""
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Vendor(Base):
    """Normalized vendor master."""

    __tablename__ = "vendors"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    external_id = Column(String(100), nullable=False, index=True)  # QBO Vendor.Id
    name = Column(String(255), nullable=False)
    display_name = Column(String(255))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    tenant = relationship("Tenant", back_populates="vendors")
    bills = relationship("Bill", back_populates="vendor")
