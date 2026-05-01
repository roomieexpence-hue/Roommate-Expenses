"""
email_service.py
----------------
Send HTML email notifications via Gmail SMTP.
"""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime


def send_expense_notification(
    updated_by: str,
    amount: float,
    description: str,
    category: str,
    date_str: str,
    totals: dict,
    members: list[str],
    settlement_txns: list[dict],
) -> bool:
    """
    Send an HTML email to all configured recipients.
    Returns True on success, False on failure.
    """
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port   = int(os.getenv("SMTP_PORT", 587))
    sender      = os.getenv("EMAIL_SENDER", "")
    password    = os.getenv("EMAIL_PASSWORD", "")
    recipients_raw = os.getenv("EMAIL_RECIPIENTS", "")

    if not sender or not password or not recipients_raw:
        print("[email_service] SMTP credentials not configured – skipping email.")
        return False

    recipients = [r.strip() for r in recipients_raw.split(",") if r.strip()]

    subject = f"💸 {updated_by} added ₹{amount:,.0f} – RoomiePay Update"
    html_body = _build_html(updated_by, amount, description, category, date_str, totals, members, settlement_txns)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, recipients, msg.as_string())
        print(f"[email_service] Notification sent to {recipients}")
        return True
    except Exception as e:
        print(f"[email_service] Failed to send email: {e}")
        return False


def _build_html(updated_by, amount, description, category, date_str, totals, members, settlement_txns) -> str:
    rows = ""
    for m in members:
        val = totals.get(m, 0)
        rows += f"<tr><td>{m}</td><td>₹{val:,.0f}</td></tr>"

    settle_rows = ""
    for t in settlement_txns:
        settle_rows += (
            f"<tr><td>{t['payer']}</td><td>→</td>"
            f"<td>{t['receiver']}</td><td>₹{t['amount']:,.0f}</td></tr>"
        )
    settle_section = (
        f"""
        <h3 style="margin-top:24px">Settlement Summary</h3>
        <table border="0" cellpadding="6" cellspacing="0" style="border-collapse:collapse;width:100%">
          <tr style="background:#f0f0f0"><th>Payer</th><th></th><th>Receiver</th><th>Amount</th></tr>
          {settle_rows}
        </table>"""
        if settle_rows
        else "<p style='color:#666'>All members are square! 🎉</p>"
    )

    return f"""
<!DOCTYPE html>
<html>
<body style="font-family:'Segoe UI',sans-serif;max-width:600px;margin:auto;padding:20px;background:#f9f9f9">
  <div style="background:#1a1a2e;color:#fff;padding:24px;border-radius:12px 12px 0 0">
    <h2 style="margin:0">💸 RoomiePay Update</h2>
    <p style="margin:4px 0 0;opacity:.7">{date_str}</p>
  </div>
  <div style="background:#fff;padding:24px;border-radius:0 0 12px 12px;box-shadow:0 2px 12px rgba(0,0,0,.08)">
    <p><strong>{updated_by}</strong> added <strong style="color:#16a34a">₹{amount:,.0f}</strong>
       in <em>{category}</em>{(' – ' + description) if description else ''}.</p>

    <h3 style="margin-top:24px">Member Totals</h3>
    <table border="0" cellpadding="6" cellspacing="0"
           style="border-collapse:collapse;width:100%;background:#f8fafc;border-radius:8px">
      <tr style="background:#e2e8f0"><th style="text-align:left">Member</th><th style="text-align:left">Total</th></tr>
      {rows}
      <tr style="border-top:2px solid #cbd5e1;font-weight:bold">
        <td>Overall</td><td>₹{totals.get('overall', 0):,.0f}</td>
      </tr>
    </table>

    {settle_section}

    <p style="font-size:12px;color:#999;margin-top:32px">Sent by RoomiePay • Don't reply to this email</p>
  </div>
</body>
</html>"""
