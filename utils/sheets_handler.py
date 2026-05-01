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
from datetime import datetime

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

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
    """Build and return a Sheets API service object."""
    creds_file = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
    creds = service_account.Credentials.from_service_account_file(
        creds_file, scopes=SCOPES
    )
    return build("sheets", "v4", credentials=creds)


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
    newest first.  Each entry: {date, member, amount, raw}.
    """
    data = _read_all(_get_service(), spreadsheet_id)
    if len(data) < 2:
        return []

    headers = data[0]
    entries = []

    for row in data[1:]:
        if not row:
            continue
        date = row[0]
        for member in members:
            if member not in headers:
                continue
            cidx = headers.index(member)
            if cidx < len(row) and row[cidx]:
                cell = row[cidx]
                parts = cell.split("+")
                for part in parts:
                    try:
                        amt = float(part.strip())
                        entries.append({"date": date, "member": member, "amount": amt, "raw": cell})
                    except ValueError:
                        pass

    entries.sort(key=lambda x: x["date"], reverse=True)
    return entries[:n]


def export_to_csv(spreadsheet_id: str) -> str:
    """Return sheet data as CSV string."""
    data = _read_all(_get_service(), spreadsheet_id)
    lines = [",".join(row) for row in data]
    return "\n".join(lines)
