# 💸 RoomiePay – Shared Expense Tracker

A full-stack Flask web application for managing shared expenses among roommates with Google Sheets integration, email notifications, and a modern data-driven dashboard.

---

## ✨ Features

| Feature | Details |
|---|---|
| **Expense Tracking** | Add expenses per member with date & time tracking |
| **Google Sheets Sync** | Auto-updates live spreadsheet after every entry |
| **Email Notifications** | HTML emails sent to roommates after updates |
| **Dashboard** | Member stats, bar charts, daily trends, ledger, recent transactions |
| **Settlement** | Who-owes-whom calculated automatically |
| **Monthly History** | Clickable archive of past months with settlement details |
| **Anomaly Detection** | Flags unusually high spenders |
| **ML Prediction** | Predicts next month's expenses via linear regression |
| **Exports** | Download data as CSV or Excel |
| **Auth** | Simple shared group password |
| **Mobile Ready** | Fully responsive + dark mode support |
| **Production Deploy** | Ready for Vercel / Render / Railway |

---

## 📁 Project Structure

```
roommate-expenses/
├── app.py                  # Flask app, 19+ routes, auth
├── requirements.txt        # 15 dependencies
├── vercel.json             # Vercel config (Python 3.12)
├── .env                    # Environment variables (NOT pushed)
├── credentials.json        # Google service account (NOT pushed)
├── credentials_b64.txt     # Base64 credentials for Vercel (NOT pushed)
├── utils/
│   ├── sheets_handler.py   # Google Sheets read/write, syncing
│   ├── email_service.py    # SMTP email notifications
│   └── calculations.py     # Settlement, anomaly, ML predict
└── templates/
    ├── base.html           # Shared styles, nav, components
    ├── login.html          # Login page
    └── dashboard.html      # Main dashboard (900+ lines)
```

---

## 🚀 Local Setup

### 1. Clone & Install

