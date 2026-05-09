#!/usr/bin/env python3
"""
Weekly tickler file digest — emails a summary of recent and upcoming dates from a Google Sheet.

Reads a private Google Sheet via a service account, buckets rows by "Check on date"
into the past 7 days and the next 60 days, then emails the summary via Gmail SMTP.

Required env vars (or a .env file):
  SHEET_ID              Google Sheet ID (from the URL)
  SERVICE_ACCOUNT_FILE  Path to the service account JSON credentials
  GMAIL_USER            Sending Gmail address
  GMAIL_APP_PASSWORD    Gmail app password (not your account password)
  EMAIL_TO              Recipient address (defaults to GMAIL_USER)
"""
import sys
import os
import argparse
import doctest
import logging
from datetime import date, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib

import gspread
import pandas as pd
from dotenv import load_dotenv

load_dotenv()


def download_sheet(sheet_id, service_account_file):
    """ Download all rows from the first worksheet of a Google Sheet.
        Returns a DataFrame.
        >>> isinstance(download_sheet.__doc__, str)
        True
        """
    gc = gspread.service_account(filename=service_account_file)
    sh = gc.open_by_key(sheet_id)
    return pd.DataFrame(sh.sheet1.get_all_records())


def expand_quarterly_rows(df, today):
    """ Expand is_quarterly rows into concrete dated rows for nearby years.
        The check-on value is like 'XXXX-02-07': 7th day of the 2nd month of
        each calendar quarter (Q1=Jan/Feb/Mar, so 2nd month = Feb).
        Generates dates for the previous, current, and next year.
        >>> import pandas as pd
        >>> from datetime import date
        >>> today = date(2026, 5, 6)
        >>> row = {"event": "Q", "check-on": "XXXX-02-07", "notes": "", "related-url": ""}
        >>> expanded = expand_quarterly_rows(pd.DataFrame([row]), today)
        >>> len(expanded)
        12
        >>> date(2026, 5, 7) in list(expanded["check-on"])
        True
        """
    QUARTER_STARTS = [1, 4, 7, 10]
    years = [today.year - 1, today.year, today.year + 1]

    expanded_rows = []
    for _, row in df.iterrows():
        parts = str(row["check-on"]).split("-")
        if len(parts) != 3:
            continue
        try:
            q_month = int(parts[1])
            q_day = int(parts[2])
        except ValueError:
            continue
        if q_month not in (1, 2, 3):
            logging.warning(f"Quarterly pattern {row['check-on']!r} has invalid month offset {q_month} (must be 1–3), skipping")
            continue
        for year in years:
            for qs in QUARTER_STARTS:
                actual_month = qs + (q_month - 1)
                try:
                    d = date(year, actual_month, q_day)
                except ValueError:
                    continue
                new_row = row.to_dict()
                new_row["check-on"] = d
                expanded_rows.append(new_row)

    return pd.DataFrame(expanded_rows)


def process_dates(df, today=None):
    """ Bucket rows into past-week and next-60-days based on 'check-on'.
        Rows with unparseable dates are silently dropped.
        Rows with is_quarterly=True use a quarterly date pattern (XXXX-MM-DD).
        >>> import pandas as pd
        >>> from datetime import date, timedelta
        >>> today = date(2026, 5, 2)
        >>> rows = [
        ...     {"event": "A", "check-on": "2026-04-28", "is_quarterly": False},
        ...     {"event": "B", "check-on": "2026-05-10", "is_quarterly": False},
        ...     {"event": "C", "check-on": "2026-09-01", "is_quarterly": False},
        ...     {"event": "D", "check-on": "XXXX-02-05", "is_quarterly": True},
        ... ]
        >>> past, upcoming = process_dates(pd.DataFrame(rows), today=today)
        >>> list(past["event"])
        ['A']
        >>> set(upcoming["event"]) == {"B", "D"}
        True
        >>> rows2 = [{"event": "A", "check-on": "2026-04-28"}, {"event": "B", "check-on": "2026-05-10"}]
        >>> past2, upcoming2 = process_dates(pd.DataFrame(rows2), today=today)
        >>> list(past2["event"]), list(upcoming2["event"])
        (['A'], ['B'])
        """
    if today is None:
        today = date.today()
    col = "check-on"

    is_quarterly = df.get("is_quarterly", pd.Series(False, index=df.index))
    is_quarterly = is_quarterly.apply(lambda v: v is True or str(v).strip().upper() == "TRUE")

    quarterly_df = df[is_quarterly].copy()
    regular_df = df[~is_quarterly].copy()

    regular_df[col] = pd.to_datetime(regular_df[col], errors="coerce").dt.date
    regular_df = regular_df.dropna(subset=[col])

    if not quarterly_df.empty:
        quarterly_expanded = expand_quarterly_rows(quarterly_df, today)
    else:
        quarterly_expanded = pd.DataFrame()

    combined = pd.concat([regular_df, quarterly_expanded], ignore_index=True) if not quarterly_expanded.empty else regular_df

    past = combined[(combined[col] >= today - timedelta(days=7)) & (combined[col] <= today)]
    upcoming = combined[(combined[col] > today) & (combined[col] <= today + timedelta(days=60))]

    return past.sort_values(col), upcoming.sort_values(col)


