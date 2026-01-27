import io
import json
from datetime import datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

DISTRICT_URL = "https://www.sjusd.org/events"
DATA_DIR = Path("data")
DISTRICT_FILE = DATA_DIR / "district_calendar.json"
CACHE_HOURS = 24


def is_cache_fresh():
    """Check if cached district calendar data is less than 24 hours old."""
    if not DISTRICT_FILE.exists():
        return False

    with open(DISTRICT_FILE) as f:
        data = json.load(f)

    scraped_at = datetime.fromisoformat(data.get("scraped_at", "2000-01-01"))
    return datetime.now() - scraped_at < timedelta(hours=CACHE_HOURS)


def fetch_calendar_page(month, year):
    """Fetch the district calendar page for a given month/year."""
    response = requests.get(
        DISTRICT_URL,
        params={"month": month, "year": year},
        timeout=30,
    )
    response.raise_for_status()
    return response.text


def extract_text(html):
    """Extract main content text from HTML, stripping nav/footer/scripts."""
    soup = BeautifulSoup(html, "html.parser")

    # Remove non-content elements
    for tag in soup.find_all(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()

    # Try to find main content area
    main = soup.find("main") or soup.find("div", {"role": "main"}) or soup.find("body")
    if main is None:
        main = soup

    text = main.get_text(separator="\n", strip=True)

    # Collapse excessive blank lines
    lines = [line for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


def find_student_calendar_url(html):
    """Find the student calendar PDF URL for the current school year."""
    soup = BeautifulSoup(html, "html.parser")
    now = datetime.now()

    # Determine the current school year label (e.g., "2025-2026")
    # School year runs Aug-May, so Aug+ is the start of a new year
    if now.month >= 8:
        school_year = f"{now.year}-{now.year + 1}"
    else:
        school_year = f"{now.year - 1}-{now.year}"

    # Find links containing the school year near "Student calendar" or "English"
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if "/fs/resource-manager/view/" not in href:
            continue
        # Walk nearby text to see if this is a student calendar link
        text_context = link.get_text(strip=True)
        parent_text = link.parent.get_text(separator=" ", strip=True) if link.parent else ""
        # Look for the English student calendar for the current school year
        if school_year in parent_text and "english" in text_context.lower():
            if "student" in parent_text.lower() or "student" in text_context.lower():
                return href

    # Fallback: find any link with the school year and resource-manager
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if "/fs/resource-manager/view/" in href:
            parent_text = link.parent.get_text(separator=" ", strip=True) if link.parent else ""
            if school_year in parent_text and "english" in link.get_text(strip=True).lower():
                return href

    return None


def fetch_student_calendar_pdf(html):
    """Download and extract text from the student calendar PDF."""
    pdf_path = find_student_calendar_url(html)
    if not pdf_path:
        print("  Could not find student calendar PDF link on events page")
        return None

    # Build full URL
    if pdf_path.startswith("/"):
        pdf_url = f"https://www.sjusd.org{pdf_path}"
    else:
        pdf_url = pdf_path

    print(f"  Downloading student calendar PDF...")
    response = requests.get(pdf_url, timeout=30, allow_redirects=True)
    response.raise_for_status()

    reader = PdfReader(io.BytesIO(response.content))
    text_parts = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            text_parts.append(text)

    combined = "\n".join(text_parts)
    print(f"  Extracted {len(combined)} characters from student calendar PDF")
    return combined


def save_district_data(text, student_calendar_text=None):
    """Save scraped district calendar data to JSON."""
    DATA_DIR.mkdir(exist_ok=True)

    data = {
        "source_url": DISTRICT_URL,
        "scraped_at": datetime.now().isoformat(),
        "text": text,
    }
    if student_calendar_text:
        data["student_calendar"] = student_calendar_text

    with open(DISTRICT_FILE, "w") as f:
        json.dump(data, f, indent=2)

    return DISTRICT_FILE


def main():
    """Scrape district calendar (current month events + student calendar PDF) with 24h cache."""
    if is_cache_fresh():
        print(f"District calendar cache is fresh (< {CACHE_HOURS}h old). Skipping scrape.")
        print(f"  Cached file: {DISTRICT_FILE}")
        return

    now = datetime.now()

    # Fetch the events page (current month)
    month_name = now.strftime("%B %Y")
    print(f"Fetching district calendar: {month_name}")
    html = fetch_calendar_page(now.month, now.year)

    print(f"  Extracting text content for {month_name}...")
    events_text = extract_text(html)
    print(f"  Extracted {len(events_text)} characters")

    # Also fetch the student calendar PDF (has all important dates for the year)
    print("Fetching student calendar PDF...")
    student_cal_text = fetch_student_calendar_pdf(html)

    combined = f"=== {month_name} Events ===\n{events_text}"
    output = save_district_data(combined, student_cal_text)
    print(f"\nSaved combined calendar to {output}")


if __name__ == "__main__":
    main()
