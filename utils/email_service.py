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
        rows += f"<tr><td>{m}</td><td>₹{val:,.0f}</td></tr>"

    settle_rows = ""
    for t in settlement_txns:
        settle_rows += (
            f"<tr><td>{t['payer']}</td><td>→</td>"
            f"<td>{t['receiver']}</td><td style='font-weight:bold;color:#16a34a'>₹{t['amount']:,.0f}</td></tr>"
        )
    
    settle_section = (
        f"""
        <h3 style="margin-top:24px">Settlement Needed</h3>
        <table border="0" cellpadding="8" cellspacing="0" style="border-collapse:collapse;width:100%;background:#f0fdf4;border-left:4px solid #16a34a">
          <tr style="background:#dcfce7"><th style="text-align:left">Payer</th><th></th><th style="text-align:left">Receiver</th><th style="text-align:right">Amount</th></tr>
          {settle_rows}
        </table>"""
        if settle_rows
        else "<p style='color:#666;background:#dcfce7;padding:12px;border-radius:8px'>✅ All members are square! 🎉</p>"
    )

    overall_total = monthly_totals.get('overall', 0)
    
    return f"""
<!DOCTYPE html>
<html>
<body style="font-family:'Segoe UI',sans-serif;max-width:600px;margin:auto;padding:20px;background:#f9f9f9">
  <div style="background:#1a1a2e;color:#fff;padding:24px;border-radius:12px 12px 0 0">
    <h1 style="margin:0">📊 RoomiePay Monthly Summary</h1>
    <p style="margin:8px 0 0;opacity:.8;font-size:18px">{month_name}</p>
  </div>
  <div style="background:#fff;padding:24px;border-radius:0 0 12px 12px;box-shadow:0 2px 12px rgba(0,0,0,.08)">
    
    <div style="background:#eff6ff;border-left:4px solid #3b82f6;padding:16px;border-radius:8px;margin-bottom:24px">
      <p style="margin:0;color:#666">Total Expense for {month_name}</p>
      <p style="margin:8px 0 0;font-size:32px;font-weight:bold;color:#1e40af">₹{overall_total:,.0f}</p>
    </div>

    <h3 style="margin-top:0;margin-bottom:12px">Member Spending</h3>
    <table border="0" cellpadding="8" cellspacing="0"
           style="border-collapse:collapse;width:100%;background:#f8fafc;border-radius:8px">
      <tr style="background:#e2e8f0"><th style="text-align:left">Member</th><th style="text-align:right">Spent</th></tr>
      {rows}
      <tr style="border-top:2px solid #cbd5e1;font-weight:bold;background:#e2e8f0">
        <td>Total</td><td style="text-align:right">₹{overall_total:,.0f}</td>
      </tr>
    </table>

    {settle_section}

    <p style="font-size:11px;color:#999;margin-top:32px;line-height:1.6">
      This is an automated summary from RoomiePay.<br>
      Month: {month}/{year} | Please settle payments accordingly.
    </p>
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
    <h2 style="margin:0">💸 RoomiePay Update{month_name}</h2>
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
    
    # Fall back to local file (development)
    creds_file = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
    if os.path.exists(creds_file):
        creds = service_account.Credentials.from_service_account_file(
            creds_file, scopes=SCOPES
        )
        return build("sheets", "v4", credentials=creds)
    
    raise Exception(
        f"❌ Google credentials not found!\n"
        f"   • Local: '{creds_file}' file doesn't exist\n"
        f"   • Vercel: GOOGLE_CREDENTIALS_B64 env var is not set\n"
        f"   See VERCEL_SETUP.md for setup instructions."
    )


def _sheet_id(service, spreadsheet_id: str) -> int:
    """Return the numeric sheetId of the first sheet."""
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    return meta["sheets"][0]["properties"]["sheetId"]


# ─── Initialise ───────────────────────────────────────────────────────────────

def initialise_sheet(spreadsheet_id: str, members: list[str]) -> None:
    """
    Ensure the header row exists with member names and coloured backgrounds.
    Safe to call multiple times – skips if headers already present.
    """
    service = _get_service()
    headers = ["Date"] + members

    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range="Sheet1!A1:Z1")
        .execute()
    )
    existing = result.get("values", [])
    if existing and existing[0][:len(headers)] == headers:
        return  # already initialised

    # Write header text
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range="Sheet1!A1",
        valueInputOption="RAW",
        body={"values": [headers]},
    ).execute()

    # Apply colours to header cells
    sid = _sheet_id(service, spreadsheet_id)
    requests = []
    for col_idx, _ in enumerate(headers):
        color = (
            {"red": 0.15, "green": 0.15, "blue": 0.15}  # dark for Date col
            if col_idx == 0
            else HEADER_COLORS[(col_idx - 1) % len(HEADER_COLORS)]
        )
        requests.append(
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sid,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                        "startColumnIndex": col_idx,
                        "endColumnIndex": col_idx + 1,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": color,
                            "textFormat": {
                                "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                                "bold": True,
                            },
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat)",
                }
            }
        )

    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id, body={"requests": requests}
    ).execute()


# ─── Sync members with code ───────────────────────────────────────────────────

def sync_sheet_members(spreadsheet_id: str, members: list[str]) -> None:
    """
    Ensure the Google Sheet headers match the current members list.
    
    This is the KEY function that keeps the sheet in sync with code:
    • If a member was accidentally deleted from the sheet, it gets recreated
    • If members in code change, the sheet is updated to match
    • All data rows are extended to match the new structure
    
    Safe to call anytime, including before every add_expense().
    """
    service = _get_service()
    required_headers = ["Date"] + members
    
    # Read current sheet
    all_data = _read_all(service, spreadsheet_id)
    
    if not all_data:
        # Sheet is empty, initialize it
        initialise_sheet(spreadsheet_id, members)
        return
    
    current_headers = all_data[0]
    
    # Check if headers match exactly
    if current_headers == required_headers:
        return  # Already in sync
    
    # Headers don't match - update them
    all_data[0] = required_headers
    
    # Extend all data rows to match the new header length
    for i in range(1, len(all_data)):
        while len(all_data[i]) < len(required_headers):
            all_data[i].append("")
        # Trim to exact length in case it was longer
        all_data[i] = all_data[i][:len(required_headers)]
    
    # Write the updated sheet back
    service.spreadsheets().values().clear(
        spreadsheetId=spreadsheet_id, range="Sheet1"
    ).execute()
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range="Sheet1!A1",
        valueInputOption="RAW",
        body={"values": all_data},
    ).execute()
    
    # Reapply header colors
    sid = _sheet_id(service, spreadsheet_id)
    requests = []
    for col_idx, _ in enumerate(required_headers):
        color = (
            {"red": 0.15, "green": 0.15, "blue": 0.15}  # dark for Date col
            if col_idx == 0
            else HEADER_COLORS[(col_idx - 1) % len(HEADER_COLORS)]
        )
        requests.append(
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sid,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                        "startColumnIndex": col_idx,
                        "endColumnIndex": col_idx + 1,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": color,
                            "textFormat": {
                                "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                                "bold": True,
                            },
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat)",
                }
            }
        )
    
    service.spreadsheets().batchUpdate(
        spreadsheet_id=spreadsheet_id, body={"requests": requests}
    ).execute()


# ─── Core write ───────────────────────────────────────────────────────────────

def add_expense(
    spreadsheet_id: str,
    members: list[str],
    member_name: str,
    amount: float,
    date_str: str,          # YYYY-MM-DD
) -> None:
    """
    Add an expense for *member_name* on *date_str*.

    • Syncs sheet members with current code members first (recreates deleted columns)
    • If the date row exists, append amount with '+'.
    • If not, create a new row.
    """
    service = _get_service()
    
    # IMPORTANT: Sync members first to ensure all columns exist
    # This recreates any accidentally deleted member columns
    sync_sheet_members(spreadsheet_id, members)
    
    all_data = _read_all(service, spreadsheet_id)

    headers = all_data[0] if all_data else ["Date"] + members
    col_idx = headers.index(member_name)   # raises ValueError if not found

    # Find existing row for this date
    row_idx = None
    for i, row in enumerate(all_data[1:], start=1):
        if row and row[0] == date_str:
            row_idx = i
            break

    amount_str = str(int(amount)) if amount == int(amount) else str(amount)

    if row_idx is not None:
        # Extend row to ensure it has enough columns
        row = all_data[row_idx]
        while len(row) <= col_idx:
            row.append("")

        existing = row[col_idx].strip()
        row[col_idx] = f"{existing}+{amount_str}" if existing else amount_str
        all_data[row_idx] = row
    else:
        # Build new row
        new_row = [""] * (len(headers))
        new_row[0] = date_str
        new_row[col_idx] = amount_str
        all_data.append(new_row)
        # Sort by date (skip header)
        data_rows = sorted(all_data[1:], key=lambda r: r[0] if r else "")
        all_data = [all_data[0]] + data_rows

    # Write back entire sheet (simplest approach for correctness)
    service.spreadsheets().values().clear(
        spreadsheetId=spreadsheet_id, range="Sheet1"
    ).execute()
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range="Sheet1!A1",
        valueInputOption="RAW",
        body={"values": all_data},
    ).execute()


def add_member_column(spreadsheet_id: str, member_name: str, col_idx: int) -> None:
    """Add a new member column to the sheet with colored header."""
    service = _get_service()
    all_data = _read_all(service, spreadsheet_id)

    if not all_data:
        return

    # Add member to header
    if len(all_data[0]) <= col_idx:
        all_data[0].extend([""] * (col_idx + 1 - len(all_data[0])))
    all_data[0][col_idx] = member_name

    # Ensure all rows have the new column
    for row in all_data[1:]:
        while len(row) <= col_idx:
            row.append("")

    # Write back entire sheet
    service.spreadsheets().values().clear(
        spreadsheetId=spreadsheet_id, range="Sheet1"
    ).execute()
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range="Sheet1!A1",
        valueInputOption="RAW",
        body={"values": all_data},
    ).execute()

    # Apply color to the new header cell
    sid = _sheet_id(service, spreadsheet_id)
    color = HEADER_COLORS[(col_idx - 1) % len(HEADER_COLORS)]
    
    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={
            "requests": [
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sid,
                            "startRowIndex": 0,
                            "endRowIndex": 1,
                            "startColumnIndex": col_idx,
                            "endColumnIndex": col_idx + 1,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColor": color,
                                "textFormat": {
                                    "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                                    "bold": True,
                                },
                            }
                        },
                        "fields": "userEnteredFormat(backgroundColor,textFormat)",
                    }
                }
            ]
        },
    ).execute()


def expense_exists(
    spreadsheet_id: str,
    members: list[str],
    member_name: str,
    amount: float,
    date_str: str,
) -> bool:
    """Check if the exact same expense (member, amount, date) already exists."""
    try:
        service = _get_service()
        all_data = _read_all(service, spreadsheet_id)
        
        if not all_data or len(all_data) < 2:
            return False
        
        headers = all_data[0]
        col_idx = headers.index(member_name) if member_name in headers else -1
        
        if col_idx == -1:
            return False
        
        amount_str = str(int(amount)) if amount == int(amount) else str(amount)
        
        # Find the row for this date
        for row in all_data[1:]:
            if row and len(row) > 0 and row[0] == date_str:
                if len(row) > col_idx:
                    cell_content = row[col_idx].strip()
                    # Check if the exact amount exists in the cell
                    # Cell might contain "100" or "100+50" etc
                    amounts = cell_content.split('+')
                    if amount_str in amounts:
                        return True
                break
        
        return False
    except Exception:
        return False


# ─── Reads ────────────────────────────────────────────────────────────────────

def _read_all(service, spreadsheet_id: str) -> list[list[str]]:
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range="Sheet1")
        .execute()
    )
    return result.get("values", [])


def get_all_data(spreadsheet_id: str) -> list[list[str]]:
    """Return the full sheet as a 2-D list (including header row)."""
    return _read_all(_get_service(), spreadsheet_id)


def get_totals(spreadsheet_id: str, members: list[str]) -> dict:
    """
    Return {member: total_float, ..., 'overall': float}
    Parses cells like '140+64+34'.
    """
    data = _read_all(_get_service(), spreadsheet_id)
    if not data:
        return {m: 0.0 for m in members} | {"overall": 0.0}

    headers = data[0]
    totals = {m: 0.0 for m in members}

    for row in data[1:]:
        for member in members:
            if member not in headers:
                continue
            cidx = headers.index(member)
            if cidx < len(row) and row[cidx]:
                for part in row[cidx].split("+"):
                    try:
                        totals[member] += float(part.strip())
                    except ValueError:
                        pass

    totals["overall"] = sum(totals[m] for m in members)
    return totals


def get_monthly_totals(spreadsheet_id: str, members: list[str], year: int, month: int) -> dict:
    """Return {member: total} for a specific year-month."""
    data = _read_all(_get_service(), spreadsheet_id)
    if not data:
        return {m: 0.0 for m in members}

    headers = data[0]
    prefix = f"{year:04d}-{month:02d}"
    totals = {m: 0.0 for m in members}

    for row in data[1:]:
        if not row or not row[0].startswith(prefix):
            continue
        for member in members:
            if member not in headers:
                continue
            cidx = headers.index(member)
            if cidx < len(row) and row[cidx]:
                for part in row[cidx].split("+"):
                    try:
                        totals[member] += float(part.strip())
                    except ValueError:
                        pass

    return totals


def get_recent_transactions(spreadsheet_id: str, members: list[str], n: int = 5) -> list[dict]:
    """
    Return the last *n* individual expense entries across all members,
    newest first. Each entry: {date, member, amount}.
    
    FIXED: Now properly tracks transaction creation order (not just date)
    """
    data = _read_all(_get_service(), spreadsheet_id)
    if len(data) < 2:
        return []

    headers = data[0]
    entries = []

    # Go through all rows and all members to collect transactions
    for row_idx, row in enumerate(data[1:], start=1):
        if not row or not row[0]:
            continue
        
        date = row[0]
        
        for member in members:
            if member not in headers:
                continue
            
            cidx = headers.index(member)
            if cidx >= len(row) or not row[cidx]:
                continue
            
            cell = row[cidx].strip()
            parts = cell.split("+")
            
            for part_idx, part in enumerate(parts):
                try:
                    amt = float(part.strip())
                    # Create unique ID for sorting: date + row position + part position
                    entries.append({
                        "date": date,
                        "member": member,
                        "amount": amt,
                        "row_idx": row_idx,
                        "part_idx": part_idx
                    })
                except ValueError:
                    pass

    # Sort by: date (descending), then row position (descending), then part position (descending)
    entries.sort(key=lambda x: (x["date"], x["row_idx"], x["part_idx"]), reverse=True)
    
    # Remove sorting keys before returning
    return [{"date": e["date"], "member": e["member"], "amount": e["amount"]} for e in entries[:n]]


def get_today_transactions(spreadsheet_id: str, members: list[str], today_str: str = None, n: int = 10) -> list[dict]:
    """
    Get transactions for today's date only, up to n entries.
    today_str format: 'YYYY-MM-DD'. If None, uses current date.
    """
    from datetime import date as date_class
    
    if today_str is None:
        today_str = date_class.today().isoformat()
    
    data = _read_all(_get_service(), spreadsheet_id)
    if len(data) < 2:
        return []

    headers = data[0]
    entries = []

    # Go through all rows and all members to collect transactions for today only
    for row_idx, row in enumerate(data[1:], start=1):
        if not row or not row[0]:
            continue
        
        date = row[0]
        
        # Only include transactions from today
        if date != today_str:
            continue
        
        for member in members:
            if member not in headers:
                continue
            
            cidx = headers.index(member)
            if cidx >= len(row) or not row[cidx]:
                continue
            
            cell = row[cidx].strip()
            parts = cell.split("+")
            
            for part_idx, part in enumerate(parts):
                try:
                    amt = float(part.strip())
                    entries.append({
                        "date": date,
                        "member": member,
                        "amount": amt,
                        "row_idx": row_idx,
                        "part_idx": part_idx
                    })
                except ValueError:
                    pass

    # Sort by: row position (descending), then part position (descending)
    entries.sort(key=lambda x: (x["row_idx"], x["part_idx"]), reverse=True)
    
    # Remove sorting keys before returning
    return [{"date": e["date"], "member": e["member"], "amount": e["amount"]} for e in entries[:n]]


def get_monthly_summary(spreadsheet_id: str, members: list[str], year: int, month: int) -> dict:
    """
    Get monthly summary: who spent what and settlement info.
    Returns: {member_totals, settlement, month_name, year}
    """
    monthly_totals = get_monthly_totals(spreadsheet_id, members, year, month)
    
    from datetime import datetime
    month_name = datetime(year, month, 1).strftime("%B")
    
    # Calculate settlement for this month
    from utils import calculations as calc
    settlement = calc.settlement(monthly_totals, members)
    
    return {
        "totals": monthly_totals,
        "settlement": settlement,
        "month": month_name,
        "year": year,
        "members": members
    }


def archive_month_to_sheet2(spreadsheet_id: str, members: list[str], year: int, month: int) -> None:
    """
    Archive monthly summary to Sheet2 (Monthly Archive).
    Creates Sheet2 if it doesn't exist.
    
    Sheet2 Format:
    Month | Year | Member1 | Member2 | ... | Settlement Info
    """
    service = _get_service()
    monthly_data = get_monthly_summary(spreadsheet_id, members, year, month)
    
    try:
        # Get or create Sheet2
        sheet_meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheet_ids = {sheet["properties"]["title"]: sheet["properties"]["sheetId"] 
                     for sheet in sheet_meta.get("sheets", [])}
        
        # Create Sheet2 if it doesn't exist
        if "Monthly Archive" not in sheet_ids:
            sheet_id = max([s["properties"]["sheetId"] for s in sheet_meta["sheets"]]) + 1
            requests = [{
                "addSheet": {
                    "properties": {
                        "sheetId": sheet_id,
                        "title": "Monthly Archive",
                        "gridProperties": {"rowCount": 1000, "columnCount": 26}
                    }
                }
            }]
            service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": requests}
            ).execute()
        
        # Read existing archive data
        archive_result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range="Monthly Archive!A:Z"
        ).execute()
        archive_data = archive_result.get("values", [])
        
        # Create header if empty
        if not archive_data:
            archive_data = [["Month", "Year"] + members + ["Settlement Info"]]
        
        # Prepare month data row
        month_row = [
            monthly_data["month"],
            str(monthly_data["year"])
        ]
        
        # Add member totals
        for member in members:
            month_row.append(monthly_data["totals"].get(member, 0))
        
        # Add settlement info as JSON string
        settlement_text = "; ".join([
            f"{s['payer']} pays {s['receiver']} ₹{s['amount']}"
            for s in monthly_data["settlement"]
        ]) if monthly_data["settlement"] else "All square"
        month_row.append(settlement_text)
        
        # Append to archive
        archive_data.append(month_row)
        
        # Write back
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range="Monthly Archive!A1",
            valueInputOption="RAW",
            body={"values": archive_data}
        ).execute()
    except Exception as e:
        print(f"Error archiving to Sheet2: {e}")


def get_all_monthly_summaries(spreadsheet_id: str, members: list[str], limit: int = 12) -> list[dict]:
    """
    Extract all monthly summaries from Sheet1 data.
    Returns the most recent `limit` months from Sheet1 (not Sheet2 archive).
    Most recent first.
    """
    data = _read_all(_get_service(), spreadsheet_id)
    if len(data) < 2:
        return []
    
    headers = data[0]
    months_data = {}  # Key: (year, month), Value: month_info
    
    # Process all rows
    for row in data[1:]:
        if not row or not row[0]:
            continue
        
        try:
            row_date = datetime.strptime(row[0], "%Y-%m-%d").date()
            year = row_date.year
            month = row_date.month
            month_name = row_date.strftime("%B")
            key = (year, month)
            
            # Initialize if not seen before
            if key not in months_data:
                months_data[key] = {
                    "month": month_name,
                    "month_num": month,  # Store numeric month for sorting
                    "year": year,
                    "totals": {m: 0.0 for m in members},
                    "settlement": []
                }
            
            # Add this row's data to the month
            for member in members:
                if member not in headers:
                    continue
                
                cidx = headers.index(member)
                if cidx >= len(row) or not row[cidx]:
                    continue
                
                cell = row[cidx].strip()
                parts = cell.split("+")
                
                for part in parts:
                    try:
                        amt = float(part.strip())
                        months_data[key]["totals"][member] += amt
                    except ValueError:
                        pass
        except (ValueError, IndexError):
            continue
    
    # Convert to list and sort
    result = []
    for key, month_info in months_data.items():
        # Calculate settlement for this month
        member_totals = month_info["totals"]
        balances = {m: 0 for m in members}
        avg = sum(member_totals.values()) / len(members) if members else 0
        for member, total in member_totals.items():
            balances[member] = total - avg
        
        # Calculate who pays whom
        settlement = []
        sorted_members = sorted(members, key=lambda m: balances[m])
        
        for i, payer in enumerate(sorted_members):
            payer_balance = balances[payer]
            if payer_balance >= -0.01:
                continue
            
            for j, receiver in enumerate(sorted_members):
                if j <= i:
                    continue
                
                receiver_balance = balances[receiver]
                if receiver_balance <= 0.01:
                    continue
                
                amount = min(-payer_balance, receiver_balance)
                if amount > 0.01:
                    settlement.append({
                        "payer": payer,
                        "receiver": receiver,
                        "amount": round(amount, 2)
                    })
                    balances[payer] += amount
                    balances[receiver] -= amount
        
        month_info["settlement"] = settlement
        month_info["overall"] = sum(member_totals.values())
        month_info["total_expense"] = sum(member_totals.values())
        result.append(month_info)
    
    # Sort by year and month (newest first) - use numeric month for correct sorting
    result.sort(key=lambda x: (x["year"], x["month_num"]), reverse=True)
    
    return result[:limit]


def get_archived_months(spreadsheet_id: str, members: list[str], limit: int = 12) -> list[dict]:
    """
    Read all archived months from Sheet2 (Monthly Archive).
    Returns list of {month, year, totals, settlement} dictionaries.
    Most recent first.
    """
    service = _get_service()
    
    try:
        archive_result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range="Monthly Archive!A:Z"
        ).execute()
        archive_data = archive_result.get("values", [])
        
        if len(archive_data) < 2:  # No header or data
            return []
        
        # Parse archive data
        headers = archive_data[0]
        archived_months = []
        
        for row in archive_data[1:]:
            if not row or len(row) < 2:
                continue
            
            try:
                month_name = row[0]
                year = int(row[1])
                
                # Extract member totals
                member_totals = {}
                for idx, member in enumerate(members):
                    col_idx = idx + 2  # Skip Month and Year columns
                    if col_idx < len(row):
                        try:
                            member_totals[member] = float(row[col_idx])
                        except (ValueError, IndexError):
                            member_totals[member] = 0.0
                
                # Extract settlement info
                settlement_text = row[-1] if len(row) > len(members) + 2 else "All square"
                
                archived_months.append({
                    "month": month_name,
                    "year": year,
                    "totals": member_totals,
                    "settlement": settlement_text,
                    "overall": sum(member_totals.values())
                })
            except (ValueError, IndexError):
                continue
        
        # Sort by year and month (newest first)
        month_order = {"January": 1, "February": 2, "March": 3, "April": 4,
                      "May": 5, "June": 6, "July": 7, "August": 8,
                      "September": 9, "October": 10, "November": 11, "December": 12}
        
        archived_months.sort(
            key=lambda x: (x["year"], month_order.get(x["month"], 0)),
            reverse=True
        )
        
        return archived_months[:limit]
    except Exception as e:
        print(f"Error reading archived months: {e}")
        return []


def export_to_csv(spreadsheet_id: str) -> str:
    """Return sheet data as CSV string."""
    data = _read_all(_get_service(), spreadsheet_id)
    lines = [",".join(row) for row in data]
    return "\n".join(lines)


def get_month_transactions(spreadsheet_id: str, members: list[str], year: int, month: int) -> dict:
    """
    Get detailed transactions for a specific month.
    Returns: {
        "month": "May",
        "year": 2026,
        "members": ["Aman", "Rahul", ...],
        "transactions": [
            {"date": "2026-05-15", "member": "Aman", "amount": 500},
            ...
        ],
        "member_totals": {"Aman": 1500, "Rahul": 2000},
        "settlement": [...],
        "overall": 5000
    }
    """
    data = _read_all(_get_service(), spreadsheet_id)
    if not data:
        return {
            "month": datetime(year, month, 1).strftime("%B"),
            "year": year,
            "members": members,
            "transactions": [],
            "member_totals": {m: 0 for m in members},
            "settlement": [],
            "overall": 0
        }
    
    headers = data[0]
    transactions = []
    member_totals = {m: 0 for m in members}
    
    # Collect all transactions for this month
    for row_idx, row in enumerate(data[1:], start=1):
        if not row or not row[0]:
            continue
        
        try:
            row_date = datetime.strptime(row[0], "%Y-%m-%d").date()
        except (ValueError, IndexError):
            continue
        
        # Check if this row is in the target month
        if row_date.month != month or row_date.year != year:
            continue
        
        # Extract transactions for each member
        for member in members:
            if member not in headers:
                continue
            
            cidx = headers.index(member)
            if cidx >= len(row) or not row[cidx]:
                continue
            
            cell = row[cidx].strip()
            parts = cell.split("+")
            
            for part in parts:
                try:
                    amt = float(part.strip())
                    transactions.append({
                        "date": row[0],
                        "member": member,
                        "amount": amt
                    })
                    member_totals[member] += amt
                except ValueError:
                    pass
    
    # Sort by date descending
    transactions.sort(key=lambda x: x["date"], reverse=True)
    
    # Calculate settlement for this month
    settlement = []
    
    # Sort members by balance
    balances = {m: 0 for m in members}
    for member, total in member_totals.items():
        avg = sum(member_totals.values()) / len(members)
        balances[member] = total - avg
    
    # Calculate who pays whom
    sorted_members = sorted(members, key=lambda m: balances[m])
    
    for i, payer in enumerate(sorted_members):
        payer_balance = balances[payer]
        if payer_balance >= -0.01:  # They don't owe anything
            continue
        
        for j, receiver in enumerate(sorted_members):
            if j <= i:
                continue
            
            receiver_balance = balances[receiver]
            if receiver_balance <= 0.01:  # They don't have anything to receive
                continue
            
            amount = min(-payer_balance, receiver_balance)
            if amount > 0.01:
                settlement.append({
                    "payer": payer,
                    "receiver": receiver,
                    "amount": round(amount, 2)
                })
                balances[payer] += amount
                balances[receiver] -= amount
    
    overall = sum(member_totals.values())
    month_name = datetime(year, month, 1).strftime("%B")
    
    return {
        "month": month_name,
        "year": year,
        "members": members,
        "transactions": transactions,
        "member_totals": member_totals,
        "settlement": settlement,
        "overall": overall
    }
