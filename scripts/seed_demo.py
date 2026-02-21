#!/usr/bin/env python3
"""Seed demo tenant + sample bills for testing without QuickBooks."""
import secrets
import sys
from pathlib import Path
from datetime import date, timedelta
import random

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal, init_db
from app.models import Tenant, Vendor, Bill, LineItem


def seed():
    init_db()
    db = SessionLocal()
    t = db.query(Tenant).filter(Tenant.name == "Demo Company").first()
    if not t:
        t = Tenant(
            name="Demo Company",
            accounting_platform="quickbooks",
            accounting_realm_id="demo-realm",
            api_key=secrets.token_hex(32),
        )
        db.add(t)
        db.commit()
        db.refresh(t)
        print(f"Created tenant: {t.id}")
        # API key printed only for local/demo; never log or expose in production
        print(f"API Key: {t.api_key}")
    else:
        if not t.api_key:
            t.api_key = secrets.token_hex(32)
            db.commit()
        print(f"Using tenant: {t.id}")
        print(f"API Key: {t.api_key}")

    # Create 5 vendors
    vendors = []
    for i, name in enumerate(["Acme Supplies", "TechCorp IT", "Office Depot", "CloudHost Inc", "Consulting LLC"]):
        v = db.query(Vendor).filter(Vendor.tenant_id == t.id, Vendor.external_id == f"v{i+1}").first()
        if not v:
            v = Vendor(tenant_id=t.id, external_id=f"v{i+1}", name=name)
            db.add(v)
            db.flush()
            vendors.append(v)
        else:
            vendors.append(v)

    db.commit()
    for v in vendors:
        db.refresh(v)

    # Create bills (duplicates, outliers, round numbers)
    base = date.today() - timedelta(days=90)
    # Same vendor (Acme), same amount 5000, 3 days apart = duplicate
    # Acme at 5000 vs baseline ~1500 = price outlier
    # Round 5000 with no line items = round_number
    bill_specs = [
        (0, 1200, True),   # Acme 1200
        (0, 800, True),    # Acme 800
        (0, 5000, False),  # Acme 5000 - duplicate & outlier & round
        (0, 5000, False),  # Acme 5000 - duplicate (same vendor+amt, 3 days later)
        (1, 450, True), (1, 1100, True), (2, 999, False), (2, 5000, False),
    ]
    for i, (v_idx, amt, has_lines) in enumerate(bill_specs):
        vendor = vendors[v_idx]
        txn = base + timedelta(days=20 + i * 3)  # Sequential, 3 days apart
        ext_id = f"bill-demo-{i+1}"
        existing = db.query(Bill).filter(Bill.tenant_id == t.id, Bill.external_id == ext_id).first()
        if existing:
            continue
        b = Bill(
            tenant_id=t.id,
            vendor_id=vendor.id,
            external_id=ext_id,
            bill_number=f"INV-{1000+i}",
            total_amount=float(amt),
            balance=0,
            txn_date=txn,
            has_line_items=has_lines,
        )
        db.add(b)
    db.commit()
    print("Seeded demo data. Run detection to find anomalies.")
    db.close()


if __name__ == "__main__":
    seed()
