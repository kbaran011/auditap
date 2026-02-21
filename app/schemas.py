"""
Pydantic schemas for API — strict validation (OWASP API Security).

- All string inputs have explicit max_length to prevent DoS and injection.
- Request body models use extra="forbid" to reject unexpected fields.
"""
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, ConfigDict

# Shared max lengths for consistency and security (strict input validation)
MAX_LEN_NAME = 255
MAX_LEN_EMAIL = 320
MAX_LEN_REALM_ID = 50
MAX_LEN_OAUTH_TOKEN = 500
MAX_LEN_API_KEY = 64
MAX_LEN_STATUS = 32
MAX_LEN_NOTES = 2000
MAX_LEN_DESCRIPTION = 2000
MAX_LEN_OAUTH_CODE = 512
MAX_LEN_STATE = 128


class TenantCreate(BaseModel):
    """Request body for creating a tenant; extra fields rejected (OWASP)."""
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., min_length=1, max_length=MAX_LEN_NAME)
    alert_email: Optional[str] = Field(None, max_length=MAX_LEN_EMAIL)


class TenantOut(BaseModel):
    """Tenant response — never includes api_key (returned only on create/rotate)."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    accounting_platform: str
    accounting_realm_id: Optional[str] = None
    alert_email: Optional[str] = None


class TenantCreateResponse(BaseModel):
    """Returned once on tenant create; only response that includes api_key."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    accounting_platform: str
    accounting_realm_id: Optional[str] = None
    alert_email: Optional[str] = None
    api_key: str  # Shown only once; client must store it securely


class TenantRotateKeyResponse(BaseModel):
    """Returned once after key rotation; new api_key must be stored by the client."""
    api_key: str


class ConnectQBOBody(BaseModel):
    """Request body for QBO token storage; strict length limits on tokens."""
    model_config = ConfigDict(extra="forbid")
    realm_id: str = Field(..., min_length=1, max_length=MAX_LEN_REALM_ID)
    access_token: str = Field(..., min_length=1, max_length=MAX_LEN_OAUTH_TOKEN)
    refresh_token: str = Field(..., min_length=1, max_length=MAX_LEN_OAUTH_TOKEN)


class VendorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    external_id: str
    name: str


class BillOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    external_id: str
    bill_number: Optional[str]
    total_amount: float
    txn_date: date
    vendor_id: int
    has_line_items: bool


class AnomalyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
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


class AnomalyUpdate(BaseModel):
    """Request body for updating anomaly; only allowed statuses and bounded notes."""
    model_config = ConfigDict(extra="forbid")
    status: Literal["open", "acknowledged", "dismissed"] = Field(...)
    resolution_notes: Optional[str] = Field(None, max_length=MAX_LEN_NOTES)


class AnomalyWithBill(AnomalyOut):
    bill: Optional[BillOut] = None


# OAuth callback query params — schema-based validation to avoid injection and malformed input
class QBOCallbackQuery(BaseModel):
    """Strict validation for /api/auth/qbo/callback query parameters."""
    model_config = ConfigDict(extra="forbid")
    code: str = Field(..., min_length=1, max_length=MAX_LEN_OAUTH_CODE)
    state: str = Field("", max_length=MAX_LEN_STATE)
    realm_id: str = Field("", max_length=MAX_LEN_REALM_ID)
    realmId: str = Field("", max_length=MAX_LEN_REALM_ID)


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
