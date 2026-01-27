import os
import json
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path("data")
RAW_EMAILS_FILE = "raw_emails.json"
PTA_FILE = DATA_DIR / "pta_page.json"
DISTRICT_FILE = DATA_DIR / "district_calendar.json"
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


def load_pta_page():
    """Load scraped PTA page data."""
    if not PTA_FILE.exists():
        print(f"WARNING: {PTA_FILE} not found. Run scrape_pta.py first.")
        return None

    with open(PTA_FILE) as f:
        data = json.load(f)

    return data.get("text", "")


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


def load_district_calendar():
    """Load scraped district calendar data."""
    if not DISTRICT_FILE.exists():
        print(f"WARNING: {DISTRICT_FILE} not found. Run scrape_district.py first.")
        return None

    with open(DISTRICT_FILE) as f:
        data = json.load(f)

    return data.get("text", "")


def extract_events_from_pta(pta_text):
    """Extract events from PTA website text."""
    client = Anthropic()

    now = datetime.now()

    prompt = f"""Extract ALL upcoming events from this PTA website page.

TODAY'S DATE: {now.strftime('%Y-%m-%d')}

Return a JSON array with these fields:
- "name": Event name
- "date": Date in YYYY-MM-DD format (null if unclear)
- "time": Time of event if mentioned (e.g., "6:00 PM - 8:00 PM"), null if not stated
- "type": "event" or "deadline"
- "priority": "high" for dances/fundraisers/major school events, "medium" for meetings/assemblies, "low" for minor items
- "description": Brief description including any relevant details
- "url": Registration or sign-up URL if mentioned (null if none)
- "source": "pta_website"

EXTRACT EVERYTHING INCLUDING:
- PTA events (dances, fundraisers, socials, Galentine's Night Out, etc.)
- School assemblies and performances (Author Assembly, Variety Show, etc.)
- PTA meetings
- Volunteer opportunities
- Deadlines for sign-ups or registrations
- Any other events or dates mentioned

RULES:
- Current school year: Fall 2025, Spring 2026
- Only extract events dated {now.strftime('%Y-%m-%d')} or later
- If a date is ambiguous, use the next upcoming occurrence
- Include as much detail as available (times, locations, costs, links)

## PTA WEBSITE CONTENT:
{pta_text}

Return ONLY valid JSON array, no other text."""

    response = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )

    return response.content[0].text


def extract_events_from_district(district_text):
    """Extract events from district calendar text."""
    client = Anthropic()

    now = datetime.now()

    prompt = f"""Extract ALL upcoming events from this SJUSD district calendar.

TODAY'S DATE: {now.strftime('%Y-%m-%d')}

Return a JSON array with these fields:
- "name": Event name
- "date": Date in YYYY-MM-DD format (null if unclear)
- "time": Time of event if mentioned (e.g., "6:00 PM - 8:00 PM"), null if not stated
- "type": "event" or "deadline"
- "priority": "high" for school holidays/no-school days, "medium" for board meetings/info nights, "low" for minor items
- "description": Brief description including location if available
- "url": Related URL if mentioned (null if none)
- "source": "district_calendar"

EXTRACT EVERYTHING INCLUDING:
- School holidays and recesses (Winter Recess, Spring Break, etc.)
- No-school days (MLK Day, Presidents' Day, etc.)
- Board of Education meetings
- Information nights and open houses
- District-wide events and programs
- Early dismissal or minimum days
- Any other district events or dates

RULES:
- Current school year: Fall 2025, Spring 2026
- Only extract events dated {now.strftime('%Y-%m-%d')} or later
- If a date is ambiguous, use the next upcoming occurrence
- Include as much detail as available (times, locations)

## DISTRICT CALENDAR CONTENT:
{district_text}

Return ONLY valid JSON array, no other text."""

    response = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )

    return response.content[0].text


def deduplicate_events(email_events, pta_events, district_events=None):
    """Merge email, PTA, and district events, removing duplicates.

    Priority order for duplicates: district > PTA > email
    (more specific sources tend to have better details).
    """
    # Combine PTA + district into one "enriched" pool
    enriched = list(pta_events or []) + list(district_events or [])

    if not enriched:
        return email_events or []
    if not email_events:
        # Still need to dedup between PTA and district
        return _dedup_pair(list(pta_events or []), list(district_events or []))

    merged = []
    used_enriched_indices = set()

    for email_event in email_events:
        email_name = (email_event.get("name") or "").lower()
        email_date = email_event.get("date")

        # Skip menu items — they never come from other sources
        if email_event.get("type") in ("breakfast_menu", "lunch_menu"):
            merged.append(email_event)
            continue

        best_match_idx = None
        best_similarity = 0

        for i, other_event in enumerate(enriched):
            if i in used_enriched_indices:
                continue

            other_name = (other_event.get("name") or "").lower()
            other_date = other_event.get("date")

            similarity = SequenceMatcher(None, email_name, other_name).ratio()

            # Same date + similar name (>0.5) = duplicate
            if email_date and other_date and email_date == other_date and similarity > 0.5:
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match_idx = i
            # Very similar name (>0.8) even without date match
            elif similarity > 0.8:
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match_idx = i

        if best_match_idx is not None:
            # Enriched version wins
            used_enriched_indices.add(best_match_idx)
            merged.append(enriched[best_match_idx])
        else:
            merged.append(email_event)

    # Add any enriched events that didn't match an email event
    for i, event in enumerate(enriched):
        if i not in used_enriched_indices:
            merged.append(event)

    # Dedup within the merged set (PTA vs district duplicates)
    return _dedup_within(merged)


