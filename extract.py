import os
import json
import re
from datetime import datetime, timedelta, date
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
    """Load current and next month's menu files (breakfast and lunch)."""
    now = datetime.now()
    current_suffix = f"{now.strftime('%b').upper()}_{now.year}"

    # Next month
    if now.month == 12:
        next_month = datetime(now.year + 1, 1, 1)
    else:
        next_month = datetime(now.year, now.month + 1, 1)
    next_suffix = f"{next_month.strftime('%b').upper()}_{next_month.year}"

    menus = []

    for menu_type in ["breakfast", "lunch"]:
        for suffix in [current_suffix, next_suffix]:
            pattern = f"menu_elementary_{menu_type}_{suffix}*.json"
            for filepath in DATA_DIR.glob(pattern):
                with open(filepath) as f:
                    data = json.load(f)
                    data["_filename"] = filepath.name
                    menus.append(data)

    if not menus:
        print(f"WARNING: No menu files found in {DATA_DIR}. Run scrape_web.py first.")

    return menus


def load_pta_page():
    """Load scraped PTA page data including images."""
    if not PTA_FILE.exists():
        print(f"WARNING: {PTA_FILE} not found. Run scrape_pta.py first.")
        return None, []

    with open(PTA_FILE) as f:
        data = json.load(f)

    text = data.get("text", "")
    images = data.get("images", [])
    return text, images


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
- "location": Location/venue if mentioned (e.g., "Cafeteria", "Library", "MPR", "Gym") - null if not specified
- "url": Registration or sign-up URL if mentioned (null if none)
- "image_url": Flyer or event image URL if found near the event mention (look for .jpg, .png, .jpeg URLs from s3.amazonaws.com or cdn.filestackcontent.com) - null if none

EXTRACT events relevant to ELEMENTARY SCHOOL students and parents:
- ALL PTA events (dances, meetings, fundraisers, etc.)
- School holidays and no-school days
- Minimum days / early dismissal
- Tours, info nights, workshops for elementary
- Any deadlines or due dates relevant to elementary students

DO NOT EXTRACT:
- Middle school information nights or events
- High school information nights or events
- Events specific to a named middle or high school
- District committee or board meetings

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
    """Load scraped district calendar data (events page + student calendar PDF)."""
    if not DISTRICT_FILE.exists():
        print(f"WARNING: {DISTRICT_FILE} not found. Run scrape_district.py first.")
        return None

    with open(DISTRICT_FILE) as f:
        data = json.load(f)

    parts = []
    if data.get("text"):
        parts.append(data["text"])
    if data.get("student_calendar"):
        parts.append(f"=== Student Calendar (Important Dates) ===\n{data['student_calendar']}")

    return "\n\n".join(parts) if parts else None


