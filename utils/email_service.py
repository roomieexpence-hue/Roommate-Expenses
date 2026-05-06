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
    year: int = None,
    month: int = None,
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
    
    # Get current month/year if not provided
    if year is None or month is None:
        now = datetime.now()
        year = now.year
        month = now.month

    subject = f"💸 {updated_by} added ₹{amount:,.0f} – RoomiePay Update ({datetime(year, month, 1).strftime('%B %Y')})"
    html_body = _build_html(updated_by, amount, description, category, date_str, totals, members, settlement_txns, year, month)

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


def send_month_end_summary(
    year: int,
    month: int,
    monthly_totals: dict,
    settlement_txns: list[dict],
    members: list[str],
) -> bool:
    """
    Send month-end summary email with total expenses and settlement info.
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
    
    month_name = datetime(year, month, 1).strftime("%B %Y")
    subject = f"📊 {month_name} - RoomiePay Monthly Summary"
    html_body = _build_month_end_html(year, month, monthly_totals, settlement_txns, members)

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
        print(f"[email_service] Month-end summary sent to {recipients}")
        return True
    except Exception as e:
        print(f"[email_service] Failed to send month-end email: {e}")
        return False


def _build_month_end_html(year: int, month: int, monthly_totals: dict, settlement_txns: list[dict], members: list[str]) -> str:
    """Build HTML for month-end summary email."""
    month_name = datetime(year, month, 1).strftime("%B %Y")
    
    rows = ""
    for m in members:
        val = monthly_totals.get(m, 0)
        rows += f"<tr><td style='padding:10px 12px;border-bottom:1px solid #e5e7eb'><strong>{m}</strong></td><td style='padding:10px 12px;border-bottom:1px solid #e5e7eb;text-align:right;font-weight:600'>₹{val:,.0f}</td></tr>"

    settle_rows = ""
    for t in settlement_txns:
        settle_rows += (
            f"<tr style='border-bottom:1px solid #e5e7eb'>"
            f"<td style='padding:10px 12px;text-align:center'><strong>{t['payer']}</strong></td>"
            f"<td style='padding:10px 12px;text-align:center;color:#999'>→</td>"
            f"<td style='padding:10px 12px;text-align:center'><strong>{t['receiver']}</strong></td>"
            f"<td style='padding:10px 12px;text-align:right;font-weight:bold;color:#16a34a'>₹{t['amount']:,.0f}</td>"
            f"</tr>"
        )
    
    settle_section = (
        f"""<div style="margin-top:24px;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px;overflow:hidden">
          <h3 style="margin:0 0 12px 0;color:#15803d;font-size:16px">Settlement Summary</h3>
          <table border="0" cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse">
            <tr style="background:#dcfce7;border-bottom:1px solid #bbf7d0">
              <th style="padding:10px 12px;text-align:left;font-weight:600;color:#15803d">Payer</th>
              <th style="padding:10px 12px;text-align:center;color:#15803d"></th>
              <th style="padding:10px 12px;text-align:left;font-weight:600;color:#15803d">Receiver</th>
              <th style="padding:10px 12px;text-align:right;font-weight:600;color:#15803d">Amount</th>
            </tr>
            {settle_rows}
          </table>
        </div>"""
        if settle_rows
        else "<div style='background:#dcfce7;border-radius:8px;padding:16px;text-align:center;color:#15803d;border:1px solid #bbf7d0'><strong>✅ All square! 🎉</strong></div>"
    )

    overall_total = monthly_totals.get('overall', 0)
    
    return f"""<!DOCTYPE html>
