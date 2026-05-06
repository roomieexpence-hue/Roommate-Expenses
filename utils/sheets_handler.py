"""
sheets_handler.py
-----------------
All Google Sheets read/write logic lives here.

Sheet layout expected:
  Row 1  : Headers  → Date | Member1 | Member2 | ...
  Row 2+ : Data     → 2024-06-01 | 140+64 | 300 | ...
"""

import os
import json
import base64
from datetime import datetime, timezone, timedelta

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from . import calculations as calc

# IST timezone (UTC+5:30)
IST = timezone(timedelta(hours=5, minutes=30))

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Palette for member column headers (one per member, cycles if > 7)
HEADER_COLORS = [
    {"red": 0.27, "green": 0.51, "blue": 0.71},  # steel blue
    {"red": 0.18, "green": 0.63, "blue": 0.46},  # emerald
    {"red": 0.83, "green": 0.33, "blue": 0.33},  # coral
    {"red": 0.60, "green": 0.40, "blue": 0.80},  # violet
    {"red": 0.95, "green": 0.62, "blue": 0.07},  # amber
    {"red": 0.20, "green": 0.63, "blue": 0.79},  # cyan
    {"red": 0.84, "green": 0.44, "blue": 0.24},  # burnt orange
]


def _get_service():
    """Build and return a Sheets API service object.
    
    Supports two modes:
    1. Local: credentials.json file (GOOGLE_CREDENTIALS_FILE env var)
    2. Vercel: GOOGLE_CREDENTIALS_B64 env var (base64 encoded JSON)
    """
    # Check if we're on Vercel (detectable by presence of VERCEL env var)
    is_vercel = os.getenv("VERCEL") == "1"
    
    # Try to load from environment variable first (Vercel production)
    creds_b64 = os.getenv("GOOGLE_CREDENTIALS_B64")
    if creds_b64:
        try:
            creds_json_str = base64.b64decode(creds_b64).decode("utf-8")
            creds_dict = json.loads(creds_json_str)
            creds = service_account.Credentials.from_service_account_info(
                creds_dict, scopes=SCOPES
            )
            return build("sheets", "v4", credentials=creds)
        except Exception as e:
            raise Exception(f"Failed to load credentials from GOOGLE_CREDENTIALS_B64: {e}")
    
    # If we're on Vercel and don't have the env var, fail immediately
    if is_vercel:
        raise Exception(
            "🚨 VERCEL ERROR: GOOGLE_CREDENTIALS_B64 environment variable is NOT SET!\n"
            "Follow these steps:\n"
            "1. Go to Vercel Dashboard → Settings → Environment Variables\n"
            "2. Add GOOGLE_CREDENTIALS_B64 with the base64 encoded credentials\n"
            "3. Redeploy the project\n"
            "See VERCEL_SETUP.md for detailed instructions."
        )
    
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

def _format_amount_with_time(amount: float) -> str:
    """
    Format amount with current time in IST (Indian Standard Time).
    Format: amount(HH:MM:SS)
    Example: 123(14:30:45)
    """
    now = datetime.now(IST)
    time_str = now.strftime("%H:%M:%S")
    amount_str = str(int(amount)) if amount == int(amount) else str(amount)
    return f"{amount_str}({time_str})"


