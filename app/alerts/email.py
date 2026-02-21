"""SMTP email alert sender for anomaly notifications."""
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING

from app.config import settings

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from app.models import Tenant, Anomaly

logger = logging.getLogger(__name__)


def send_anomaly_alert(tenant: "Tenant", anomalies: list["Anomaly"]) -> None:
    """Send SMTP email listing high-confidence anomalies to the tenant's alert email."""
    if not settings.smtp_user or not tenant.alert_email:
        return
    if not anomalies:
        return

    n = len(anomalies)
    subject = f"\u26a0\ufe0f {n} anomal{'y' if n == 1 else 'ies'} found in your accounts payable"

    rows_html = ""
    for a in anomalies:
        severity_color = {"high": "#f85149", "medium": "#d29922", "low": "#3fb950"}.get(a.severity, "#8b949e")
        amount_str = f"${a.amount:,.2f}" if a.amount is not None else "-"
        confidence_str = f"{a.confidence_score * 100:.0f}%" if a.confidence_score is not None else "-"
        rows_html += f"""
        <tr>
          <td style="padding:8px;border-bottom:1px solid #30363d;">{a.anomaly_type.replace('_', ' ').title()}</td>
          <td style="padding:8px;border-bottom:1px solid #30363d;color:{severity_color};">{a.severity.upper()}</td>
          <td style="padding:8px;border-bottom:1px solid #30363d;">{amount_str}</td>
          <td style="padding:8px;border-bottom:1px solid #30363d;">{confidence_str}</td>
          <td style="padding:8px;border-bottom:1px solid #30363d;">{a.description or '-'}</td>
        </tr>"""

    html = f"""
    <html>
    <body style="font-family:sans-serif;background:#0d1117;color:#e6edf3;padding:24px;">
      <h2 style="color:#58a6ff;">A/P Anomaly Detector Alert</h2>
      <p>Hello {tenant.name},</p>
      <p>{n} anomal{'y' if n == 1 else 'ies'} requiring your attention {'was' if n == 1 else 'were'} detected in your accounts payable:</p>
      <table style="width:100%;border-collapse:collapse;margin-top:16px;">
        <thead>
          <tr style="background:#161b22;">
            <th style="padding:8px;text-align:left;color:#8b949e;font-size:12px;">TYPE</th>
            <th style="padding:8px;text-align:left;color:#8b949e;font-size:12px;">SEVERITY</th>
            <th style="padding:8px;text-align:left;color:#8b949e;font-size:12px;">AMOUNT</th>
            <th style="padding:8px;text-align:left;color:#8b949e;font-size:12px;">CONFIDENCE</th>
            <th style="padding:8px;text-align:left;color:#8b949e;font-size:12px;">DESCRIPTION</th>
          </tr>
        </thead>
        <tbody>{rows_html}</tbody>
      </table>
      <p style="margin-top:24px;color:#8b949e;font-size:12px;">
        Log in to your A/P Anomaly Detector dashboard to review and dismiss these alerts.
      </p>
    </body>
    </html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.alert_from_email or settings.smtp_user
    msg["To"] = tenant.alert_email
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(msg["From"], [tenant.alert_email], msg.as_string())
        logger.info("Alert email sent to %s for tenant %s (%d anomalies)", tenant.alert_email, tenant.id, n)
    except Exception as exc:
        logger.error("Failed to send alert email for tenant %s: %s", tenant.id, exc)
