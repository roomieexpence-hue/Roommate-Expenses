# 💸 RoomiePay – Shared Expense Tracker

A full-stack Flask web application for managing shared expenses among roommates with Google Sheets integration, email notifications, and a modern data-driven dashboard.

---

## ✨ Features

| Feature | Details |
|---|---|
| **Expense Tracking** | Add expenses per member, category, date |
| **Google Sheets Sync** | Auto-updates a live spreadsheet after every entry |
| **Email Notifications** | HTML email sent to all roommates after every update |
| **Dashboard** | Stat cards, bar chart, ledger table, recent transactions |
| **Settlement** | Who-owes-whom calculated automatically |
| **Anomaly Detection** | Flags unusually high spenders |
| **ML Prediction** | Predicts next month's expenses via linear regression |
| **Exports** | Download data as CSV or Excel |
| **Auth** | Simple shared group password |
| **Deployment-ready** | Gunicorn + Procfile for Render / Railway |

---

## 📁 Project Structure

```
roommate-expenses/
├── app.py                  # Flask app, routes, auth
├── requirements.txt
├── Procfile                # Deployment (Render/Railway)
├── runtime.txt
├── .env.example            # Copy to .env and fill in
├── credentials.json        # Google service account key (you add this)
├── utils/
│   ├── __init__.py
│   ├── sheets_handler.py   # Google Sheets read/write
│   ├── email_service.py    # SMTP email via Gmail
│   └── calculations.py     # Settlement, anomaly, ML predict
└── templates/
    ├── base.html           # Nav, styles, shared layout
    ├── login.html          # Login page
    └── dashboard.html      # Main dashboard
```

---

## 🚀 Setup Guide

### 1. Clone & Install

```bash
git clone <your-repo-url>
cd roommate-expenses
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Google Sheets API Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or use an existing one)
3. Enable **Google Sheets API**
4. Go to **IAM & Admin → Service Accounts → Create Service Account**
5. Give it a name, click through to **Keys → Add Key → JSON**
6. Download the JSON file and save it as `credentials.json` in the project root
7. Create a new [Google Sheet](https://sheets.google.com)
8. Copy the Sheet ID from the URL:
   `https://docs.google.com/spreadsheets/d/**<SHEET_ID>**/edit`
9. Share the sheet with the service account email (found in `credentials.json` → `client_email`) with **Editor** access

### 3. Gmail App Password Setup

1. Go to your Google Account → Security → 2-Step Verification (enable if not already)
2. Go to **Security → App Passwords**
3. Generate a new app password for "Mail"
4. Copy the 16-character password

### 4. Configure Environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
SECRET_KEY=some-random-string-here
ROOMMATES=Aman,Rahul,Shubham

GOOGLE_SHEET_ID=your_sheet_id_here
GOOGLE_CREDENTIALS_FILE=credentials.json

SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
EMAIL_SENDER=yourname@gmail.com
EMAIL_PASSWORD=your_16_char_app_password
EMAIL_RECIPIENTS=aman@gmail.com,rahul@gmail.com,shubham@gmail.com

APP_PASSWORD=roomie2024
```

### 5. Run Locally

```bash
python app.py
```

Visit `http://localhost:5000` and log in with your `APP_PASSWORD`.

---

## 📊 Google Sheet Format

The app automatically creates and manages this layout:

| Date | Aman | Rahul | Shubham |
|---|---|---|---|
| 2024-06-01 | 140+64 | 300 | |
| 2024-06-02 | | 150 | 200+50 |

- First row = coloured member headers (auto-created)
- Multiple expenses on same day → `140+64+34` format
- New date → new row (sorted chronologically)

---

## 🚀 Deploy to Render

1. Push code to GitHub
2. Go to [render.com](https://render.com) → New Web Service → Connect repo
3. Settings:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app`
4. Add all `.env` variables in **Environment** tab
5. Upload `credentials.json` as a Secret File at `/etc/secrets/credentials.json`
   and set `GOOGLE_CREDENTIALS_FILE=/etc/secrets/credentials.json`

---

## 🚀 Deploy to Railway

```bash
npm install -g @railway/cli
railway login
railway init
railway up
```

Set environment variables in Railway dashboard.

---

## 🔌 API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/api/totals` | GET | All-time totals per member |
| `/api/monthly?year=&month=` | GET | Monthly totals |
| `/api/table` | GET | Full sheet data as JSON |
| `/api/settlement` | GET | Who owes whom |
| `/api/predict` | GET | ML next-month prediction |
| `/export/csv` | GET | Download CSV |
| `/export/excel` | GET | Download Excel |
| `/add` | POST | Add an expense |

---

## 🔐 Security Notes

- Never commit `.env` or `credentials.json` to git
- Add both to `.gitignore`
- Use a strong `SECRET_KEY` in production
- The `APP_PASSWORD` is a shared group password; for production, consider per-user auth

---

## 🐛 Troubleshooting

| Problem | Fix |
|---|---|
| `403 Google Sheets` | Check service account email has Editor access on the sheet |
| Email not sending | Verify App Password (not your Gmail password); check 2FA is enabled |
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` inside venv |
| Chart not loading | Check browser console; ensure `/api/monthly` returns 200 |
