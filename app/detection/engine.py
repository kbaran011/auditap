"""Anomaly detection: duplicates, price outliers, round numbers."""
import json
from datetime import timedelta
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Bill, Vendor, VendorBaseline, Anomaly
from app.pipeline.baselines import compute_baselines


def run_detection(tenant_id: int, db: Session) -> int:
    """Run all anomaly detectors. Returns count of new anomalies."""
    compute_baselines(tenant_id, db)
    count = 0
    count += _detect_duplicates(tenant_id, db)
    count += _detect_price_outliers(tenant_id, db)
    count += _detect_round_numbers(tenant_id, db)
    return count


def _detect_duplicates(tenant_id: int, db: Session) -> int:
    """Flag bills with same vendor + amount within N days (exact or near-duplicate)."""
    window = settings.duplicate_day_window
    bills = (
        db.query(Bill)
        .filter(Bill.tenant_id == tenant_id)
        .order_by(Bill.txn_date)
        .all()
    )
    seen = {}  # (vendor_id, round(amount, 2)) -> [(bill_id, txn_date, amount), ...]
    for b in bills:
        key = (b.vendor_id, round(b.total_amount, 2))
        lst = seen.setdefault(key, [])
        lst.append((b.id, b.txn_date, b.total_amount))
    count = 0
    for key, lst in seen.items():
        if len(lst) < 2:
            continue
        for i, (bid, d, amt) in enumerate(lst):
            for j, (bid2, d2, amt2) in enumerate(lst):
                if i >= j:
                    continue
                if abs((d - d2).days) <= window:
                    # Check we haven't already flagged this bill
                    existing = (
                        db.query(Anomaly)
                        .filter(
                            Anomaly.tenant_id == tenant_id,
                            Anomaly.bill_id == bid,
                            Anomaly.anomaly_type == "duplicate",
                        )
                        .first()
                    )
                    if existing:
                        continue
                    should_alert = amt >= settings.alert_min_amount
                    meta = json.dumps({"related_bill_id": bid2, "duplicate_of": bid})
                    a = Anomaly(
                        tenant_id=tenant_id,
                        bill_id=bid,
                        anomaly_type="duplicate",
                        severity="high" if amt >= 1000 else "medium",
                        amount=amt,
                        confidence_score=0.95,
                        description=f"Possible duplicate: same vendor and amount within {window} days",
                        metadata_json=meta,
                        should_alert=should_alert,
                    )
                    db.add(a)
                    count += 1
                    # No break — continue checking other pairs so bill3, bill4 etc. are also flagged
    return count


def _detect_price_outliers(tenant_id: int, db: Session) -> int:
    """Flag bills where amount is >2σ above vendor baseline."""
    sigma = settings.alert_sigma_threshold
    baselines = (
        db.query(VendorBaseline, Vendor)
        .join(Vendor, VendorBaseline.vendor_id == Vendor.id)
        .filter(Vendor.tenant_id == tenant_id)
        .all()
    )
    count = 0
    for baseline, vendor in baselines:
        if baseline.std_amount is None or baseline.std_amount <= 0:
            continue
        threshold = baseline.avg_amount + sigma * baseline.std_amount
        bills = (
            db.query(Bill)
            .filter(Bill.vendor_id == vendor.id, Bill.total_amount > threshold)
            .all()
        )
        for b in bills:
            z = (b.total_amount - baseline.avg_amount) / baseline.std_amount
            existing = (
                db.query(Anomaly)
                .filter(
                    Anomaly.tenant_id == tenant_id,
                    Anomaly.bill_id == b.id,
                    Anomaly.anomaly_type == "price_creep",
                )
                .first()
            )
            if existing:
                continue
            should_alert = b.total_amount >= settings.alert_min_amount or z >= sigma
            a = Anomaly(
                tenant_id=tenant_id,
                bill_id=b.id,
                anomaly_type="price_creep",
                severity="high" if z >= 3 else "medium",
                amount=b.total_amount,
                confidence_score=min(0.99, 0.5 + z / 10),
                description=f"Amount {b.total_amount:.2f} is {z:.1f}σ above vendor baseline ({baseline.avg_amount:.2f})",
                metadata_json=json.dumps({"z_score": z, "baseline_avg": baseline.avg_amount, "baseline_std": baseline.std_amount}),
                should_alert=should_alert,
            )
            db.add(a)
            count += 1
    return count


def _detect_round_numbers(tenant_id: int, db: Session) -> int:
    """Flag suspicious round-number totals with no line items (potential data entry shortcuts)."""
    bills = db.query(Bill).filter(Bill.tenant_id == tenant_id).all()
    count = 0
    for b in bills:
        if b.has_line_items:
            continue
        amt = b.total_amount
        if amt < settings.alert_min_amount:
            continue
        # Flag any multiple of $500 — covers $500, $1k, $1.5k, $3k, $7.5k, etc.
        if amt % 500 == 0:
            existing = (
                db.query(Anomaly)
                .filter(
                    Anomaly.tenant_id == tenant_id,
                    Anomaly.bill_id == b.id,
                    Anomaly.anomaly_type == "round_number",
                )
                .first()
            )
            if existing:
                continue
            a = Anomaly(
                tenant_id=tenant_id,
                bill_id=b.id,
                anomaly_type="round_number",
                severity="low",
                amount=amt,
                confidence_score=0.6,
                description=f"Round number (${amt:,.0f}) with no line-item detail — consider verifying against source invoice",
                metadata_json=json.dumps({"round_value": amt}),
                should_alert=amt >= settings.alert_min_amount,
            )
            db.add(a)
            count += 1
    return count