def _parse_amount_with_time(cell_value: str) -> tuple[float, str]:
    """
    Parse amount(HH:MM:SS) format.
    Returns: (amount_float, time_string)
    Example: "123(14:30:45)" → (123.0, "14:30:45")
    Falls back to just amount if no time format found.
    """
    cell_value = str(cell_value).strip()
    
    # Try to parse new format: amount(HH:MM:SS)
    if "(" in cell_value and ")" in cell_value:
        try:
            amount_part, time_part = cell_value.split("(", 1)
            time_str = time_part.rstrip(")")
            amount = float(amount_part.strip())
            return amount, time_str
        except (ValueError, IndexError):
            # If parsing fails, try to get just the amount
            try:
                return float(cell_value), ""
            except ValueError:
                return 0.0, ""
    else:
        # Old format (just amount)
        try:
            return float(cell_value), ""
        except ValueError:
            return 0.0, ""


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
    • If the date row exists, append amount with '+' to same row
    • If not, create a new row for that date
    • Stores in format: amount(HH:MM:SS) e.g., 123(14:30:45)
    • Keeps sheet sorted by DATE (chronological order)
    """
    service = _get_service()
    
    # IMPORTANT: Sync members first to ensure all columns exist
    sync_sheet_members(spreadsheet_id, members)
    
    all_data = _read_all(service, spreadsheet_id)
    headers = all_data[0] if all_data else ["Date"] + members
    col_idx = headers.index(member_name)

    # Find existing row for this date
    row_idx = None
    for i, row in enumerate(all_data[1:], start=1):
        if row and row[0] == date_str:
            row_idx = i
            break

    amount_str = _format_amount_with_time(amount)

    if row_idx is not None:
        # Append to existing row for this date
        row = all_data[row_idx]
        while len(row) <= col_idx:
            row.append("")
        existing = row[col_idx].strip()
        row[col_idx] = f"{existing}+{amount_str}" if existing else amount_str
        all_data[row_idx] = row
    else:
        # Create new row for this date
        new_row = [""] * len(headers)
        new_row[0] = date_str
        new_row[col_idx] = amount_str
        all_data.append(new_row)
        # IMPORTANT: Sort by date so chronological order is maintained
        data_rows = sorted(all_data[1:], key=lambda r: r[0] if r else "")
        all_data = [all_data[0]] + data_rows

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
        
        # Find the row for this date
        for row in all_data[1:]:
            if row and len(row) > 0 and row[0] == date_str:
                if len(row) > col_idx:
                    cell_content = row[col_idx].strip()
                    if not cell_content:
                        break
                    
                    # Cell might contain "100" or "100(16:45:30)" or "100(16:45:30)+50(17:20:15)"
                    # Split by '+' to get individual transaction entries
                    entries = cell_content.split('+')
                    for entry in entries:
                        parsed_amount, _ = _parse_amount_with_time(entry.strip())
                        # Check if this amount matches (within floating point tolerance)
                        if abs(parsed_amount - amount) < 0.01:
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
    Parses cells like '140+64+34' or '140(14:30:45)+64(15:45:20)+34(16:20:10)'.
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
                        amount, _ = _parse_amount_with_time(part)
                        totals[member] += amount
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
        if not row or not row[0] or not row[0].startswith(prefix):
            continue
        for member in members:
            if member not in headers:
                continue
            cidx = headers.index(member)
            if cidx < len(row) and row[cidx]:
                for part in row[cidx].split("+"):
                    try:
                        amount, _ = _parse_amount_with_time(part)
                        totals[member] += amount
                    except ValueError:
                        pass

    return totals


def get_recent_transactions(spreadsheet_id: str, members: list[str], n: int = 5) -> list[dict]:
    """
    Return the last *n* individual expense entries, prioritizing TODAY's transactions.
    
    Logic:
    1. Collect all transactions from TODAY first
    2. If less than n transactions today, fill remaining from previous dates (newest dates first)
    3. Each entry: {date, member, amount, time}
    4. Within same date, sort by time (newest first)
    """
    from datetime import date as date_class
    
    data = _read_all(_get_service(), spreadsheet_id)
    if len(data) < 2:
        return []

    today_str = date_class.today().isoformat()
    headers = data[0]
    
    # Organize transactions by date
    transactions_by_date = {}  # {date_str: [transaction list]}
    
    for row in data[1:]:
        if not row or not row[0]:
            continue
        
        date_str = row[0]
        if date_str not in transactions_by_date:
            transactions_by_date[date_str] = []
        
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
                    amount, time_str = _parse_amount_with_time(part)
                    
                    # Parse time to seconds for sorting within same date
                    time_seconds = 0
                    if time_str:
                        try:
                            h, m, s = map(int, time_str.split(':'))
                            time_seconds = h * 3600 + m * 60 + s
                        except (ValueError, AttributeError):
                            time_seconds = 0
                    
                    transactions_by_date[date_str].append({
                        "date": date_str,
                        "member": member,
                        "amount": amount,
                        "time": time_str,
                        "time_seconds": time_seconds
                    })
                except ValueError:
                    pass
    
    # Sort transactions within each date by time (newest first)
    for date_str in transactions_by_date:
        transactions_by_date[date_str].sort(
            key=lambda x: x["time_seconds"], 
            reverse=True
        )
    
    # Collect result: today first, then previous dates in reverse chronological order
    result = []
    dates_sorted = sorted(transactions_by_date.keys(), reverse=True)  # Newest dates first
    
    # Prioritize today's date - move it to front if it exists
    if today_str in dates_sorted:
        dates_sorted.remove(today_str)
        dates_sorted.insert(0, today_str)
    
    # Collect up to n transactions
    for date_str in dates_sorted:
        for transaction in transactions_by_date[date_str]:
            if len(result) >= n:
                break
            
            item = {
                "date": transaction["date"],
                "member": transaction["member"],
                "amount": transaction["amount"]
            }
            if transaction["time"]:
                item["time"] = transaction["time"]
            result.append(item)
        
        if len(result) >= n:
            break
    
    return result


def get_today_transactions(spreadsheet_id: str, members: list[str], today_str: str = None, n: int = 10) -> list[dict]:
    """
    Get transactions for today's date only, up to n entries.
    today_str format: 'YYYY-MM-DD'. If None, uses current date.
    Returns list of dicts with: date, member, amount, time
    Sorted by time (newest first).
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
                    amount, time_str = _parse_amount_with_time(part)
                    if amount > 0:
                        entries.append({
                            "date": date,
                            "member": member,
                            "amount": amount,
                            "time": time_str,
                            "row_idx": row_idx,
                            "part_idx": part_idx
                        })
                except ValueError:
                    pass

    # Sort by: time (descending, newest first), then row position (descending)
    entries.sort(key=lambda x: (x.get("time", "") or "00:00:00"), reverse=True)
    
    # Remove sorting keys before returning
    return [{"date": e["date"], "member": e["member"], "amount": e["amount"], "time": e["time"]} for e in entries[:n]]


