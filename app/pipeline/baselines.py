"""Compute vendor baselines for anomaly detection."""
from datetime import date, timedelta
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Bill, Vendor, VendorBaseline


def compute_baselines(tenant_id: int, db: Session) -> int:
    """Compute 90-day baselines per vendor. Returns count of baselines created/updated."""
    end = date.today()
    start = end - timedelta(days=settings.baseline_days)
    vendors = db.query(Vendor).filter(Vendor.tenant_id == tenant_id).all()
    count = 0
    for vendor in vendors:
        rows = (
            db.query(
                func.count(Bill.id).label("cnt"),
                func.avg(Bill.total_amount).label("avg_amt"),
                func.min(Bill.total_amount).label("min_amt"),
                func.max(Bill.total_amount).label("max_amt"),
            )
            .filter(
                Bill.vendor_id == vendor.id,
                Bill.txn_date >= start,
                Bill.txn_date <= end,
            )
            .first()
        )
        if not rows or rows.cnt == 0:
            continue
        # Compute sample std dev (Bessel's correction: divide by n-1)
        amounts = (
            db.query(Bill.total_amount)
            .filter(
                Bill.vendor_id == vendor.id,
                Bill.txn_date >= start,
                Bill.txn_date <= end,
            )
            .all()
        )
        vals = [a[0] for a in amounts]
        n = len(vals)
        avg = sum(vals) / n
        variance = sum((x - avg) ** 2 for x in vals) / (n - 1) if n > 1 else 0
        std = variance ** 0.5
        baseline = (
            db.query(VendorBaseline)
            .filter(
                VendorBaseline.vendor_id == vendor.id,
                VendorBaseline.window_start == start,
                VendorBaseline.window_end == end,
            )
            .first()
        )
        if baseline:
            baseline.avg_amount = avg
            baseline.std_amount = std
            baseline.min_amount = rows.min_amt
            baseline.max_amount = rows.max_amt
            baseline.payment_count = n
        else:
            baseline = VendorBaseline(
                vendor_id=vendor.id,
                window_start=start,
                window_end=end,
                avg_amount=avg,
                std_amount=std,
                min_amount=rows.min_amt,
                max_amount=rows.max_amt,
                payment_count=n,
            )
            db.add(baseline)
            count += 1
    db.commit()
    return count