```bash
git clone <your-repo-url>
cd roommate-expenses
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Google Sheets API Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project → Enable **Google Sheets API**
3. **IAM & Admin → Service Accounts → Create Service Account → Keys → Add JSON Key**
4. Save as `credentials.json` in project root
5. Create a [Google Sheet](https://sheets.google.com)
6. Share with service account email (from `credentials.json`) with **Editor** access

### 3. Gmail App Password

1. Enable 2-Step Verification in your Google Account
2. **Security → App Passwords → Generate for Mail**
3. Copy the 16-character password

### 4. Environment Config

```bash
# Create .env file
SECRET_KEY=your-random-secret-here
ROOMMATES=Aman,Rahul,Shubham
GOOGLE_SHEET_ID=<from-sheet-url>
GOOGLE_CREDENTIALS_FILE=credentials.json
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
EMAIL_SENDER=your@gmail.com
EMAIL_PASSWORD=<16-char-app-password>
EMAIL_RECIPIENTS=aman@gmail.com,rahul@gmail.com
APP_PASSWORD=roomie2024
```

### 5. Run Locally

```bash
python app.py
# Visit http://localhost:5000 → Login with APP_PASSWORD
```

---

## 🌐 Dashboard Features

| Section | Description |
|---|---|
| **Member Stats** | All-time totals + spending share % per member |
| **Who Owes Whom** | Settlement calculations with arrow flows |
| **Monthly Spending** | Bar chart (this month or all-time toggle) |
| **Recent Transactions** | Last 5 entries with timestamps |
| **Daily Trend Chart** | Line chart (last 5/10 days) |
| **Monthly History** | Clickable archive showing past months |
| **Expense Ledger** | Full data table with date sorting |
| **Quick Add** | Desktop form + mobile modal |
| **Export** | Download CSV or Excel |

---

## 🚀 Deploy to Vercel

### Step 1: Push to GitHub

```bash
git add .
git commit -m "Ready for Vercel deployment"
git push origin master
```

### Step 2: Import Project on Vercel

1. Go to **https://vercel.com/new**
2. Click **"Import Git Repository"**
3. Select your **roommate-expenses** repo

### Step 3: Add Environment Variables

In Vercel → **Settings → Environment Variables**, add:

| Variable | Value | Scope |
|---|---|---|
| `GOOGLE_CREDENTIALS_B64` | Base64 from `credentials_b64.txt` | All |
| `GOOGLE_SHEET_ID` | Your sheet ID | All |
| `ROOMMATES` | `Aman,Rahul,Shubham` | All |
| `SECRET_KEY` | Random strong string | All |
| `SMTP_SERVER` | `smtp.gmail.com` | All |
| `SMTP_PORT` | `587` | All |
| `EMAIL_SENDER` | Your Gmail | All |
| `EMAIL_PASSWORD` | 16-char app password | All |
| `EMAIL_RECIPIENTS` | Comma-separated emails | All |
| `APP_PASSWORD` | `roomie2024` | All |

### Step 4: Deploy

1. After setting env vars, click **Deploy**
2. Wait 2-3 minutes
3. Get your live URL → Share with roommates! 🎉

---

## 📊 Google Sheet Format

Auto-managed by the app:

| Date | Aman | Rahul | Shubham |
|---|---|---|---|
| 2024-06-01 | 140(14:30:45)+64(15:20:10) | 300(16:00:00) | |
| 2024-06-02 | | 150(10:15:30) | 200+50 |

- **Header row**: Colored member names (auto-created)
- **Data cells**: `amount(HH:MM:SS)+amount+...` format
- **Sorting**: Auto-sorted by date, newest first

---

## 🔌 API Endpoints (19 routes)

| Endpoint | Method | Returns |
|---|---|---|
| `/` | GET | Login page (if not authenticated) |
| `/dashboard` | GET | Main dashboard |
| `/add` | POST | Add expense, redirect |
| `/api/totals` | GET | All-time totals per member |
| `/api/monthly?year=&month=` | GET | Monthly totals |
| `/api/table` | GET | Full sheet data |
| `/api/settlement` | GET | Settlement calculations |
| `/api/daily-expenses` | GET | Daily trend data |
| `/api/archived-months` | GET | Past month summaries |
| `/api/month-details?year=&month=` | GET | Month details with transactions |
| `/api/predict` | GET | ML spending prediction |
| `/export/csv` | GET | Download CSV |
| `/export/excel` | GET | Download Excel |

---

## 🔐 Security

| Item | Status |
|---|---|
| `.env` file | ✅ Protected (.gitignore) |
| `credentials.json` | ✅ Protected (.gitignore) |
| `credentials_b64.txt` | ✅ Protected (.gitignore) |
| Vercel secrets | ✅ Set via environment variables |
| Group password | ✅ `APP_PASSWORD` env var |

**Never commit sensitive files!** Use Vercel environment variables for production.

---

## 🐛 Troubleshooting

| Problem | Solution |
|---|---|
| `403 Google Sheets Error` | Verify service account has **Editor** access on sheet |
| Email not sending | Check 2FA enabled + 16-char app password correct |
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` |
| Vercel deployment fails | Check logs + verify all env vars are set |
| Charts not loading | Check browser console → ensure APIs return 200 |
| `GOOGLE_CREDENTIALS_B64 not set` | Add to Vercel environment variables |

---

## 📦 Tech Stack

- **Backend**: Flask 3.0.3, Python 3.12
- **Database**: Google Sheets API
- **Frontend**: HTML/CSS/JavaScript, Chart.js, Jinja2
- **ML**: scikit-learn (linear regression)
- **Email**: SMTP via Gmail
- **Deployment**: Vercel, Render, Railway compatible

---

## 📝 License

Open source – feel free to fork and customize!

---

## 💡 Quick Start Checklist

- [ ] Clone repo
- [ ] Create Python venv
- [ ] Install requirements
- [ ] Set up Google Sheets API credentials
- [ ] Create Gmail app password
- [ ] Configure `.env`
- [ ] Run locally: `python app.py`
- [ ] Push to GitHub
- [ ] Deploy on Vercel
- [ ] Add environment variables in Vercel
- [ ] Click Deploy
- [ ] Share URL with roommates! 🎉