def parse_student_calendar_dates():
    """Parse the student calendar PDF text to extract no-school and important dates.

    This directly parses date ranges like '16-20February Winter recess' from the
    student calendar, expanding them into individual day events. More reliable
    than LLM extraction for structured date ranges.
    """
    if not DISTRICT_FILE.exists():
        return []

    with open(DISTRICT_FILE) as f:
        data = json.load(f)

    text = data.get("student_calendar", "")
    if not text:
        return []

    now = datetime.now()

    # Determine school year: Aug+ = current year start, else previous year
    if now.month >= 8:
        fall_year = now.year
    else:
        fall_year = now.year - 1
    spring_year = fall_year + 1

    MONTH_MAP = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
    }

    # Match patterns like "16-20February Winter recess" or "26-28November Thanksgiving recess"
    # Also handles single-day patterns like "19December All schools out 2 hours early"
    pattern = re.compile(
        r'(\d{1,2})(?:-(\d{1,2}))?\s*(January|February|March|April|May|June|July|August|September|October|November|December)\s+(.+?)(?:\n|$)',
        re.IGNORECASE,
    )

    events = []
    today = now.date()

    for match in pattern.finditer(text):
        start_day = int(match.group(1))
        end_day = int(match.group(2)) if match.group(2) else start_day
        month_name = match.group(3)
        description = match.group(4).strip()

        month_num = MONTH_MAP[month_name.lower()]

        # Assign the right year based on month (Aug-Dec = fall_year, Jan-Jul = spring_year)
        if month_num >= 8:
            year = fall_year
        else:
            year = spring_year

        # Determine if this is a no-school/recess event
        desc_lower = description.lower()
        is_no_school = any(kw in desc_lower for kw in ["recess", "no school", "holiday"])
        is_early_release = "hours early" in desc_lower or "early" in desc_lower

        # Skip secondary-only early release days
        if "secondary" in desc_lower and "all" not in desc_lower:
            continue

        if is_no_school:
            event_name = description.rstrip(".")
            if "no school" not in event_name.lower():
                event_name = f"{event_name} (No School)"
            priority = "high"
        elif is_early_release:
            event_name = description.rstrip(".")
            priority = "medium"
        else:
            # Skip non-relevant items (graduation ceremonies, extended year, etc.)
            continue

        # Create one event per day in the range
        for day in range(start_day, end_day + 1):
            try:
                event_date = date(year, month_num, day)
            except ValueError:
                continue

            if event_date < today:
                continue

            # Skip weekends
            if event_date.weekday() >= 5:
                continue

            events.append({
                "name": event_name,
                "date": event_date.isoformat(),
                "time": None,
                "type": "event",
                "priority": priority,
                "description": description,
                "url": None,
                "source": "student_calendar",
            })

    return events


def analyze_image_content(client, image_url):
    """Use vision to understand what an image contains."""
    import base64
    import requests as req

    try:
        # Download image
        response = req.get(image_url, timeout=10)
        if response.status_code != 200:
            return None

        # Encode as base64
        image_data = base64.standard_b64encode(response.content).decode("utf-8")

        # Determine media type
        content_type = response.headers.get("content-type", "image/jpeg")
        if "png" in content_type or image_url.endswith(".png"):
            media_type = "image/png"
        elif "gif" in content_type:
            media_type = "image/gif"
        else:
            media_type = "image/jpeg"

        # Ask Claude to describe the image
        result = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=200,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_data,
                        }
                    },
                    {
                        "type": "text",
                        "text": "What event or activity is this flyer/image about? Reply with just the event name or 'unknown' if not an event flyer. Keep it to 5 words max."
                    }
                ]
            }]
        )
        return result.content[0].text.strip()
    except Exception as e:
        print(f"    Error analyzing image: {e}")
        return None


