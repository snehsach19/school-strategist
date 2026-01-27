import os
import json
from datetime import date
from dotenv import load_dotenv
from imap_tools import MailBox, AND
from tqdm import tqdm

load_dotenv()

GMAIL_EMAIL = os.getenv("GMAIL_EMAIL")
GMAIL_PASSWORD = os.getenv("GMAIL_PASSWORD")

# School year start date
SCHOOL_YEAR_START = date(2025, 8, 1)
BATCH_SIZE = 50
OUTPUT_FILE = "raw_emails.json"


def fetch_parentsquare_emails(since_date=SCHOOL_YEAR_START):
    """Fetch all ParentSquare emails since the given date."""
    with MailBox("imap.gmail.com").login(GMAIL_EMAIL, GMAIL_PASSWORD) as mailbox:
        # Search for emails from ParentSquare since school year start
        criteria = AND(from_="parentsquare", date_gte=since_date)

        # Get all matching message UIDs first (lightweight)
        uids = list(mailbox.uids(criteria))
        total_count = len(uids)

        if total_count == 0:
            print("No ParentSquare emails found.")
            return []

        print(f"Found {total_count} ParentSquare emails since {since_date}")

        # Fetch in batches with progress bar
        all_emails = []
        for i in tqdm(range(0, total_count, BATCH_SIZE), desc="Fetching batches"):
            batch_uids = uids[i:i + BATCH_SIZE]
            batch_emails = list(mailbox.fetch(AND(uid=batch_uids)))
            all_emails.extend(batch_emails)

        return all_emails


def email_to_dict(email):
    """Convert email object to serializable dict."""
    return {
        "uid": email.uid,
        "subject": email.subject,
        "from": email.from_,
        "date": email.date.isoformat() if email.date else None,
        "text": email.text,
    }


def save_emails(emails, filename=OUTPUT_FILE):
    """Save emails to JSON file."""
    data = [email_to_dict(e) for e in tqdm(emails, desc="Processing")]
    with open(filename, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Saved {len(data)} emails to {filename}")


if __name__ == "__main__":
    print(f"Connecting as: {GMAIL_EMAIL}")
    print(f"Fetching emails since: {SCHOOL_YEAR_START}")
    print("-" * 50)

    emails = fetch_parentsquare_emails()

    if emails:
        save_emails(emails)