<html style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Roboto','Helvetica Neue',sans-serif">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <style>
    body {{ margin: 0; padding: 0; background: #f3f4f6; }}
    .container {{ max-width: 600px; margin: 20px auto; background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 10px 30px rgba(0,0,0,0.1); }}
    .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: #fff; padding: 32px 24px; text-align: center; }}
    .header h1 {{ margin: 0 0 8px 0; font-size: 28px; font-weight: 700; }}
    .header p {{ margin: 0; font-size: 14px; opacity: 0.9; }}
    .body {{ padding: 32px 24px; color: #1f2937; }}
    .stat-box {{ background: #eff6ff; border-left: 4px solid #3b82f6; border-radius: 8px; padding: 16px; margin-bottom: 24px; }}
    .stat-label {{ color: #666; font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; }}
    .stat-value {{ font-size: 32px; font-weight: 700; color: #1e40af; }}
    .section-title {{ font-size: 14px; font-weight: 700; color: #6b7280; text-transform: uppercase; letter-spacing: 0.5px; margin: 24px 0 12px 0; }}
    .footer {{ background: #f9fafb; border-top: 1px solid #e5e7eb; padding: 16px 24px; text-align: center; font-size: 12px; color: #9ca3af; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>📊 Monthly Summary</h1>
      <p>{month_name}</p>
    </div>
    
    <div class="body">
      <div class="stat-box">
        <div class="stat-label">Total Expense</div>
        <div class="stat-value">₹{overall_total:,.0f}</div>
      </div>

      <div class="section-title">Member Spending Breakdown</div>
      <table border="0" cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse;border:1px solid #e5e7eb;border-radius:8px;overflow:hidden">
        <tr style="background:#f3f4f6">
          <th style="padding:12px;text-align:left;font-weight:600;border-bottom:1px solid #e5e7eb">Member</th>
          <th style="padding:12px;text-align:right;font-weight:600;border-bottom:1px solid #e5e7eb">Spent</th>
        </tr>
        {rows}
        <tr style="background:#f3f4f6;border-top:2px solid #e5e7eb;font-weight:700">
          <td style="padding:12px">TOTAL</td>
          <td style="padding:12px;text-align:right">₹{overall_total:,.0f}</td>
        </tr>
      </table>

      {settle_section}

      <p style="font-size:13px;color:#6b7280;margin-top:32px;line-height:1.8;border-top:1px solid #e5e7eb;padding-top:16px">
        <strong>📋 Summary:</strong><br>
        {month_name} expenses have been finalized. Please review the settlement above and complete all pending payments before the next billing cycle.
      </p>
    </div>

    <div class="footer">
      <p style="margin:0">RoomiePay • Shared Expense Tracker<br><span style="font-size:11px">This is an automated message. Please don't reply to this email.</span></p>
    </div>
  </div>
</body>
</html>"""


def _build_html(updated_by, amount, description, category, date_str, totals, members, settlement_txns, year=None, month=None) -> str:
    month_name = ""
    if year and month:
        month_name = f" ({datetime(year, month, 1).strftime('%B %Y')})"
    
    rows = ""
    for m in members:
        val = totals.get(m, 0)
        rows += f"<tr><td style='padding:10px 12px;border-bottom:1px solid #e5e7eb'><strong>{m}</strong></td><td style='padding:10px 12px;border-bottom:1px solid #e5e7eb;text-align:right;font-weight:600'>₹{val:,.0f}</td></tr>"

    settle_rows = ""
    for t in settlement_txns:
        settle_rows += (
            f"<tr style='border-bottom:1px solid #e5e7eb'>"
            f"<td style='padding:10px 12px;text-align:center'><strong>{t['payer']}</strong></td>"
            f"<td style='padding:10px 12px;text-align:center;color:#999'>→</td>"
            f"<td style='padding:10px 12px;text-align:center'><strong>{t['receiver']}</strong></td>"
            f"<td style='padding:10px 12px;text-align:right;font-weight:bold;color:#16a34a'>₹{t['amount']:,.0f}</td>"
            f"</tr>"
        )
    settle_section = (
        f"""<div style="margin-top:24px;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px;overflow:hidden">
          <h3 style="margin:0 0 12px 0;color:#15803d;font-size:16px">Settlement Needed</h3>
          <table border="0" cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse">
            <tr style="background:#dcfce7;border-bottom:1px solid #bbf7d0">
              <th style="padding:10px 12px;text-align:left;font-weight:600;color:#15803d">Payer</th>
              <th style="padding:10px 12px;text-align:center;color:#15803d"></th>
              <th style="padding:10px 12px;text-align:left;font-weight:600;color:#15803d">Receiver</th>
              <th style="padding:10px 12px;text-align:right;font-weight:600;color:#15803d">Amount</th>
            </tr>
            {settle_rows}
          </table>
        </div>"""
        if settle_rows
        else "<div style='background:#dcfce7;border-radius:8px;padding:16px;text-align:center;color:#15803d;border:1px solid #bbf7d0'><strong>✅ All members are square!</strong> 🎉</div>"
    )

    overall = totals.get('overall', 0)
    
    return f"""<!DOCTYPE html>
<html style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Roboto','Helvetica Neue',sans-serif">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <style>
    body {{ margin: 0; padding: 0; background: #f3f4f6; }}
    .container {{ max-width: 600px; margin: 20px auto; background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 10px 30px rgba(0,0,0,0.1); }}
    .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: #fff; padding: 32px 24px; text-align: center; }}
    .header h1 {{ margin: 0 0 8px 0; font-size: 28px; font-weight: 700; letter-spacing: -0.5px; }}
    .header p {{ margin: 0; font-size: 14px; opacity: 0.9; }}
    .body {{ padding: 32px 24px; color: #1f2937; }}
    .transaction-box {{ background: #f0f9ff; border-left: 4px solid #3b82f6; border-radius: 8px; padding: 16px; margin-bottom: 24px; }}
    .transaction-box p {{ margin: 0; font-size: 15px; line-height: 1.6; }}
    .amount {{ font-size: 24px; font-weight: 700; color: #16a34a; }}
    .section-title {{ font-size: 14px; font-weight: 700; color: #6b7280; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px; margin-top: 24px; }}
    .footer {{ background: #f9fafb; border-top: 1px solid #e5e7eb; padding: 16px 24px; text-align: center; font-size: 12px; color: #9ca3af; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>💸 RoomiePay Update{month_name}</h1>
      <p>{date_str}</p>
    </div>
    
    <div class="body">
      <div class="transaction-box">
        <p><strong>{updated_by}</strong> added <span class="amount">₹{amount:,.0f}</span></p>
        <p style="margin-top:8px;font-size:13px;color:#666"><strong>Category:</strong> {category}{' – ' + description if description else ''}</p>
      </div>

      <div class="section-title">Member Totals for {month_name if month_name else 'Current Month'}</div>
      <table border="0" cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse;border:1px solid #e5e7eb;border-radius:8px;overflow:hidden">
        <tr style="background:#f3f4f6">
          <th style="padding:12px;text-align:left;font-weight:600;border-bottom:1px solid #e5e7eb">Member</th>
          <th style="padding:12px;text-align:right;font-weight:600;border-bottom:1px solid #e5e7eb">Total</th>
        </tr>
        {rows}
        <tr style="background:#f3f4f6;border-top:2px solid #e5e7eb;font-weight:700">
          <td style="padding:12px">OVERALL</td>
          <td style="padding:12px;text-align:right">₹{overall:,.0f}</td>
        </tr>
      </table>

      {settle_section}

      <p style="font-size:13px;color:#6b7280;margin-top:32px;line-height:1.8;border-top:1px solid #e5e7eb;padding-top:16px">
        <strong>💡 Next Steps:</strong><br>
        Review the settlement above and make payments accordingly. Keep track of who owes whom to settle monthly expenses fairly.
      </p>
    </div>

    <div class="footer">
      <p style="margin:0">RoomiePay • Shared Expense Tracker<br><span style="font-size:11px">This is an automated message. Please don't reply to this email.</span></p>
    </div>
  </div>
</body>
</html>"""