def get_monthly_summary(spreadsheet_id: str, members: list[str], year: int, month: int) -> dict:
    """
    Get monthly summary: who spent what and settlement info.
    Returns: {member_totals, settlement, month_name, year}
    """
    monthly_totals = get_monthly_totals(spreadsheet_id, members, year, month)
    
    month_name = datetime(year, month, 1).strftime("%B")
    
    # Calculate settlement for this month
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
                        amount, _ = _parse_amount_with_time(part)
                        months_data[key]["totals"][member] += amount
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
        if row_date.year != year or row_date.month != month:
            continue
        
        # Process each member's transaction for this row
        for member_idx, member in enumerate(members):
            col_idx = member_idx + 1
            if col_idx < len(row) and row[col_idx]:
                try:
                    # Parse amount (can have multiple parts like "100(14:35:54)+50(15:20:10)")
                    parts = row[col_idx].split('+')
                    for part in parts:
                        # Extract just the number part
                        amount_match = part.split('(')[0]
                        if amount_match:
                            amount = float(amount_match)
                            transactions.append({
                                "date": row_date.strftime("%Y-%m-%d"),
                                "member": member,
                                "amount": amount
                            })
                            member_totals[member] += amount
                except (ValueError, IndexError):
                    continue
    
    # Calculate settlement
    settlement = calc.settlement(member_totals, members)
    
    return {
        "month": datetime(year, month, 1).strftime("%B"),
        "year": year,
        "members": members,
        "transactions": transactions,
        "member_totals": member_totals,
        "settlement": settlement,
        "overall": sum(member_totals.values())
    }
