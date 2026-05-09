# Tickler File Manager
A second brain for reminding you of dates important to you.

This script will email you a weekly rundown of recently past and upcoming entries in your tickler file.

If you don't have a tickler file, [this short post will get you started](https://joemurph.com/article/detail/tickler-files-for-journalists/).

This assumes you are hosting the spreadsheet that acts as your tickler file on Google Sheets. TODO: Allow arbitrary CSV endpoint for tickler file.

Note that parts of this README and parts of the tickler.py code were written with AI.

## Setup

The hard stuff:

### 1. Google Sheets API

1. In [Google Cloud Console](https://console.cloud.google.com), enable the **Google Sheets API** for your project.
2. Go to **APIs & Services → Credentials → Create Credentials → Service account**. Download the JSON key and save it locally (e.g. `service_account.json`).
3. Share your Google Sheet with the service account's email address (Viewer access is enough).

### 2. Gmail app password

In your Google Account, go to **Security → 2-Step Verification → App passwords** and generate a password for this script.

### 3. Config

Copy the example .env file:
```bash
cp .env.example .env
```

Fill in `.env`:

| Variable | Description |
|---|---|
| `SHEET_ID` | The long ID from your sheet's URL |
| `SERVICE_ACCOUNT_FILE` | Absolute path to the service account JSON |
| `GMAIL_USER` | Your Gmail address |
| `GMAIL_APP_PASSWORD` | The app password from step 2 |
| `EMAIL_TO` | Recipient address (defaults to `GMAIL_USER`) |

### 4. Install dependencies

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 5. Schedule

```bash
launchctl load ~/Library/LaunchAgents/com.joemurphy.tickler.plist
```

## Usage

Preview the email without sending:

```bash
python tickler.py --dry-run
```

Send immediately:

```bash
python tickler.py
```

Run doctests:

```bash
python tickler.py --test
```

Verbose logging:

```bash
python tickler.py --verbose --dry-run
```

Override sheet or credentials without editing `.env`:

```bash
python tickler.py --sheet-id YOUR_ID --service-account-file /path/to/creds.json --dry-run
```

Logs from the scheduled run are written to `tickler.log`.
