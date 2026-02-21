"""API routes for tenants, sync, detection, anomalies."""
import csv
import io
import logging
import secrets
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import func, distinct
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Tenant, Bill, Vendor, Anomaly
from app.schemas import (
    TenantCreate,
    TenantOut,
    TenantCreateResponse,
    TenantRotateKeyResponse,
    AnomalyOut,
    AnomalyUpdate,
    ConnectQBOBody,
    QBOCallbackQuery,
    SyncResult,
    DetectionResult,
    DashboardStats,
)
from app.schemas import MAX_LEN_OAUTH_CODE, MAX_LEN_STATE, MAX_LEN_REALM_ID
from app.api.auth import get_tenant_by_key
from app.pipeline.sync import sync_tenant
from app.detection.engine import run_detection
from app.connectors.quickbooks import get_authorization_url, exchange_code_for_tokens
from app.alerts.email import send_anomaly_alert

router = APIRouter()
logger = logging.getLogger(__name__)

# Path param validation: positive integer IDs (strict input validation, OWASP)
TenantIdPath = Path(..., gt=0, description="Tenant ID (positive integer)")
AnomalyIdPath = Path(..., gt=0, description="Anomaly ID (positive integer)")


def get_qbo_callback_query(
    code: str = Query(..., min_length=1, max_length=MAX_LEN_OAUTH_CODE),
    state: str = Query("", max_length=MAX_LEN_STATE),
    realm_id: str = Query("", max_length=MAX_LEN_REALM_ID),
    realmId: str = Query("", max_length=MAX_LEN_REALM_ID),
) -> QBOCallbackQuery:
    """Dependency: validate OAuth callback query params with length limits (OWASP)."""
    return QBOCallbackQuery(code=code, state=state, realm_id=realm_id, realmId=realmId)


@router.get("/auth/qbo")
def qbo_authorize(
    tenant_id: int = Query(1, gt=0, le=2**31 - 1, description="Tenant ID for OAuth state"),
):
    """Redirect user to QuickBooks OAuth authorization."""
    url = get_authorization_url(state=f"tenant_{tenant_id}")
    return RedirectResponse(url=url)


@router.get("/auth/qbo/callback")
def qbo_callback(
    query: QBOCallbackQuery = Depends(get_qbo_callback_query),
    db: Session = Depends(get_db),
):
    """Handle QuickBooks OAuth callback, store tokens, redirect to dashboard."""
    state = query.state
    tenant_id = int(state.replace("tenant_", "")) if state and state.startswith("tenant_") else 1
    if tenant_id <= 0:
        raise HTTPException(400, "Invalid state parameter")
    token = exchange_code_for_tokens(query.code)
    t = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not t:
        raise HTTPException(404, "Tenant not found")
    t.accounting_realm_id = query.realm_id or query.realmId
    t.access_token = token["access_token"]
    t.refresh_token = token["refresh_token"]
    db.commit()
    return RedirectResponse(url=f"/?tenant={tenant_id}&connected=1")


