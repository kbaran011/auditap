# AI-Powered Accounts Payable (A/P) Anomaly Detector — Project Plan

## Executive Summary

A B2B SaaS that plugs into accounting software, scans all outgoing payments, and flags anomalies—duplicate invoices, vendor overcharges, zombie subscriptions—that cost mid-sized businesses 1–3% of revenue.

**Pitch**: "I will find $5,000 of leaked money in your past 90 days for free. If I do, the software costs $500/month."

**Positioning (critical)**: We are *not* an AP routing or payment tool. We are a **Read-Only Audit Layer** that sits on top of whatever software they use (QuickBooks, Bill.com, Ramp, Tipalti). We catch the mistakes their current system misses.

---

## 1. Problem & Opportunity

| Pain Point | Quantified Impact |
|------------|-------------------|
| Duplicate invoices paid | 0.3–0.8% of A/P spend |
| Vendor price creeping | 0.5–1.5% year-over-year |
| Zombie subscriptions (unused SaaS) | $200–2,000/month per company |
| Unauthorized scope changes | Variable, often 5–15% on affected invoices |

**Why manufacturing/logistics/retail?** High vendor count, complex approval chains, multi-location data sprawl, often legacy or fragmented systems.

---

## 2. Target Customer Profile

- **Firmographic**: $5M–50M revenue, 20–200 employees, 50+ vendors
- **Verticals**: Manufacturing, logistics, multi-location retail
- **Current stack**: QuickBooks, Xero, Sage, NetSuite, or similar
- **Buyer**: CFO, Controller, or Operations Director
- **Trigger**: Audit findings, budget pressure, or desire for automated controls

---

## 3. Product Architecture (High-Level)

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CLIENT ACCOUNTING SOFTWARE                    │
│         (QuickBooks, Xero, Sage, NetSuite — via API/Sync)            │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         EXTRACTION LAYER                             │
│  • OAuth / API connectors per platform                               │
│  • Incremental sync (bills, vendors, payments, subscriptions)        │
│  • OCR fallback: if API returns only total, download attached PDF    │
│    → parse line items via LLM (e.g., Gemini 1.5 Flash) → enrich      │
│  • Raw data → staging tables                                         │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      SQL PIPELINE (Data Engine)                      │
│  • Normalize vendors, line items, payment dates                      │
│  • Build baselines: avg price, frequency, variance by vendor         │
│  • Join bills ↔ payments ↔ vendors                                  │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      ANOMALY DETECTION ENGINE                        │
│  • Rule-based: exact duplicates, near-duplicates, suspicious totals  │
│  • Statistical: outliers vs baseline (price, volume, timing)         │
│  • LLM: compare line items to historical scope, flag creeping        │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       ALERTING & REPORTING                           │
│  • Confidence scores: only alert if high-value (e.g., >$500) OR      │
│    statistical outlier (>2σ) — avoid alert fatigue                   │
│  • Dashboard: anomalies, trends, ROI summary                         │
│  • Email/Slack: high-confidence findings only                        │
│  • Exportable reports for audit trail                                │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 4. Technical Components

### 4.1 Data Connectors

| Platform | Integration Method | Priority |
|----------|-------------------|----------|
| QuickBooks Online | QBO API (OAuth 2.0) | P0 — largest SMB market |
| Xero | Xero API | P0 |
| Sage Intacct | REST API | P1 |
| NetSuite | REST/SuiteQL | P1 — enterprise mid-market |

**Sync scope**: Bills, vendors, bill payments, journal entries (for subscriptions), invoices (for cross-reference).

#### Reality Check: The Line-Item Data Problem

Many mid-market bookkeepers enter only the **total amount** (e.g., $5,000) and attach a PDF—no line-item breakdown in the accounting system. The API then returns a single total, which breaks scope/price-creep detection.

**Fix**: Add an OCR + LLM parsing step to the Extraction Layer. If the API returns only a total and no line items:
1. Download the attached invoice PDF from the accounting system.
2. Use OCR or vision-capable LLM (e.g., Gemini 1.5 Flash) to extract line items (description, quantity, unit price, amount).
3. Populate `line_items` from the parsed result before running anomaly detection.

### 4.2 SQL Pipeline (Data Engine)

Core tables to derive:

- **bills_raw** — raw bill/invoice records
- **vendors** — normalized vendor master
- **payments** — bill payments linked to bills
- **line_items** — line-level detail (amount, description, quantity, unit price)
- **baselines** — per-vendor: avg amount, std dev, payment frequency, last seen

Pipeline jobs:

1. **Extract** — pull from accounting API → raw staging
2. **Transform** — dedupe, normalize, enrich
3. **Baseline** — compute rolling stats (e.g., 90-day window)
4. **Detect** — run anomaly rules and LLM checks

### 4.3 Anomaly Detection Logic

| Anomaly Type | Method | Example |
|--------------|--------|---------|
| Duplicate invoice | Exact/near match on vendor + amount + date | Same vendor, same amount, within 7 days |
| Price creeping | Statistical (z-score) vs baseline | Unit price 2σ above 90-day avg |
| Zombie subscriptions | Frequency + amount + no usage signal | Fixed monthly charge, no login/activity |
| Scope drift | LLM comparison | "Consulting" line item vs past "Hourly support" |
| Round numbers / suspicious totals | Heuristics | $5,000.00 exactly, no line-item breakdown |

**LLM role**: For invoices with line-item detail, send to LLM with:
- Current line items
- Historical baseline (same vendor, last N invoices)
- Prompt: "Flag if any line suggests price increase, scope change, or new unauthorized charge."

