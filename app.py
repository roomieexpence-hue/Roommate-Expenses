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

    try:
        # Sync sheet members with code (recreates any accidentally deleted columns)
        sh.sync_sheet_members(sheet_id, members)
        
        totals   = sh.get_totals(sheet_id, members)
        recent   = sh.get_recent_transactions(sheet_id, members, n=5)
        anomalies = calc.detect_anomaly(totals, members)
    except Exception as e:
        app.logger.error(f"Dashboard data error: {e}")
        totals    = {m: 0 for m in members} | {"overall": 0}
        recent    = []
        anomalies = []

    settle = calc.settlement(totals, members)

    now = datetime.now()
    return render_template(
        "dashboard.html",
        members=members,
        totals=totals,
        recent=recent,
        settlement=settle,
        anomalies=anomalies,
        categories=CATEGORIES,
        today=today,
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

    # Email notification (non-blocking failure)
    try:
        mail.send_expense_notification(
            member, amount, "", "", date_str,
            totals, members, settle
        )
    except Exception as e:
        app.logger.warning(f"Email failed: {e}")

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