@router.post("/tenants", response_model=TenantCreateResponse)
def create_tenant(data: TenantCreate, db: Session = Depends(get_db)):
    """Create a tenant and generate an API key. API key is returned only in this response (secure handling)."""
    api_key = secrets.token_hex(32)
    t = Tenant(
        name=data.name,
        accounting_platform="quickbooks",
        api_key=api_key,
        alert_email=data.alert_email,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    logger.info("Tenant created: id=%s name=%s", t.id, t.name)
    # Return create response with api_key only once (OWASP: never expose keys in GET/list)
    return TenantCreateResponse(
        id=t.id,
        name=t.name,
        accounting_platform=t.accounting_platform,
        accounting_realm_id=t.accounting_realm_id,
        alert_email=t.alert_email,
        api_key=api_key,
    )


@router.get("/tenants/{tenant_id}", response_model=TenantOut)
def get_tenant(
    tenant_id: int = TenantIdPath,
    db: Session = Depends(get_db),
):
    """Return tenant without api_key (key is never exposed on GET — secure API key handling)."""
    t = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not t:
        raise HTTPException(404, "Tenant not found")
    return t


@router.post("/tenants/{tenant_id}/rotate-key", response_model=TenantRotateKeyResponse)
def rotate_api_key(
    tenant_id: int = TenantIdPath,
    tenant: Tenant = Depends(get_tenant_by_key),
    db: Session = Depends(get_db),
):
    """
    Rotate API key for the tenant. Requires current X-API-Key.
    New key is returned only in this response (key rotation — OWASP).
    """
    if tenant.id != tenant_id:
        raise HTTPException(403, "Forbidden")
    new_key = secrets.token_hex(32)
    tenant.api_key = new_key
    db.commit()
    logger.info("API key rotated for tenant id=%s", tenant_id)
    return TenantRotateKeyResponse(api_key=new_key)


@router.post("/tenants/{tenant_id}/connect-qbo")
def connect_qbo(
    tenant_id: int = TenantIdPath,
    body: ConnectQBOBody,
    tenant: Tenant = Depends(get_tenant_by_key),
    db: Session = Depends(get_db),
):
    """Store QBO OAuth tokens in the request body (not query params)."""
    if tenant.id != tenant_id:
        raise HTTPException(403, "Forbidden")
    tenant.accounting_realm_id = body.realm_id
    tenant.access_token = body.access_token
    tenant.refresh_token = body.refresh_token
    db.commit()
    return {"status": "connected"}


@router.post("/tenants/{tenant_id}/sync", response_model=SyncResult)
def sync(
    tenant_id: int = TenantIdPath,
    tenant: Tenant = Depends(get_tenant_by_key),
    db: Session = Depends(get_db),
):
    """Sync vendors, bills, payments from QuickBooks."""
    if tenant.id != tenant_id:
        raise HTTPException(403, "Forbidden")
    try:
        counts = sync_tenant(tenant, db)
        return SyncResult(**counts)
    except Exception as e:
        logger.error("Sync failed for tenant %s: %s", tenant_id, e)
        raise HTTPException(500, str(e))


@router.post("/tenants/{tenant_id}/detect", response_model=DetectionResult)
def detect(
    tenant_id: int = TenantIdPath,
    tenant: Tenant = Depends(get_tenant_by_key),
    db: Session = Depends(get_db),
):
    """Run anomaly detection pipeline."""
    if tenant.id != tenant_id:
        raise HTTPException(403, "Forbidden")
    count = run_detection(tenant_id, db)
    db.commit()
    logger.info("Detection run for tenant %s: %d anomalies found", tenant_id, count)

    # Send email alert if configured
    if settings_smtp_enabled() and tenant.alert_email and count > 0:
        alertable = (
            db.query(Anomaly)
            .filter(
                Anomaly.tenant_id == tenant_id,
                Anomaly.should_alert == True,
                Anomaly.status == "open",
            )
            .order_by(Anomaly.created_at.desc())
            .limit(50)
            .all()
        )
        if alertable:
            send_anomaly_alert(tenant, alertable)

    return DetectionResult(anomalies_found=count)


def settings_smtp_enabled() -> bool:
    from app.config import settings
    return bool(settings.smtp_user)


@router.get("/tenants/{tenant_id}/anomalies", response_model=list[AnomalyOut])
def list_anomalies(
    tenant_id: int = TenantIdPath,
    status: str = Query(
        default="open",
        min_length=1,
        max_length=32,
        description="Filter: open, acknowledged, dismissed, all",
    ),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    tenant: Tenant = Depends(get_tenant_by_key),
    db: Session = Depends(get_db),
):
    """List anomalies for tenant with vendor name and bill number, newest first."""
    if tenant.id != tenant_id:
        raise HTTPException(403, "Forbidden")

    q = (
        db.query(Anomaly, Vendor.name.label("vendor_name"), Bill.bill_number.label("bill_number"))
        .outerjoin(Bill, Anomaly.bill_id == Bill.id)
        .outerjoin(Vendor, Bill.vendor_id == Vendor.id)
        .filter(Anomaly.tenant_id == tenant_id)
    )

    # Strict status filter (valid set only)
    if status not in ("open", "acknowledged", "dismissed", "all"):
        raise HTTPException(400, "status must be one of: open, acknowledged, dismissed, all")
    if status != "all":
        q = q.filter(Anomaly.status == status)

    rows = q.order_by(Anomaly.created_at.desc()).offset(offset).limit(limit).all()

    result = []
    for anomaly, vendor_name, bill_number in rows:
        out = AnomalyOut.model_validate(anomaly)
        out.vendor_name = vendor_name
        out.bill_number = bill_number
        result.append(out)
    return result


@router.patch("/tenants/{tenant_id}/anomalies/{anomaly_id}", response_model=AnomalyOut)
def update_anomaly(
    tenant_id: int = TenantIdPath,
    anomaly_id: int = AnomalyIdPath,
    body: AnomalyUpdate,
    tenant: Tenant = Depends(get_tenant_by_key),
    db: Session = Depends(get_db),
):
    """Update anomaly status (acknowledge or dismiss)."""
    if tenant.id != tenant_id:
        raise HTTPException(403, "Forbidden")

    anomaly = db.query(Anomaly).filter(
        Anomaly.id == anomaly_id,
        Anomaly.tenant_id == tenant_id,
    ).first()
    if not anomaly:
        raise HTTPException(404, "Anomaly not found")

    anomaly.status = body.status
    if body.resolution_notes is not None:
        anomaly.resolution_notes = body.resolution_notes
    db.commit()
    db.refresh(anomaly)
    return AnomalyOut.model_validate(anomaly)


@router.get("/tenants/{tenant_id}/anomalies/export")
def export_anomalies(
    tenant_id: int = TenantIdPath,
    tenant: Tenant = Depends(get_tenant_by_key),
    db: Session = Depends(get_db),
):
    """Export anomalies as a CSV file."""
    if tenant.id != tenant_id:
        raise HTTPException(403, "Forbidden")

    rows = (
        db.query(Anomaly, Vendor.name.label("vendor_name"), Bill.bill_number.label("bill_number"))
        .outerjoin(Bill, Anomaly.bill_id == Bill.id)
        .outerjoin(Vendor, Bill.vendor_id == Vendor.id)
        .filter(Anomaly.tenant_id == tenant_id)
        .order_by(Anomaly.created_at.desc())
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Date", "Vendor", "Bill #", "Anomaly Type", "Severity",
        "Amount", "Confidence %", "Description", "Status",
    ])
    for anomaly, vendor_name, bill_number in rows:
        writer.writerow([
            anomaly.created_at.date() if anomaly.created_at else "",
            vendor_name or "",
            bill_number or "",
            anomaly.anomaly_type,
            anomaly.severity,
            f"{anomaly.amount:.2f}" if anomaly.amount is not None else "",
            f"{anomaly.confidence_score * 100:.0f}" if anomaly.confidence_score is not None else "",
            anomaly.description or "",
            anomaly.status,
        ])

    output.seek(0)
    filename = f"anomalies_{date.today().isoformat()}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/tenants/{tenant_id}/dashboard", response_model=DashboardStats)