def format_rows(df):
    """ Format a DataFrame of tickler rows as a plain-text bullet list.
        >>> import pandas as pd
        >>> rows = [{"event": "Test", "check-on": "2026-05-01", "notes": "hi", "related-url": ""}]
        >>> "Test" in format_rows(pd.DataFrame(rows))
        True
        """
    if df.empty:
        return "  (none)"
    lines = []
    for _, row in df.iterrows():
        event = row.get("event", "Untitled")
        check_date = row.get("check-on", "")
        notes = row.get("notes", "")
        url = row.get("related-url", "")
        line = f"  * {event} ({check_date})"
        if notes and not pd.isna(notes):
            line += f"\n    {notes}"
        if url and not pd.isna(url) and url not in ("N/A", ""):
            line += f"\n    {url}"
        lines.append(line)
    return "\n\n".join(lines)


def build_email(past, upcoming):
    """ Return (subject, body) for the weekly digest email.
        >>> import pandas as pd
        >>> subject, body = build_email(pd.DataFrame(), pd.DataFrame())
        >>> "Tickler" in subject
        True
        """
    today = date.today()
    subject = f"Tickler File — {today.strftime('%B %d, %Y')}"
    body = f"""Weekly Tickler Summary
{'=' * 40}

HAPPENED IN THE LAST 7 DAYS
{'-' * 40}
{format_rows(past)}

COMING UP IN THE NEXT 60 DAYS
{'-' * 40}
{format_rows(upcoming)}
"""
    return subject, body


def send_email(subject, body, gmail_user, app_password, email_to):
    """ Send a plain-text email via Gmail SMTP. """
    msg = MIMEMultipart()
    msg["From"] = gmail_user
    msg["To"] = email_to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(gmail_user, app_password)
        server.sendmail(gmail_user, email_to, msg.as_string())


def main(args):
    """ Handle the command line. """
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s"
    )

    sheet_id = args.sheet_id or os.environ["SHEET_ID"]
    service_account_file = args.service_account_file or os.environ["SERVICE_ACCOUNT_FILE"]
    gmail_user = os.environ["GMAIL_USER"]
    app_password = os.environ["GMAIL_APP_PASSWORD"]
    email_to = os.environ.get("EMAIL_TO", gmail_user)

    logging.debug(f"Downloading sheet {sheet_id}")
    df = download_sheet(sheet_id, service_account_file)
    logging.debug(f"Downloaded {len(df)} rows")

    past, upcoming = process_dates(df)
    logging.info(f"{len(past)} past-week rows, {len(upcoming)} upcoming rows")

    subject, body = build_email(past, upcoming)

    if args.dry_run:
        print(f"Subject: {subject}\n")
        print(body)
        return 0

    send_email(subject, body, gmail_user, app_password, email_to)
    logging.info(f"Sent: {subject}")
    return 0


def build_parser(args):
    """ Handle argparse and make it testable.
        >>> args = build_parser(['--verbose'])
        >>> print(args.verbose)
        True
        >>> args = build_parser(['--dry-run'])
        >>> print(args.dry_run)
        True
        """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-v", "--verbose", dest="verbose", default=False, action="store_true")
    parser.add_argument("-t", "--test", dest="test", default=False, action="store_true", help="Run doctests.")
    parser.add_argument("--dry-run", dest="dry_run", default=False, action="store_true", help="Print the email instead of sending it.")
    parser.add_argument("--sheet-id", dest="sheet_id", default=None, help="Override SHEET_ID env var.")
    parser.add_argument("--service-account-file", dest="service_account_file", default=None, help="Override SERVICE_ACCOUNT_FILE env var.")
    args = parser.parse_args(args)
    return args


if __name__ == "__main__":
    args = build_parser(sys.argv[1:])

    if args.test:
        doctest.testmod(verbose=args.verbose)
        sys.exit(0)

    sys.exit(main(args))
