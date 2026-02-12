"""Simple API server for the React frontend to call Claude."""

import json
import os
from datetime import datetime, timedelta
from flask import Flask, jsonify, request
from flask_cors import CORS
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Configure CORS for production - allow all origins for simplicity
CORS(app, resources={r"/api/*": {"origins": "*"}})

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

EVENTS_FILE = "events.json"
RAW_EMAILS_FILE = "raw_emails.json"


def load_events():
    """Load events from JSON file."""
    try:
        with open(EVENTS_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def load_emails():
    """Load raw emails for context."""
    try:
        with open(RAW_EMAILS_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def date_with_day(date_str):
    """Format a date string as 'Wednesday, 2025-02-12'."""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        return f"{d.strftime('%A')}, {date_str}"
    except (ValueError, TypeError):
        return date_str


def search_emails(emails, search_words):
    """Search raw emails for keyword matches, return relevant excerpts."""
    if not search_words or not emails:
        return ""

    matches = []
    for email in emails:
        subject = (email.get("subject") or "").lower()
        body = (email.get("body") or email.get("text") or "").lower()
        email_text = f"{subject} {body}"

        for word in search_words:
            if word in email_text:
                subj = email.get("subject") or "No subject"
                date = email.get("date") or ""
                body_raw = email.get("body") or email.get("text") or ""
                # Truncate body to ~2000 chars
                excerpt = body_raw[:2000]
                if len(body_raw) > 2000:
                    excerpt += "..."
                matches.append(f"--- Email: {subj} ({date}) ---\n{excerpt}")
                break

    if matches:
        return "\n\nRELEVANT EMAIL CONTENT:\n" + "\n\n".join(matches[:5])
    return ""


def get_recent_email_subjects(emails, count=4):
    """Get the most recent email subjects as general context."""
    if not emails:
        return ""

    # Sort by date descending (most recent first)
    sorted_emails = sorted(emails, key=lambda e: e.get("date") or "", reverse=True)
    subjects = []
    for email in sorted_emails[:count]:
        subj = email.get("subject") or "No subject"
        date = email.get("date") or ""
        subjects.append(f"- {date}: {subj}")

    if subjects:
        return "\n\nRECENT SCHOOL COMMUNICATIONS:\n" + "\n".join(subjects)
    return ""


@app.route("/api/ask", methods=["POST"])
def ask_assistant():
    """Answer questions about school events using Claude."""
    data = request.get_json()
    question = data.get("question", "").strip()

    if not question:
        return jsonify({"error": "No question provided"}), 400

    events = load_events()
    emails = load_emails()

    # Build context
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    today_display = now.strftime("%A, %B %d, %Y")
    two_weeks_ago = (now - timedelta(days=14)).strftime("%Y-%m-%d")

    # Pre-search: Extract meaningful words from question and search menus/emails
    question_lower = question.lower()

    # Common words to ignore when searching
    stop_words = {'when', 'is', 'the', 'a', 'an', 'are', 'there', 'what', 'how', 'do', 'does',
                  'we', 'have', 'any', 'next', 'coming', 'up', 'for', 'lunch', 'breakfast',
                  'menu', 'school', 'day', 'week', 'today', 'tomorrow', 'this', 'that', 'it',
                  'can', 'i', 'my', 'kid', 'child', 'serve', 'served', 'serving', 'get', 'will', 'be',
                  'about', 'from', 'with', 'tell', 'know', 'news', 'update', 'latest', 'recent'}

    # Extract search words (4+ chars, not in stop words)
    search_words = [w.strip('?.,!') for w in question_lower.split()
                    if len(w) >= 4 and w.strip('?.,!') not in stop_words]

    # Search menus for any matching words
    menu_search_results = ""
    if search_words:
        all_menus = [e for e in events if e.get("type") in ["breakfast_menu", "lunch_menu"] and (e.get("date") or "") >= today]
        all_menus = sorted(all_menus, key=lambda x: x.get("date", ""))

        matches = []
        matched_words = set()
        for menu in all_menus:
            desc = (menu.get("description") or "").lower()
            name = (menu.get("name") or "").lower()
            menu_text = f"{name} {desc}"
            for word in search_words:
                if word in menu_text:
                    matched_words.add(word)
                    meal_type = "Breakfast" if menu.get("type") == "breakfast_menu" else "Lunch"
                    matches.append(f"- {date_with_day(menu['date'])} ({meal_type}): {menu.get('description', '')}")
                    break

        if matches:
            menu_search_results = f"\n\nMENU SEARCH RESULTS FOR '{', '.join(matched_words).upper()}':\n" + "\n".join(matches[:15])

    # Search emails for matching words
    email_search_results = search_emails(emails, search_words)

    # Get recent email subjects as general context
    recent_emails_context = get_recent_email_subjects(emails)

    # All events (including past 2 weeks for "what happened" questions)
    all_events = [
        e for e in events
        if e.get("type") in ["event", "deadline"] and (e.get("date") or "") >= two_weeks_ago
    ]
    all_events = sorted(all_events, key=lambda x: x.get("date", ""))

    past_events = [e for e in all_events if (e.get("date") or "") < today]
    upcoming_events = [e for e in all_events if (e.get("date") or "") >= today]

    # All menus (data is small enough to include everything)
    all_breakfast = sorted(
        [e for e in events if e.get("type") == "breakfast_menu" and (e.get("date") or "") >= today],
        key=lambda x: x.get("date", "")
    )
    all_lunch = sorted(
        [e for e in events if e.get("type") == "lunch_menu" and (e.get("date") or "") >= today],
        key=lambda x: x.get("date", "")
    )

    # Format events in a readable way with day-of-week
    def format_event(e):
        date = e.get("date", "TBD")
        name = e.get("name", "Unnamed")
        desc = e.get("description", "")
        display = date_with_day(date)
        if desc:
            return f"- {display}: {name} - {desc}"
        return f"- {display}: {name}"

    def format_menu(e):
        date = (e.get("date") or "")
        desc = e.get("description", "")
        return f"- {date_with_day(date)}: {desc}"

    past_events_text = "\n".join(format_event(e) for e in past_events) or "No recent past events."
    upcoming_events_text = "\n".join(format_event(e) for e in upcoming_events) or "No upcoming events found."
    breakfast_text = "\n".join(format_menu(e) for e in all_breakfast) or "No breakfast menus available."
    lunch_text = "\n".join(format_menu(e) for e in all_lunch) or "No lunch menus available."

    system_prompt = f"""You are a friendly, helpful assistant for parents at Los Alamitos Elementary School. You have access to school events, lunch/breakfast menus, and recent school email communications.

Today is {today_display}.

Be warm and conversational — like a fellow school parent who always knows what's going on. Keep answers concise but complete. If you're not sure about something, say so rather than guessing."""

    user_prompt = f"""{menu_search_results}{email_search_results}{recent_emails_context}

RECENT PAST EVENTS (last 2 weeks):
{past_events_text}

UPCOMING EVENTS AND DEADLINES:
{upcoming_events_text}

BREAKFAST MENUS:
{breakfast_text}

LUNCH MENUS:
{lunch_text}

INSTRUCTIONS:
- If there are MENU SEARCH RESULTS above, use those to answer — they show ALL dates when the food is available
- If there is RELEVANT EMAIL CONTENT above, use it to answer questions about school news, district updates, closures, etc.
- Include the day of the week when mentioning dates (e.g., "Wednesday, February 12")
- Answer questions directly and concisely
- Be friendly and helpful — like a fellow parent who's in the know

Question: {question}"""

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}]
        )
        answer = response.content[0].text
        return jsonify({"answer": answer})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/events", methods=["GET"])
def get_events():
    """Return all events as JSON."""
    events = load_events()
    return jsonify(events)


@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint for deployment platforms."""
    return jsonify({"status": "healthy"})


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5001))
    debug = os.getenv("FLASK_ENV") == "development"
    app.run(host="0.0.0.0", port=port, debug=debug)