def dashboard(
    tenant_id: int = TenantIdPath,
    tenant: Tenant = Depends(get_tenant_by_key),
    db: Session = Depends(get_db),
):
    """Dashboard summary stats."""
    if tenant.id != tenant_id:
        raise HTTPException(403, "Forbidden")
    vendor_count = db.query(Vendor).filter(Vendor.tenant_id == tenant_id).count()
    bill_count = db.query(Bill).filter(Bill.tenant_id == tenant_id).count()
    anomaly_count = db.query(Anomaly).filter(Anomaly.tenant_id == tenant_id).count()

    # Deduplicate by bill_id to avoid counting the same bill amount multiple times
    # Sum distinct bill amounts that have at least one anomaly
    distinct_bill_ids = (
        db.query(distinct(Anomaly.bill_id))
        .filter(Anomaly.tenant_id == tenant_id, Anomaly.bill_id.isnot(None))
        .subquery()
    )
    total_amt = (
        db.query(func.coalesce(func.sum(Bill.total_amount), 0))
        .filter(Bill.id.in_(distinct_bill_ids))
        .scalar()
    ) or 0

    high_conf = db.query(Anomaly).filter(
        Anomaly.tenant_id == tenant_id, Anomaly.should_alert == True
    ).count()

    return DashboardStats(
        tenant_id=tenant_id,
        vendor_count=vendor_count,
        bill_count=bill_count,
        anomaly_count=anomaly_count,
        total_anomaly_amount=float(total_amt),
        high_confidence_count=high_conf,
    )
