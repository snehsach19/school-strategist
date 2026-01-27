import json
from datetime import datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

PTA_URL = "https://losalamitospta.membershiptoolkit.com/home"
DATA_DIR = Path("data")
PTA_FILE = DATA_DIR / "pta_page.json"
CACHE_HOURS = 24


def is_cache_fresh():
    """Check if cached PTA data is less than 24 hours old."""
    if not PTA_FILE.exists():
        return False

    with open(PTA_FILE) as f:
        data = json.load(f)

    scraped_at = datetime.fromisoformat(data.get("scraped_at", "2000-01-01"))
    return datetime.now() - scraped_at < timedelta(hours=CACHE_HOURS)


def fetch_pta_page(url):
    """Fetch the PTA homepage HTML."""
    response = requests.get(url, timeout=30)
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


def save_pta_data(text, url):
    """Save scraped PTA data to JSON."""
    DATA_DIR.mkdir(exist_ok=True)

    data = {
        "source_url": url,
        "scraped_at": datetime.now().isoformat(),
        "text": text,
    }

    with open(PTA_FILE, "w") as f:
        json.dump(data, f, indent=2)

    return PTA_FILE


def main():
    """Scrape PTA homepage with 24h cache."""
    if is_cache_fresh():
        print(f"PTA cache is fresh (< {CACHE_HOURS}h old). Skipping scrape.")
        print(f"  Cached file: {PTA_FILE}")
        return

    print(f"Fetching PTA page: {PTA_URL}")
    html = fetch_pta_page(PTA_URL)

    print("Extracting text content...")
    text = extract_text(html)

    print(f"Extracted {len(text)} characters of text")

    output = save_pta_data(text, PTA_URL)
    print(f"Saved to {output}")


if __name__ == "__main__":
    main()
