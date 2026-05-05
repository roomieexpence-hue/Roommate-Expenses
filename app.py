"""
app.py
------
Main Flask application entry-point.

Routes
  GET  /            → login page (if not authenticated)
  POST /login       → authenticate
  GET  /logout      → clear session
  GET  /dashboard   → main dashboard
  POST /add         → add expense
  GET  /api/totals  → JSON totals (all-time)
  GET  /api/monthly → JSON monthly totals
  GET  /api/table   → JSON full sheet data
  GET  /export/csv  → download CSV
  GET  /export/excel→ download Excel
"""

import os
import io
from datetime import datetime, date
from functools import wraps

import pandas as pd
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, jsonify, send_file, flash
)
from dotenv import load_dotenv

from utils import sheets_handler as sh
from utils import calculations as calc
from utils import email_service as mail

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-change-me")

# ── Config helpers ────────────────────────────────────────────────────────────

def get_members() -> list[str]:
    raw = os.getenv("ROOMMATES", "Aman,Rahul,Shubham")
    return [m.strip() for m in raw.split(",") if m.strip()]

def get_sheet_id() -> str:
    return os.getenv("GOOGLE_SHEET_ID", "")

def update_roommates_env(new_members: list[str]) -> None:
    """Update .env file with new roommates list."""
    env_path = ".env"
    content = ""
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            content = f.read()
    
    # Update or add ROOMMATES line
    import re
    pattern = r"ROOMMATES=.*"
    new_line = f"ROOMMATES={','.join(new_members)}"
    if re.search(pattern, content):
        content = re.sub(pattern, new_line, content)
    else:
        content += f"\n{new_line}"
    
    with open(env_path, "w") as f:
        f.write(content)

CATEGORIES = ["Food", "Rent", "Utilities", "Travel", "Groceries", "Entertainment", "General"]

# ── Auth decorator ────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


# ── Auth routes ───────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def index():
    if session.get("logged_in"):
        return redirect(url_for("dashboard"))
    return render_template("login.html")


