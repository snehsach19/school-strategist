import os
import json
from datetime import datetime, timedelta
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path("data")
RAW_EMAILS_FILE = "raw_emails.json"
EVENTS_OUTPUT_FILE = "events.json"


def load_raw_emails():
    """Load raw emails from JSON file."""
    if not Path(RAW_EMAILS_FILE).exists():
        print(f"WARNING: {RAW_EMAILS_FILE} not found. Run ingest.py first.")
        return []

    with open(RAW_EMAILS_FILE) as f:
        return json.load(f)


def load_current_menus():
    """Load all current month's menu files (breakfast and lunch)."""
    now = datetime.now()
    month_suffix = f"{now.strftime('%b').upper()}_{now.year}"

    menus = []

    for menu_type in ["breakfast", "lunch"]:
        pattern = f"menu_elementary_{menu_type}_{month_suffix}*.json"
        for filepath in DATA_DIR.glob(pattern):
            with open(filepath) as f:
                data = json.load(f)
                data["_filename"] = filepath.name
                menus.append(data)

    if not menus:
        print(f"WARNING: No menu files found in {DATA_DIR}. Run scrape_web.py first.")

    return menus


def extract_events_from_emails(emails):
    """Extract events/deadlines from emails (separate from menus)."""
    client = Anthropic()

    now = datetime.now()

    # Use only the most recent emails (they have the most current calendar)
    # Sort by date descending and take recent ones
    sorted_emails = sorted(emails, key=lambda x: x.get('date', ''), reverse=True)

    # Take the 10 most recent emails with full content
    email_texts = []
    for email in sorted_emails[:10]:
        text = email.get('text', '')
        subject = email.get('subject', '')
        email_texts.append(f"Subject: {subject}\nEmail Date: {email['date']}\n{text}")

    combined_emails = "\n\n---\n\n".join(email_texts)

    prompt = f"""Extract ALL upcoming events and deadlines from these school emails.

TODAY'S DATE: {now.strftime('%Y-%m-%d')}

Return a JSON array with these fields:
- "name": Event name
- "date": Date in YYYY-MM-DD format (null if unclear)
- "type": "event" or "deadline"
- "priority": "high" for dances/major events, "medium" for meetings, "low" for minor items
- "description": Brief description
- "url": Registration or sign-up URL if mentioned (null if none)

EXTRACT EVERYTHING INCLUDING:
- ALL PTA events (dances, meetings, fundraisers, etc.)
- School holidays and no-school days
- Minimum days / early dismissal
- Tours, info nights, workshops
- Any deadlines or due dates

DATE PARSING RULES:
- School newsletters have calendar tables with month columns (JANUARY, FEBRUARY, MARCH)
- When you see "6th - Event Name" under a month column, that's the date for THAT month
- Current school year: Fall 2025, Spring 2026
- Only extract events dated {now.strftime('%B %Y')} or later

BE THOROUGH - extract every single event you find in the calendar sections.

## EMAILS:
{combined_emails}

Return ONLY valid JSON array, no other text."""

    response = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )

    return response.content[0].text


def extract_menus(menus):
    """Extract daily menu items from menu files."""
    client = Anthropic()

    now = datetime.now()
    menu_year = now.year
    menu_month = now.month

    menu_section = ""
    for menu in menus:
        meal_type = menu.get("meal_type", "menu").upper()
        menu_section += f"\n\n## {meal_type} MENU ({menu['month']}):\n{menu['text']}"

    prompt = f"""Extract daily menu items from this school menu.

Return a JSON array with these fields:
- "name": Menu item name
- "date": Date in YYYY-MM-DD format
- "type": "breakfast_menu" or "lunch_menu"
- "priority": "low"
- "description": All meal options for that day

The menu is for {now.strftime('%B')} {menu_year}:
- Day 5 = {menu_year}-{menu_month:02d}-05
- Day 6 = {menu_year}-{menu_month:02d}-06
- etc.

Skip days marked "NO SCHOOL".
{menu_section}

Return ONLY valid JSON array, no other text."""

    response = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )

    return response.content[0].text


def parse_json_response(text):
    """Try to parse JSON, handling truncation."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to fix truncated JSON by finding last complete object
        last_bracket = text.rfind('}')
        if last_bracket > 0:
            # Find matching array start
            try:
                fixed = text[:last_bracket+1] + ']'
                return json.loads(fixed)
            except:
                pass
        return None


def main():
    print("Loading data sources...")
    emails = load_raw_emails()
    menus = load_current_menus()

    print(f"Loaded {len(emails)} emails")
    print(f"Menu files: {len(menus)}")

    all_events = []

    # Phase 1: Extract events from emails
    if emails:
        print("\nPhase 1: Extracting events from emails...")
        events_result = extract_events_from_emails(emails)
        events = parse_json_response(events_result)
        if events:
            all_events.extend(events)
            print(f"  Found {len(events)} events/deadlines")
        else:
            print("  WARNING: Could not parse events response")
            with open("events_raw.txt", "w") as f:
                f.write(events_result)

    # Phase 2: Extract menus
    if menus:
        print("\nPhase 2: Extracting menus...")
        menus_result = extract_menus(menus)
        menu_items = parse_json_response(menus_result)
        if menu_items:
            all_events.extend(menu_items)
            print(f"  Found {len(menu_items)} menu items")
        else:
            print("  WARNING: Could not parse menus response")
            with open("menus_raw.txt", "w") as f:
                f.write(menus_result)

    # Save combined results
    if all_events:
        with open(EVENTS_OUTPUT_FILE, "w") as f:
            json.dump(all_events, f, indent=2)
        print(f"\nSaved {len(all_events)} total items to {EVENTS_OUTPUT_FILE}")
    else:
        print("\nNo events extracted.")


if __name__ == "__main__":
    main()
