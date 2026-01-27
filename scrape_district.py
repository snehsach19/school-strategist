import json
from datetime import datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

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


def save_district_data(text):
    """Save scraped district calendar data to JSON."""
    DATA_DIR.mkdir(exist_ok=True)

    data = {
        "source_url": DISTRICT_URL,
        "scraped_at": datetime.now().isoformat(),
        "text": text,
    }

    with open(DISTRICT_FILE, "w") as f:
        json.dump(data, f, indent=2)

    return DISTRICT_FILE


def main():
    """Scrape district calendar (current + next month) with 24h cache."""
    if is_cache_fresh():
        print(f"District calendar cache is fresh (< {CACHE_HOURS}h old). Skipping scrape.")
        print(f"  Cached file: {DISTRICT_FILE}")
        return

    now = datetime.now()
    # Current month + next month
    months = [
        (now.month, now.year),
    ]
    # Handle December -> January rollover
    if now.month == 12:
        months.append((1, now.year + 1))
    else:
        months.append((now.month + 1, now.year))

    all_text = []
    for month, year in months:
        month_name = datetime(year, month, 1).strftime("%B %Y")
        print(f"Fetching district calendar: {month_name}")
        html = fetch_calendar_page(month, year)

        print(f"  Extracting text content for {month_name}...")
        text = extract_text(html)
        print(f"  Extracted {len(text)} characters")

        all_text.append(f"=== {month_name} ===\n{text}")

    combined = "\n\n".join(all_text)
    output = save_district_data(combined)
    print(f"\nSaved combined calendar to {output}")


if __name__ == "__main__":
    main()