def extract_events_from_pta(pta_text, pta_images=None):
    """Extract events from PTA website text and images."""
    client = Anthropic()

    now = datetime.now()

    # Build images context with analyzed content
    images_context = ""
    image_map = {}  # Map event descriptions to image URLs

    if pta_images:
        print("  Analyzing images with vision...")
        images_context = "\n\nIMAGES FOUND ON PAGE:\n"
        for i, img in enumerate(pta_images):
            # Extract clean URL from Google proxy URLs
            url = img.get("url", "")
            if "#" in url:
                url = url.split("#")[-1]  # Get the actual URL after #

            # Skip small icons and logos
            if any(x in url.lower() for x in ["button", "header", "logo"]):
                continue

            # Analyze image content
            description = analyze_image_content(client, url)
            if description and description.lower() != "unknown":
                images_context += f"- Image about '{description}': {url}\n"
                image_map[description.lower()] = url
                print(f"    Found: {description}")

    prompt = f"""Extract ALL upcoming events from this PTA website page.

TODAY'S DATE: {now.strftime('%Y-%m-%d')}

Return a JSON array with these fields:
- "name": Event name
- "date": Date in YYYY-MM-DD format (null if unclear)
- "time": Time of event if mentioned (e.g., "6:00 PM - 8:00 PM"), null if not stated
- "type": "event" or "deadline"
- "priority": "high" for dances/fundraisers/major school events, "medium" for meetings/assemblies, "low" for minor items
- "description": Brief description including any relevant details
- "location": Location/venue if mentioned (e.g., "Cafeteria", "Library", "MPR", "Gym", "Auditorium") - null if not specified
- "url": Registration, sign-up, or related URL if mentioned (null if none). Look carefully for hyperlinks near event descriptions — include signup.com, Google Forms, external sites, etc.
- "image_url": Flyer or event image URL if found (look for .jpg, .png, .jpeg image URLs) - null if none
- "source": "pta_website"

EXTRACT EVERYTHING INCLUDING:
- PTA events (dances, fundraisers, socials, Galentine's Night Out, etc.)
- School assemblies and performances (Author Assembly, Variety Show, etc.)
- PTA meetings
- Volunteer opportunities
- Deadlines for sign-ups or registrations
- Any other events or dates mentioned

IMPORTANT:
- Capture any URLs associated with events. Look for links labeled "HERE", "Sign Up", "Register", or embedded in the text near event descriptions.
- Match images to events based on the image descriptions provided. If an image description matches an event name, use that image URL for the event's image_url field.

RULES:
- Current school year: Fall 2025, Spring 2026
- Only extract events dated {now.strftime('%Y-%m-%d')} or later
- If a date is ambiguous, use the next upcoming occurrence
- Include as much detail as available (times, locations, costs, links)

## PTA WEBSITE CONTENT:
{pta_text}
{images_context}

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

    prompt = f"""Extract upcoming events from this SJUSD district calendar that are relevant to ELEMENTARY SCHOOL students and parents.

TODAY'S DATE: {now.strftime('%Y-%m-%d')}

Return a JSON array with these fields:
- "name": Event name
- "date": Date in YYYY-MM-DD format (null if unclear)
- "time": Time of event if mentioned (e.g., "6:00 PM - 8:00 PM"), null if not stated
- "type": "event" or "deadline"
- "priority": "high" for school holidays/no-school days, "medium" for other events, "low" for minor items
- "description": Brief description including location if available
- "url": Related URL if mentioned (null if none)
- "source": "district_calendar"

ONLY EXTRACT events that affect ELEMENTARY schools:
- School holidays and recesses that affect ALL schools (Winter Recess, Spring Break, MLK Day, etc.)
- Early dismissal or minimum days for elementary or all schools
- District-wide events that affect elementary students

DO NOT EXTRACT:
- Middle school information nights
- High school information nights
- Board of Education meetings
- District committee meetings (PTOC, Schools of Tomorrow, CSH, VIP, etc.)
- Advisory committees
- Secondary-school-only early dismissals
- Any event specific to a named middle or high school
- Webinars or seminars for district staff

RULES:
- Current school year: Fall 2025, Spring 2026
- Only extract events dated {now.strftime('%Y-%m-%d')} or later
- For recesses and no-school days, set priority to "high"

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
            # Very similar name (>0.8) when at least one has no date
            elif similarity > 0.8 and (not email_date or not other_date):
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
            elif similarity > 0.8 and (not sec_date or not pri_date):
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
        ev_date = event.get("date")
        is_dup = False

        for j in range(i):
            other = events[j]
            other_name = (other.get("name") or "").lower()
            other_date = other.get("date")
            similarity = SequenceMatcher(None, name, other_name).ratio()

            if ev_date and other_date and ev_date == other_date and similarity > 0.5:
                is_dup = True
                break
            elif similarity > 0.8 and (not ev_date or not other_date):
                is_dup = True
                break

        if not is_dup:
            keep.append(event)

    return keep


