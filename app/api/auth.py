"""API key authentication dependency."""
from fastapi import Header, HTTPException, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Tenant


def get_tenant_by_key(x_api_key: str = Header(...), db: Session = Depends(get_db)) -> Tenant:
    """Validate X-API-Key header and return the matching tenant."""
    tenant = db.query(Tenant).filter(Tenant.api_key == x_api_key).first()
    if not tenant:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return tenant