def _dedup_pair(primary, secondary):
    """Dedup secondary into primary. Primary wins on conflicts."""
    if not secondary:
        return primary
    if not primary:
        return secondary

    result = list(primary)
    for sec_event in secondary:
        sec_name = (sec_event.get("name") or "").lower()
        sec_date = sec_event.get("date")
        is_dup = False

        for pri_event in primary:
            pri_name = (pri_event.get("name") or "").lower()
            pri_date = pri_event.get("date")
            similarity = SequenceMatcher(None, sec_name, pri_name).ratio()

            if sec_date and pri_date and sec_date == pri_date and similarity > 0.5:
                is_dup = True
                break
            elif similarity > 0.8:
                is_dup = True
                break

        if not is_dup:
            result.append(sec_event)

    return result


def _dedup_within(events):
    """Remove duplicates within a single list of events."""
    if len(events) <= 1:
        return events

    keep = []
    for i, event in enumerate(events):
        name = (event.get("name") or "").lower()
        date = event.get("date")
        is_dup = False

        for j in range(i):
            other = events[j]
            other_name = (other.get("name") or "").lower()
            other_date = other.get("date")
            similarity = SequenceMatcher(None, name, other_name).ratio()

            if date and other_date and date == other_date and similarity > 0.5:
                is_dup = True
                break
            elif similarity > 0.8:
                is_dup = True
                break

        if not is_dup:
            keep.append(event)

    return keep


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
    pta_text = load_pta_page()
    district_text = load_district_calendar()

    print(f"Loaded {len(emails)} emails")
    print(f"Menu files: {len(menus)}")
    print(f"PTA page: {'loaded' if pta_text else 'not available'}")
    print(f"District calendar: {'loaded' if district_text else 'not available'}")

    email_events = []
    menu_events = []
    pta_events = []
    district_events = []

    # Phase 1: Extract events from emails
    if emails:
        print("\nPhase 1: Extracting events from emails...")
        events_result = extract_events_from_emails(emails)
        events = parse_json_response(events_result)
        if events:
            email_events.extend(events)
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
            menu_events.extend(menu_items)
            print(f"  Found {len(menu_items)} menu items")
        else:
            print("  WARNING: Could not parse menus response")
            with open("menus_raw.txt", "w") as f:
                f.write(menus_result)

    # Phase 3: Extract events from PTA website
    if pta_text:
        print("\nPhase 3: Extracting events from PTA website...")
        pta_result = extract_events_from_pta(pta_text)
        pta_parsed = parse_json_response(pta_result)
        if pta_parsed:
            pta_events.extend(pta_parsed)
            print(f"  Found {len(pta_parsed)} PTA events")
        else:
            print("  WARNING: Could not parse PTA events response")
            with open("pta_events_raw.txt", "w") as f:
                f.write(pta_result)

    # Phase 4: Extract events from district calendar
    if district_text:
        print("\nPhase 4: Extracting events from district calendar...")
        district_result = extract_events_from_district(district_text)
        district_parsed = parse_json_response(district_result)
        if district_parsed:
            district_events.extend(district_parsed)
            print(f"  Found {len(district_parsed)} district events")
        else:
            print("  WARNING: Could not parse district events response")
            with open("district_events_raw.txt", "w") as f:
                f.write(district_result)

    # Deduplicate email + PTA + district events
    merged_events = deduplicate_events(email_events, pta_events, district_events)
    print(f"\nAfter dedup: {len(merged_events)} events "
          f"(from {len(email_events)} email + {len(pta_events)} PTA "
          f"+ {len(district_events)} district)")

    # Combine with menu events (no dedup needed for menus)
    all_events = merged_events + menu_events

    # Save combined results
    if all_events:
        with open(EVENTS_OUTPUT_FILE, "w") as f:
            json.dump(all_events, f, indent=2)
        print(f"\nSaved {len(all_events)} total items to {EVENTS_OUTPUT_FILE}")
    else:
        print("\nNo events extracted.")


if __name__ == "__main__":
    main()