#### Reality Check: Alert Fatigue

If the system flags every $5 variance, the CFO will mute your emails within a week.

**Fix**: Implement strict confidence and value thresholds. Only trigger alerts when:
- **Value threshold**: Anomaly amount > $500 (configurable per customer), or
- **Statistical threshold**: Outlier > 2 standard deviations from baseline.
- Store all findings in the dashboard; only send push/email alerts for high-confidence, high-impact items.

### 4.4 Tech Stack Recommendations

| Layer | Suggestion | Rationale |
|-------|------------|-----------|
| Backend | Python (FastAPI) or Node.js | API-heavy, async-friendly |
| Database | PostgreSQL + dbt or Airflow | Robust SQL, pipeline orchestration |
| LLM | OpenAI / Anthropic API | Strong at structured comparison tasks |
| Connectors | Merged, Plaid, or direct API | Merged covers QBO, Xero, NetSuite |
| Hosting | Vercel/Railway + managed Postgres | Fast to ship, scales with usage |
| Auth | Clerk, Auth0, or Supabase Auth | Multi-tenant, OAuth for accounting links |

---

## 5. Go-to-Market & Pricing

### 5.1 Free Audit (Lead Gen)

- **Offer**: "90-day audit. We find $5K+ in leaks or you pay nothing."
- **Process**: Connect read-only to their accounting system → run pipeline → deliver report in 5–7 days
- **Conversion**: If findings > $5K, pitch $500/month ongoing monitoring

### 5.2 Pricing

| Tier | Price | Features |
|------|-------|----------|
| Audit only | Free | One-time 90-day scan, PDF report |
| Guardian | $500/mo | Continuous monitoring, weekly alerts, dashboard |
| Enterprise | Custom | Multi-entity, SSO, SLA, dedicated support |

#### Reality Check: Positioning Against Giants

Bill.com, Ramp, Tipalti, and others dominate AP. If customers think you are replacing their AP system, they will say no.

**Fix**: Protect your niche. Emphasize in all messaging: *"Read-Only Audit Layer that sits on top of whatever you use."* You catch mistakes their current system misses—you do not route invoices, approve payments, or replace their AP workflow.

### 5.3 Why Low Churn

- **Ongoing value**: New vendors, new invoices, new subscriptions every month
- **Sunk cost**: Once connected, switching cost is high
- **Fear of leakage**: Turning off = admitting they'll lose visibility

---

## 6. Development Phases

### Phase 1: MVP (8–12 weeks)

- [ ] Single accounting connector (QuickBooks Online recommended)
- [ ] SQL pipeline: bills, vendors, payments → baselines
- [ ] OCR/LLM fallback for bills with PDF attachment but no line items (P1 for Phase 2 if timeline pressure)
- [ ] 3 anomaly types: duplicates, price outliers, round-number heuristics
- [ ] Simple dashboard (anomaly list + basic stats)
- [ ] Manual onboarding (API keys, no self-serve yet)

**Outcome**: Can run a live 90-day audit for 1–2 pilot customers.

### Phase 2: LLM + Productization (6–8 weeks)

- [ ] OCR/LLM PDF parsing for line-item extraction (when API returns only totals)
- [ ] LLM integration for scope/line-item comparison
- [ ] Self-serve signup + OAuth flow
- [ ] Email alerts with strict thresholds (>$500 or >2σ) to prevent alert fatigue
- [ ] Xero connector

**Outcome**: Scalable product, repeatable sales motion.

### Phase 3: Growth (Ongoing)

- [ ] NetSuite, Sage connectors
- [ ] Zombie subscription detection (needs usage data or heuristics)
- [ ] Multi-entity support
- [ ] Integrations: Slack, export to CSV/Excel

---

## 7. Risk & Mitigation

| Risk | Mitigation |
|------|------------|
| Accounting API rate limits | Batch sync, incremental updates, respect rate headers |
| **Line-item data missing** | OCR + LLM (e.g., Gemini 1.5 Flash) to parse attached PDFs when API returns only totals |
| Data quality (messy vendor names, sparse line items) | Fuzzy matching, fallback to bill-level analysis; OCR enriches where possible |
| **Alert fatigue / false positives** | Strict thresholds: alert only if amount >$500 OR statistical outlier >2σ; all findings in dashboard, push alerts for high-confidence only |
| Compliance (read-only access, audit trail) | Document data handling, SOC2 path if enterprise |
| LLM cost at scale | Cache baselines, batch prompts, use smaller models (e.g., Flash) where possible |

---

## 8. Success Metrics

| Metric | Target (Year 1) |
|--------|------------------|
| Free audits completed | 50 |
| Audit → paid conversion | 25–40% |
| MRR | $25K+ |
| Churn (monthly) | < 3% |
| Avg findings per audit | $8K+ (validates value prop) |

---

## 9. Next Steps

1. **Validate**: Talk to 5–10 target customers (CFOs, controllers) about current A/P pain and willingness to run a free audit.
2. **Pick stack**: Finalize backend, DB, and first connector (QBO vs Xero).
3. **Build Phase 1**: Implement extraction → SQL pipeline → 3 anomaly types → basic UI.
4. **Run pilots**: 2–3 free audits, refine detection rules and report format.
5. **Iterate**: Add LLM, productize onboarding, then scale outbound.

---

*Document version: 1.1 | Last updated: Feb 20, 2025 | + Gemini reality checks (OCR, positioning, alert fatigue)*
