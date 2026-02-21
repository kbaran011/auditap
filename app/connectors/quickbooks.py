"""QuickBooks Online connector — OAuth 2.0 + Bill/Vendor/Payment sync."""
import os
from datetime import datetime
from typing import Any, Optional

import requests
from authlib.integrations.requests_client import OAuth2Session

from app.config import settings

QBO_BASE = "https://quickbooks.api.intuit.com" if settings.qbo_environment == "production" else "https://sandbox-quickbooks.api.intuit.com"
AUTH_URL = "https://appcenter.intuit.com/connect/oauth2"
TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"


def get_oauth_client(client_id: Optional[str] = None, client_secret: Optional[str] = None, redirect_uri: Optional[str] = None):
    """Build OAuth2 client for QuickBooks."""
    return OAuth2Session(
        client_id=client_id or settings.qbo_client_id,
        client_secret=client_secret or settings.qbo_client_secret,
        redirect_uri=redirect_uri or settings.qbo_redirect_uri,
        scope="com.intuit.quickbooks.accounting",
    )


def get_authorization_url(state: Optional[str] = None) -> str:
    """Generate OAuth authorization URL for user to connect their QBO account."""
    client = get_oauth_client()
    url, _ = client.create_authorization_url(
        f"{AUTH_URL}/authorize",
        state=state or "qbo_connect",
        response_type="code",
    )
    return url


def exchange_code_for_tokens(code: str) -> dict[str, Any]:
    """Exchange authorization code for access/refresh tokens."""
    client = get_oauth_client()
    token = client.fetch_token(TOKEN_URL, code=code, grant_type="authorization_code")
    return token


def refresh_tokens(refresh_token: str) -> dict[str, Any]:
    """Refresh access token using refresh token."""
    client = get_oauth_client()
    token = client.refresh_token(TOKEN_URL, refresh_token=refresh_token)
    return token


def _headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}


def get_company_info(access_token: str, realm_id: str) -> dict[str, Any]:
    """Fetch company info (basic validation)."""
    url = f"{QBO_BASE}/v3/company/{realm_id}/companyinfo/{realm_id}"
    r = requests.get(url, headers=_headers(access_token), timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_vendors(access_token: str, realm_id: str) -> list[dict[str, Any]]:
    """Fetch all vendors from QBO."""
    url = f"{QBO_BASE}/v3/company/{realm_id}/query"
    results = []
    start = 1
    page_size = 1000
    while True:
        query = f"SELECT * FROM Vendor STARTPOSITION {start} MAXRESULTS {page_size}"
        r = requests.get(url, params={"query": query}, headers=_headers(access_token), timeout=60)
        r.raise_for_status()
        data = r.json()
        qr = data.get("QueryResponse", {})
        vendors = qr.get("Vendor", [])
        if not vendors:
            break
        results.extend(vendors)
        if len(vendors) < page_size:
            break
        start += page_size
    return results


def fetch_bills(access_token: str, realm_id: str, start_date: Optional[str] = None, end_date: Optional[str] = None):
    """Fetch bills from QBO. Optional date range (YYYY-MM-DD)."""
    url = f"{QBO_BASE}/v3/company/{realm_id}/query"
    results = []
    start = 1
    page_size = 1000
    date_clause = ""
    if start_date:
        date_clause += f" AND TxnDate >= '{start_date}'"
    if end_date:
        date_clause += f" AND TxnDate <= '{end_date}'"
    while True:
        query = f"SELECT * FROM Bill STARTPOSITION {start} MAXRESULTS {page_size} WHERE 1=1 {date_clause}"
        r = requests.get(url, params={"query": query}, headers=_headers(access_token), timeout=60)
        r.raise_for_status()
        data = r.json()
        qr = data.get("QueryResponse", {})
        bills = qr.get("Bill", [])
        if not bills:
            break
        results.extend(bills)
        if len(bills) < page_size:
            break
        start += page_size
    return results


def fetch_bill_payments(access_token: str, realm_id: str, start_date: Optional[str] = None, end_date: Optional[str] = None):
    """Fetch BillPayment transactions from QBO."""
    url = f"{QBO_BASE}/v3/company/{realm_id}/query"
    results = []
    start = 1
    page_size = 1000
    date_clause = ""
    if start_date:
        date_clause += f" AND TxnDate >= '{start_date}'"
    if end_date:
        date_clause += f" AND TxnDate <= '{end_date}'"
    while True:
        query = f"SELECT * FROM BillPayment STARTPOSITION {start} MAXRESULTS {page_size} WHERE 1=1 {date_clause}"
        r = requests.get(url, params={"query": query}, headers=_headers(access_token), timeout=60)
        r.raise_for_status()
        data = r.json()
        qr = data.get("QueryResponse", {})
        payments = qr.get("BillPayment", [])
        if not payments:
            break
        results.extend(payments)
        if len(payments) < page_size:
            break
        start += page_size
    return results


def parse_bill_line_items(bill: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract line items from a QBO Bill."""
    lines = []
    for line in bill.get("Line", []) or []:
        if line.get("DetailType") == "ItemBasedExpenseLineDetail":
            detail = line.get("ItemBasedExpenseLineDetail", {}) or {}
            lines.append({
                "description": line.get("Description"),
                "amount": float(line.get("Amount", 0)),
                "quantity": float(detail.get("Qty", 1)),
                "unit_price": float(detail.get("UnitPrice", 0)) if detail.get("UnitPrice") else None,
            })
        elif line.get("DetailType") == "AccountBasedExpenseLineDetail":
            lines.append({
                "description": line.get("Description"),
                "amount": float(line.get("Amount", 0)),
                "quantity": 1,
                "unit_price": float(line.get("Amount", 0)),
            })
    return lines
