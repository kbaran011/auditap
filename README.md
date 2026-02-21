# A/P Anomaly Detector

Read-only audit layer for accounts payable — find duplicate invoices, price creep, and leaks.

**Pitch**: "I will find $5,000 of leaked money in your past 90 days for free. If I do, the software costs $500/month."

## Quick Start

### 1. Install

```bash
cd "AI PROJECT"
python -m venv .venv
source .venv/bin/activate  # or `.venv\Scripts\activate` on Windows
pip install -r requirements.txt
```

### 2. Configure (optional)

```bash
cp .env.example .env
# Edit .env with your QuickBooks OAuth credentials
```

### 3. Run with demo data (no QuickBooks)

```bash
python scripts/seed_demo.py
uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000 — create tenant, sync (or skip), run detection, view anomalies.

### 4. Run with QuickBooks

1. Create a QuickBooks Developer app at [developer.intuit.com](https://developer.intuit.com)
2. Set redirect URI: `http://localhost:8000/api/auth/qbo/callback`
3. Add credentials to `.env`: `QBO_CLIENT_ID`, `QBO_CLIENT_SECRET`
4. OAuth: Visit `/api/auth/qbo?tenant_id=1` to connect, or manually pass tokens via Connect QBO in the dashboard
5. Create tenant → Connect QBO (realm_id + access_token + refresh_token) → Sync → Detect

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/tenants` | POST | Create tenant |
| `/api/auth/qbo` | GET | Redirect to QBO OAuth |
| `/api/auth/qbo/callback` | GET | OAuth callback (stores tokens) |
| `/api/tenants/{id}/connect-qbo` | POST | Manually store QBO tokens |
| `/api/tenants/{id}/sync` | POST | Sync from QuickBooks |
| `/api/tenants/{id}/detect` | POST | Run anomaly detection |
| `/api/tenants/{id}/anomalies` | GET | List anomalies |
| `/api/tenants/{id}/dashboard` | GET | Dashboard stats |

## Anomaly Types

- **duplicate** — Same vendor + amount within 7 days
- **price_creep** — Amount >2σ above vendor baseline
- **round_number** — Round total ($500, $5K, etc.) with no line items

## Project Structure

```
app/
  main.py           # FastAPI app
  config.py         # Settings
  database.py       # SQLAlchemy
  models/           # Tenant, Vendor, Bill, LineItem, Payment, Anomaly
  connectors/       # QuickBooks OAuth + fetch
  pipeline/         # sync, baselines
  detection/        # duplicate, price_creep, round_number
  api/              # Routes
  templates/        # Dashboard UI
scripts/
  seed_demo.py      # Demo data
```
