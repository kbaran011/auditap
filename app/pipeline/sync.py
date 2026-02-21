"""Sync accounting data into local DB."""
import logging
from datetime import datetime, date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.connectors.quickbooks import (
    fetch_vendors,
    fetch_bills,
    fetch_bill_payments,
    parse_bill_line_items,
    refresh_tokens,
)
from app.models import Tenant, Vendor, Bill, LineItem, Payment

logger = logging.getLogger(__name__)


def sync_tenant(tenant: Tenant, db: Session) -> dict[str, int]:
    """Sync vendors, bills, payments for a tenant from QuickBooks."""
    if not tenant.access_token or not tenant.accounting_realm_id:
        raise ValueError("Tenant missing OAuth tokens or realm_id")

    # Refresh token if expired
    if tenant.token_expires_at and tenant.token_expires_at < datetime.utcnow():
        logger.info("Refreshing expired token for tenant %s", tenant.id)
        new_token = refresh_tokens(tenant.refresh_token)
        tenant.access_token = new_token["access_token"]
        tenant.refresh_token = new_token.get("refresh_token", tenant.refresh_token)
        if new_token.get("expires_at"):
            tenant.token_expires_at = datetime.utcfromtimestamp(new_token["expires_at"])
        db.commit()

    counts = {"vendors": 0, "bills": 0, "payments": 0, "line_items": 0}

    logger.info("Starting sync for tenant %s", tenant.id)

    # Sync vendors
    qbo_vendors = fetch_vendors(tenant.access_token, tenant.accounting_realm_id)
    vendor_map = {}  # qbo_id -> our Vendor
    for v in qbo_vendors:
        ext_id = str(v["Id"])
        existing = db.query(Vendor).filter(
            Vendor.tenant_id == tenant.id,
            Vendor.external_id == ext_id,
        ).first()
        if existing:
            existing.name = v.get("DisplayName") or v.get("CompanyName", "")
            existing.display_name = v.get("DisplayName")
            vendor_map[ext_id] = existing
        else:
            vendor = Vendor(
                tenant_id=tenant.id,
                external_id=ext_id,
                name=v.get("DisplayName") or v.get("CompanyName", "Unknown"),
                display_name=v.get("DisplayName"),
            )
            db.add(vendor)
            db.flush()
            vendor_map[ext_id] = vendor
            counts["vendors"] += 1
    db.commit()
    # IDs are already assigned after flush+commit — no refresh needed

    # Sync bills (last 90 days by default)
    end = date.today()
    start = end - timedelta(days=90)
    qbo_bills = fetch_bills(tenant.access_token, tenant.accounting_realm_id, start.isoformat(), end.isoformat())
    bill_map = {}
    for b in qbo_bills:
        ext_id = str(b["Id"])
        vendor_ref = b.get("VendorRef", {})
        vendor_ext_id = str(vendor_ref.get("value", ""))
        vendor = vendor_map.get(vendor_ext_id)
        if not vendor:
            continue
        txn_date_str = b.get("TxnDate", "")[:10]
        txn_date = datetime.strptime(txn_date_str, "%Y-%m-%d").date() if txn_date_str else date.today()
        total = float(b.get("TotalAmt", 0))
        balance = float(b.get("Balance", 0))
        existing = db.query(Bill).filter(
            Bill.tenant_id == tenant.id,
            Bill.external_id == ext_id,
        ).first()
        if existing:
            existing.total_amount = total
            existing.balance = balance
            existing.txn_date = txn_date
            existing.bill_number = b.get("DocNumber")
            existing.due_date = datetime.strptime(b["DueDate"][:10], "%Y-%m-%d").date() if b.get("DueDate") else None
            existing.sync_at = datetime.utcnow()
            bill = existing
        else:
            bill = Bill(
                tenant_id=tenant.id,
                vendor_id=vendor.id,
                external_id=ext_id,
                bill_number=b.get("DocNumber"),
                total_amount=total,
                balance=balance,
                due_date=datetime.strptime(b["DueDate"][:10], "%Y-%m-%d").date() if b.get("DueDate") else None,
                txn_date=txn_date,
            )
            db.add(bill)
            db.flush()
            counts["bills"] += 1
        bill_map[ext_id] = bill

        # Line items
        lines = parse_bill_line_items(b)
        if lines:
            # Clear and re-insert
            db.query(LineItem).filter(LineItem.bill_id == bill.id).delete()
            for line in lines:
                li = LineItem(
                    bill_id=bill.id,
                    description=line.get("description"),
                    amount=line["amount"],
                    quantity=line.get("quantity", 1),
                    unit_price=line.get("unit_price"),
                )
                db.add(li)
                counts["line_items"] += 1
            bill.has_line_items = True

    db.commit()

    # Bill payments (link to bills via Line.LinkedTxn)
    qbo_payments = fetch_bill_payments(tenant.access_token, tenant.accounting_realm_id, start.isoformat(), end.isoformat())
    for p in qbo_payments:
        total_amt = float(p.get("TotalAmt", 0))
        txn_date_str = p.get("TxnDate", "")[:10]
        txn_date = datetime.strptime(txn_date_str, "%Y-%m-%d").date() if txn_date_str else date.today()
        for line in p.get("Line", []) or []:
            linked = line.get("LinkedTxn") or []
            line_amt = float(line.get("Amount", total_amt))
            for lt in linked:
                if lt.get("TxnType") == "Bill":
                    bill_ext_id = str(lt.get("TxnId", ""))
                    bill = bill_map.get(bill_ext_id)
                    if bill:
                        amt = float(lt.get("Amount", line_amt))
                        ext_id = f"bp-{p['Id']}-{bill.id}"
                        existing = db.query(Payment).filter(Payment.external_id == ext_id).first()
                        if not existing:
                            pay = Payment(
                                bill_id=bill.id,
                                external_id=ext_id,
                                total_amt=amt,
                                txn_date=txn_date,
                            )
                            db.add(pay)
                            counts["payments"] += 1
    db.commit()

    logger.info(
        "Sync complete for tenant %s: %d vendors, %d bills, %d payments, %d line_items",
        tenant.id, counts["vendors"], counts["bills"], counts["payments"], counts["line_items"],
    )
    return counts
