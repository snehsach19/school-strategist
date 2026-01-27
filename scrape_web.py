import os
import json
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
from dotenv import load_dotenv

load_dotenv()

STUDENT_NUTRITION_URL = os.getenv("STUDENT_NUTRITION_URL")
DATA_DIR = Path("data")


MONTH_NAMES = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]


def get_month_suffix():
    """Get current month suffix (e.g., JAN_2026)."""
    now = datetime.now()
    return f"{now.strftime('%b').upper()}_{now.year}"


def detect_month_from_text(text):
    """Detect which month a menu PDF covers based on its content.

    Returns (month_abbr, year) like ('FEB', 2026) or None.
    """
    text_lower = text.lower()
    now = datetime.now()

    # Check for month names in the text — take the one that appears most
    best_month = None
    best_count = 0
    for i, name in enumerate(MONTH_NAMES):
        count = text_lower.count(name)
        if count > best_count:
            best_count = count
            best_month = i + 1  # 1-based month number

    if best_month and best_count >= 2:
        # Determine year: if month is earlier than August and we're past August,
        # it's next calendar year (spring semester)
        year = now.year
        if best_month < 8 and now.month >= 8:
            year = now.year + 1
        abbr = datetime(year, best_month, 1).strftime("%b").upper()
        return (abbr, year)

    return None


def find_pdf_links(url):
    """Fetch page and find all PDF links."""
    response = requests.get(url, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    pdf_links = []

    for link in soup.find_all("a", href=True):
        href = link["href"]
        filename = link.get("data-file-name", "")

        if href.lower().endswith(".pdf") or filename.lower().endswith(".pdf"):
            full_url = urljoin(url, href)
            pdf_links.append({
                "url": full_url,
                "filename": filename or href.split("/")[-1],
                "text": link.get_text(strip=True),
            })

    return pdf_links


def download_and_extract_pdf(pdf_url):
    """Download PDF and extract text."""
    response = requests.get(pdf_url, timeout=60)
    response.raise_for_status()

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(response.content)
        tmp_path = tmp.name

    try:
        reader = PdfReader(tmp_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text
    finally:
        os.unlink(tmp_path)


def classify_menu(text):
    """Classify menu based on content. Returns (level, meal_type) or None."""
    text_lower = text.lower()

    # Check for Elementary
    is_elementary = "elementary" in text_lower

    # Count occurrences to determine primary meal type
    breakfast_count = text_lower.count("breakfast")
    lunch_count = text_lower.count("lunch")

    # Determine meal type by which appears more frequently
    if is_elementary:
        if lunch_count > breakfast_count:
            return ("elementary", "lunch")
        elif breakfast_count > 0:
            return ("elementary", "breakfast")

    return None


def save_menu(text, source_url, filename, level, meal_type):
    """Save menu to JSON file. Avoids overwriting by adding suffix if needed."""
    DATA_DIR.mkdir(exist_ok=True)

    # Try to detect the actual month from the PDF content
    detected = detect_month_from_text(text)
    if detected:
        month_abbr, menu_year = detected
        month_suffix = f"{month_abbr}_{menu_year}"
        month_num = [n[:3] for n in MONTH_NAMES].index(month_abbr.lower()) + 1
        month_label = datetime(menu_year, month_num, 1).strftime("%B %Y")
    else:
        month_suffix = get_month_suffix()
        month_label = datetime.now().strftime("%B %Y")
    base_filename = f"menu_{level}_{meal_type}_{month_suffix}"
    output_filename = f"{base_filename}.json"
    filepath = DATA_DIR / output_filename

    # If file exists, add numeric suffix
    counter = 2
    while filepath.exists():
        output_filename = f"{base_filename}_{counter}.json"
        filepath = DATA_DIR / output_filename
        counter += 1

    data = {
        "source_url": source_url,
        "original_filename": filename,
        "scraped_at": datetime.now().isoformat(),
        "month": month_label,
        "level": level,
        "meal_type": meal_type,
        "text": text,
    }

    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)

    return output_filename


def scrape_menus():
    """Main function to scrape and classify all school menus."""
    print(f"Fetching menus from: {STUDENT_NUTRITION_URL}")
    print("-" * 50)

    # Find all PDF links
    pdf_links = find_pdf_links(STUDENT_NUTRITION_URL)
    if not pdf_links:
        print("ERROR: No PDF links found on page.")
        return

    print(f"Found {len(pdf_links)} PDFs. Inspecting content...\n")

    kept = []
    discarded = 0

    for pdf in pdf_links:
        print(f"  Checking: {pdf['filename'][:50]}...", end=" ")

        try:
            text = download_and_extract_pdf(pdf["url"])
            classification = classify_menu(text)

            if classification:
                level, meal_type = classification
                output_file = save_menu(
                    text, pdf["url"], pdf["filename"], level, meal_type
                )
                kept.append((output_file, level, meal_type))
                print(f"-> {level} {meal_type}")
            else:
                discarded += 1
                print("-> discarded (not elementary breakfast/lunch)")

        except Exception as e:
            discarded += 1
            print(f"-> ERROR: {e}")

    # Summary
    print("\n" + "=" * 50)
    print(f"SUMMARY: Found {len(pdf_links)} PDFs. Kept {len(kept)} relevant menus.")
    print("=" * 50)

    for filename, level, meal_type in kept:
        print(f"  - {filename}")


if __name__ == "__main__":
    scrape_menus()