@app.route("/login", methods=["POST"])
def login():
    password = request.form.get("password", "")
    app_pw   = os.getenv("APP_PASSWORD", "roomie2024")
    if password == app_pw:
        session["logged_in"] = True
        # Initialise sheet on first login
        try:
            sh.initialise_sheet(get_sheet_id(), get_members())
        except Exception as e:
            app.logger.warning(f"Sheet init failed: {e}")
        return redirect(url_for("dashboard"))
    flash("Wrong password. Try again.")
    return redirect(url_for("index"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# ── Add member ────────────────────────────────────────────────────────────────

@app.route("/add-member", methods=["POST"])
@login_required
def add_member():
    members   = get_members()
    sheet_id  = get_sheet_id()
    new_name  = request.form.get("name", "").strip()

    # Validate
    if not new_name:
        flash("Member name cannot be empty.")
        return redirect(url_for("dashboard"))
    
    if new_name in members:
        flash(f"❌ '{new_name}' already exists. Use a different name.")
        return redirect(url_for("dashboard"))
    
    if len(new_name) > 30:
        flash("Member name is too long (max 30 characters).")
        return redirect(url_for("dashboard"))

    # Add to .env and Google Sheet
    try:
        new_members = members + [new_name]
        sh.add_member_column(sheet_id, new_name, len(new_members) - 1)
        update_roommates_env(new_members)
        os.environ["ROOMMATES"] = ",".join(new_members)
    except Exception as e:
        app.logger.error(f"Add member error: {e}")
        flash(f"Could not add member: {e}")
        return redirect(url_for("dashboard"))

    flash(f"✅ '{new_name}' added successfully!")
    return redirect(url_for("dashboard"))


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.route("/dashboard")
@login_required
def dashboard():
    members    = get_members()
    sheet_id   = get_sheet_id()
    today      = date.today().isoformat()
    now        = datetime.now()

    # Initialize defaults
    totals    = {m: 0 for m in members} | {"overall": 0}
    recent    = []
    anomalies = []
    all_monthly_summaries = []
    
    # Try to fetch each data section independently so partial failures don't break everything
    try:
        app.logger.info(f"Fetching monthly totals for {now.year}-{now.month:02d}")
        totals   = sh.get_monthly_totals(sheet_id, members, now.year, now.month)
        totals["overall"] = sum(totals[m] for m in members if m != "overall")
        app.logger.info(f"✓ Monthly totals loaded: {totals}")
    except Exception as e:
        app.logger.error(f"⚠ Monthly totals error: {e}")
        totals = {m: 0 for m in members} | {"overall": 0}
    
    try:
        app.logger.info("Fetching recent transactions (all dates)")
        recent   = sh.get_recent_transactions(sheet_id, members, n=5)
        app.logger.info(f"✓ Recent transactions loaded: {len(recent)} entries")
    except Exception as e:
        app.logger.error(f"⚠ Recent transactions error: {e}")
        recent = []
    
    try:
        anomalies = calc.detect_anomaly(totals, members)
        app.logger.info(f"✓ Anomalies detected: {len(anomalies)}")
    except Exception as e:
        app.logger.error(f"⚠ Anomaly detection error: {e}")
        anomalies = []
    
    try:
        app.logger.info("Fetching monthly summaries")
        all_monthly_summaries = sh.get_all_monthly_summaries(sheet_id, members, limit=6)
        app.logger.info(f"✓ Monthly summaries loaded: {len(all_monthly_summaries)} months")
    except Exception as e:
        app.logger.error(f"⚠ Monthly summaries error: {e}")
        all_monthly_summaries = []

    settle = calc.settlement(totals, members)

    month_start = date(now.year, now.month, 1).isoformat()
    month_end = date.today().isoformat()
    
    return render_template(
        "dashboard.html",
        members=members,
        totals=totals,
        recent=recent,
        settlement=settle,
        archived_months=all_monthly_summaries,
        anomalies=anomalies,
        categories=CATEGORIES,
        today=month_end,
        month_start=month_start,
        current_month=now.strftime("%B %Y"),
        current_year=now.year,
        current_month_num=now.month,
    )


# ── Add expense ───────────────────────────────────────────────────────────────

@app.route("/add", methods=["POST"])
@login_required
def add_expense():
    members   = get_members()
    sheet_id  = get_sheet_id()

    member    = request.form.get("member")
    amount_raw  = request.form.get("amount", "0")
    date_str    = request.form.get("date", date.today().isoformat())

    # Validate member
    if member not in members:
        flash(f"Unknown member: {member}")
        return redirect(url_for("dashboard"))
    
    # Validate amount
    try:
        amount = float(amount_raw)
        assert amount > 0
    except (ValueError, AssertionError):
        flash("Amount must be a positive number.")
        return redirect(url_for("dashboard"))
    
    # Validate date - no future dates
    try:
        exp_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        today = date.today()
        
        if exp_date > today:
            flash("❌ Cannot add expenses for future dates. Please select today or an earlier date.")
            return redirect(url_for("dashboard"))
    except ValueError:
        flash("Invalid date format.")
        return redirect(url_for("dashboard"))
    
    # Check for duplicate expense
    try:
        if sh.expense_exists(sheet_id, members, member, amount, date_str):
            flash(f"❌ You have already added this amount (₹{amount:,.0f}) for {member} on {date_str}.")
            return redirect(url_for("dashboard"))
    except Exception as e:
        app.logger.warning(f"Duplicate check error: {e}")

    # Write to sheet
    try:
        sh.add_expense(sheet_id, members, member, amount, date_str)
    except Exception as e:
        app.logger.error(f"Sheet write error: {e}")
        flash(f"Could not update Google Sheet: {e}")
        return redirect(url_for("dashboard"))

    # Recalculate totals
    try:
        totals = sh.get_totals(sheet_id, members)
    except Exception:
        totals = {m: 0 for m in members} | {"overall": 0}

    settle = calc.settlement(totals, members)
    summary = calc.build_summary_text(totals, members, member, amount)
    app.logger.info(summary)

    # Get month/year from expense date
    exp_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    
    # Email notification with month/year (non-blocking failure)
    try:
        mail.send_expense_notification(
            member, amount, "", "", date_str,
            totals, members, settle,
            year=exp_date.year,
            month=exp_date.month
        )
    except Exception as e:
        app.logger.warning(f"Email failed: {e}")

    # Auto-archive the month if it's an older date
    try:
        if exp_date < today:
            # This is a past expense, check if we should archive that month
            sh.archive_month_to_sheet2(sheet_id, members, exp_date.year, exp_date.month)
            app.logger.info(f"Auto-archived {exp_date.strftime('%B %Y')}")
    except Exception as e:
        app.logger.warning(f"Auto-archive failed: {e}")
    
    flash(f"✅ ₹{amount:,.0f} added for {member} on {date_str}.")
    return redirect(url_for("dashboard"))


# ── JSON APIs ─────────────────────────────────────────────────────────────────

@app.route("/api/totals")
@login_required
def api_totals():
    members  = get_members()
    sheet_id = get_sheet_id()
    try:
        totals = sh.get_totals(sheet_id, members)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"totals": totals, "members": members})


@app.route("/api/monthly")
@login_required
def api_monthly():
    members  = get_members()
    sheet_id = get_sheet_id()
    year  = int(request.args.get("year",  datetime.now().year))
    month = int(request.args.get("month", datetime.now().month))
    try:
        monthly = sh.get_monthly_totals(sheet_id, members, year, month)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"monthly": monthly, "members": members, "year": year, "month": month})


@app.route("/api/table")
@login_required
def api_table():
    sheet_id = get_sheet_id()
    try:
        data = sh.get_all_data(sheet_id)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"data": data})


@app.route("/api/settlement")
@login_required
def api_settlement():
    members  = get_members()
    sheet_id = get_sheet_id()
    try:
        totals = sh.get_totals(sheet_id, members)
        settle = calc.settlement(totals, members)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"settlement": settle})


@app.route("/api/monthly-summary")
@login_required
def api_monthly_summary():
    """Get monthly summary with settlement info."""
    members  = get_members()
    sheet_id = get_sheet_id()
    year  = int(request.args.get("year",  datetime.now().year))
    month = int(request.args.get("month", datetime.now().month))
    
    try:
        summary = sh.get_monthly_summary(sheet_id, members, year, month)
        return jsonify(summary)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/previous-month")
