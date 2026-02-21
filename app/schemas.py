"""Pydantic schemas for API."""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class TenantCreate(BaseModel):
    name: str
    alert_email: Optional[str] = None


class TenantOut(BaseModel):
    id: int
    name: str
    accounting_platform: str
    accounting_realm_id: Optional[str] = None
    api_key: Optional[str] = None
    alert_email: Optional[str] = None

    class Config:
        from_attributes = True


class ConnectQBOBody(BaseModel):
    realm_id: str
    access_token: str
    refresh_token: str


class VendorOut(BaseModel):
    id: int
    external_id: str
    name: str

    class Config:
        from_attributes = True


class BillOut(BaseModel):
    id: int
    external_id: str
    bill_number: Optional[str]
    total_amount: float
    txn_date: date
    vendor_id: int
    has_line_items: bool

    class Config:
        from_attributes = True


class AnomalyOut(BaseModel):
    id: int
    bill_id: Optional[int]
    anomaly_type: str
    severity: str
    amount: Optional[float]
    confidence_score: Optional[float]
    description: Optional[str]
    should_alert: bool
    status: str = "open"
    resolution_notes: Optional[str] = None
    created_at: datetime
    vendor_name: Optional[str] = None
    bill_number: Optional[str] = None

    class Config:
        from_attributes = True


class AnomalyUpdate(BaseModel):
    status: str  # open, acknowledged, dismissed
    resolution_notes: Optional[str] = None


class AnomalyWithBill(AnomalyOut):
    bill: Optional[BillOut] = None


class SyncResult(BaseModel):
    vendors: int
    bills: int
    payments: int
    line_items: int


class DetectionResult(BaseModel):
    anomalies_found: int


class DashboardStats(BaseModel):
    tenant_id: int
    vendor_count: int
    bill_count: int
    anomaly_count: int
    total_anomaly_amount: float
    high_confidence_count: int