def consolidate_consecutive_dates(events):
    """Merge events with same name on consecutive dates into single entries."""
    from collections import defaultdict

    # Separate events that should be consolidated vs those that shouldn't
    to_consolidate = []
    others = []

    # Keywords that indicate multi-day events to consolidate
    consolidate_keywords = ["recess", "no school", "holiday", "break", "vacation"]

    for event in events:
        name = (event.get("name") or "").lower()
        if any(kw in name for kw in consolidate_keywords) and event.get("date"):
            to_consolidate.append(event)
        else:
            others.append(event)

    if not to_consolidate:
        return events

    # Group by normalized name
    groups = defaultdict(list)
    for event in to_consolidate:
        # Normalize name for grouping
        name = event.get("name", "")
        groups[name].append(event)

    consolidated = []
    for name, group in groups.items():
        # Sort by date
        group.sort(key=lambda x: x.get("date", ""))

        # Find consecutive date ranges
        ranges = []
        current_range = [group[0]]

        for i in range(1, len(group)):
            prev_date = date.fromisoformat(group[i - 1]["date"])
            curr_date = date.fromisoformat(group[i]["date"])

            # Check if consecutive (including skipping weekends)
            diff = (curr_date - prev_date).days
            if diff == 1 or (diff <= 3 and prev_date.weekday() == 4):  # Friday to Monday
                current_range.append(group[i])
            else:
                ranges.append(current_range)
                current_range = [group[i]]

        ranges.append(current_range)

        # Create consolidated events
        for r in ranges:
            if len(r) == 1:
                consolidated.append(r[0])
            else:
                # Merge into single event with date range
                start_date = r[0]["date"]
                end_date = r[-1]["date"]

                merged = r[0].copy()
                merged["date"] = start_date
                merged["end_date"] = end_date

                # Format nice date range for display
                start = date.fromisoformat(start_date)
                end = date.fromisoformat(end_date)
                if start.month == end.month:
                    date_display = f"{start.strftime('%b %d')}-{end.strftime('%d')}"
                else:
                    date_display = f"{start.strftime('%b %d')} - {end.strftime('%b %d')}"
                merged["date_display"] = date_display

                consolidated.append(merged)

    return others + consolidated


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
    pta_text, pta_images = load_pta_page()
    district_text = load_district_calendar()

    print(f"Loaded {len(emails)} emails")
    print(f"Menu files: {len(menus)}")
    print(f"PTA page: {'loaded' if pta_text else 'not available'} ({len(pta_images)} images)")
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
        pta_result = extract_events_from_pta(pta_text, pta_images)
        pta_parsed = parse_json_response(pta_result)
        if pta_parsed:
            pta_events.extend(pta_parsed)
            print(f"  Found {len(pta_parsed)} PTA events")
        else:
            print("  WARNING: Could not parse PTA events response")
            with open("pta_events_raw.txt", "w") as f:
                f.write(pta_result)

    # Phase 4a: Parse student calendar dates directly (recesses, no-school days)
    print("\nPhase 4a: Parsing student calendar dates...")
    student_cal_events = parse_student_calendar_dates()
    if student_cal_events:
        district_events.extend(student_cal_events)
        print(f"  Found {len(student_cal_events)} student calendar events")
    else:
        print("  No student calendar dates found")

    # Phase 4b: Extract other events from district calendar via LLM
    if district_text:
        print("\nPhase 4b: Extracting events from district calendar...")
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

    # Consolidate consecutive date events (e.g., Winter Recess Mon-Fri)
    print("\nConsolidating consecutive date events...")
    before_count = len(all_events)
    all_events = consolidate_consecutive_dates(all_events)
    print(f"  Consolidated {before_count} -> {len(all_events)} events")

    # Save combined results
    if all_events:
        with open(EVENTS_OUTPUT_FILE, "w") as f:
            json.dump(all_events, f, indent=2)
        print(f"\nSaved {len(all_events)} total items to {EVENTS_OUTPUT_FILE}")
    else:
        print("\nNo events extracted.")


if __name__ == "__main__":
    main()