@login_required
def api_previous_month():
    """Get previous month's totals and settlement."""
    members  = get_members()
    sheet_id = get_sheet_id()
    now = datetime.now()
    
    # Calculate previous month
    prev_month = now.month - 1
    prev_year = now.year
    if prev_month < 1:
        prev_month = 12
        prev_year -= 1
    
    try:
        summary = sh.get_monthly_summary(sheet_id, members, prev_year, prev_month)
        return jsonify(summary)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/archived-months")
@login_required
def api_archived_months():
    """Get all archived months from Sheet2."""
    members  = get_members()
    sheet_id = get_sheet_id()
    limit    = int(request.args.get("limit", 12))
    
    try:
        archived = sh.get_archived_months(sheet_id, members, limit)
        return jsonify({"archived_months": archived, "members": members})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/archive-month", methods=["POST"])
@login_required
def api_archive_month():
    """Archive current month to Sheet2."""
    members  = get_members()
    sheet_id = get_sheet_id()
    now = datetime.now()
    
    try:
        # Archive current month to Sheet2
        sh.archive_month_to_sheet2(sheet_id, members, now.year, now.month)
        
        # Get the archived data
        archived = sh.get_archived_months(sheet_id, members, limit=1)
        
        return jsonify({
            "success": True,
            "message": f"Month {now.strftime('%B %Y')} archived successfully!",
            "archived": archived[0] if archived else None
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/month-details")
@login_required
def api_month_details():
    """Get detailed transactions for a specific month."""
    members  = get_members()
    sheet_id = get_sheet_id()
    year  = int(request.args.get("year", datetime.now().year))
    month = int(request.args.get("month", datetime.now().month))
    
    try:
        details = sh.get_month_transactions(sheet_id, members, year, month)
        return jsonify(details)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/daily-expenses")
@login_required
def api_daily_expenses():
    """Get daily expense totals by member for all dates (chart will filter to last N days)."""
    members  = get_members()
    sheet_id = get_sheet_id()
    
    try:
        # Get all data from Sheet1
        all_data = sh.get_all_data(sheet_id)
        
        daily_totals = {}
        
        # Parse data (skip header)
        if len(all_data) > 1:
            for row_data in all_data[1:]:
                if not row_data or not row_data[0]:
                    continue
                    
                date_str = row_data[0]
                
                # Parse date
                try:
                    row_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                except:
                    continue
                
                date_key = date_str
                if date_key not in daily_totals:
                    daily_totals[date_key] = {m: 0 for m in members}
                
                # Parse expenses for each member
                for idx, member in enumerate(members):
                    if idx + 1 < len(row_data) and row_data[idx + 1]:
                        cell_val = row_data[idx + 1]
                        # Handle multiple entries in one cell (e.g., "100(14:30:45)+50(15:20:10)+25")
                        parts = str(cell_val).split('+')
                        for part in parts:
                            try:
                                amount, _ = sh._parse_amount_with_time(part)
                                daily_totals[date_key][member] += amount
                            except (ValueError, TypeError):
                                pass
        
        return jsonify({"daily": daily_totals, "members": members})
    except Exception as e:
        app.logger.error(f"Daily expenses error: {e}")
        return jsonify({"daily": {}, "members": members}), 500


@app.route("/api/predict")
@login_required
def api_predict():
    """Return ML-predicted next-month total per member."""
    members  = get_members()
    sheet_id = get_sheet_id()
    now = datetime.now()
    predictions = {}
    try:
        for m in members:
            series = []
            for offset in range(6, 0, -1):   # last 6 months
                mo = now.month - offset
                yr = now.year
                while mo < 1:
                    mo += 12
                    yr -= 1
                mt = sh.get_monthly_totals(sheet_id, members, yr, mo)
                series.append(mt.get(m, 0))
            predictions[m] = calc.predict_next_month(series)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"predictions": predictions})


# ── Exports ───────────────────────────────────────────────────────────────────

@app.route("/export/csv")
@login_required
def export_csv():
    sheet_id = get_sheet_id()
    try:
        csv_str = sh.export_to_csv(sheet_id)
    except Exception as e:
        flash(f"Export failed: {e}")
        return redirect(url_for("dashboard"))
    buf = io.BytesIO(csv_str.encode("utf-8"))
    buf.seek(0)
    return send_file(buf, mimetype="text/csv",
                     as_attachment=True, download_name="roomie_expenses.csv")


@app.route("/export/excel")
@login_required
def export_excel():
    members  = get_members()
    sheet_id = get_sheet_id()
    try:
        data = sh.get_all_data(sheet_id)
        if not data:
            flash("No data to export.")
            return redirect(url_for("dashboard"))
        df = pd.DataFrame(data[1:], columns=data[0])
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Expenses")
        buf.seek(0)
    except Exception as e:
        flash(f"Excel export failed: {e}")
        return redirect(url_for("dashboard"))
    return send_file(buf, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     as_attachment=True, download_name="roomie_expenses.xlsx")


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
