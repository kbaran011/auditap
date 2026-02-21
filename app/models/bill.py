"""Bill and LineItem models."""
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Date, Text, Boolean, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Bill(Base):
    """Raw bill / invoice record."""

    __tablename__ = "bills"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=False, index=True)
    external_id = Column(String(100), nullable=False, index=True)  # QBO Bill.Id — unique per tenant

    bill_number = Column(String(100))
    total_amount = Column(Float, nullable=False)
    balance = Column(Float, default=0)
    due_date = Column(Date)
    txn_date = Column(Date, nullable=False, index=True)  # Bill date
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    sync_at = Column(DateTime(timezone=True), server_default=func.now())

    # For OCR fallback - whether we have parsed line items from PDF
    has_line_items = Column(Boolean, default=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "external_id", name="uq_bill_tenant_external"),
    )

    tenant = relationship("Tenant", back_populates="bills")
    vendor = relationship("Vendor", back_populates="bills")
    line_items = relationship("LineItem", back_populates="bill", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="bill")


class LineItem(Base):
    """Line-level detail (amount, description, quantity, unit price)."""

    __tablename__ = "line_items"

    id = Column(Integer, primary_key=True, index=True)
    bill_id = Column(Integer, ForeignKey("bills.id"), nullable=False, index=True)
    external_id = Column(String(100))
    description = Column(Text)
    amount = Column(Float, nullable=False)
    quantity = Column(Float, default=1)
    unit_price = Column(Float)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    bill = relationship("Bill", back_populates="line_items")
