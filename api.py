"""Simple API server for the React frontend to call Claude."""

import json
import os
import re
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


def clean_email_text(text):
    """Strip HTML tags, URLs, and excess whitespace from email text."""
    clean = re.sub(r'<[^>]+>', ' ', text)
    clean = re.sub(r'https?://\S+', '[link]', clean)
    clean = re.sub(r'&nbsp;', ' ', clean)
    clean = re.sub(r'&[a-z]+;', ' ', clean)
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean


def format_all_emails(emails):
    """Format all emails as clean text for full context."""
    if not emails:
        return ""

    sorted_emails = sorted(emails, key=lambda e: e.get("date") or "", reverse=True)
    formatted = []
    for email in sorted_emails:
        subject = email.get("subject") or "No subject"
        date = email.get("date") or ""
        body = email.get("body") or email.get("text") or ""
        clean_body = clean_email_text(body)
        formatted.append(f"--- {subject} ({date}) ---\n{clean_body}")

    return "\n\n".join(formatted)


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

    # All events (including past 2 weeks for "what happened" questions)
    all_events = [
        e for e in events
        if e.get("type") in ["event", "deadline"] and (e.get("date") or "") >= two_weeks_ago
    ]
    all_events = sorted(all_events, key=lambda x: x.get("date", ""))

    past_events = [e for e in all_events if (e.get("date") or "") < today]
    upcoming_events = [e for e in all_events if (e.get("date") or "") >= today]

    # All menus
    all_breakfast = sorted(
        [e for e in events if e.get("type") == "breakfast_menu" and (e.get("date") or "") >= today],
        key=lambda x: x.get("date", "")
    )
    all_lunch = sorted(
        [e for e in events if e.get("type") == "lunch_menu" and (e.get("date") or "") >= today],
        key=lambda x: x.get("date", "")
    )

    # Format events with day-of-week
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

    # Include ALL email content — the assistant should have read everything
    all_emails_text = format_all_emails(emails)

    system_prompt = f"""You are a friendly, helpful assistant for parents at Los Alamitos Elementary School. You have read ALL school email communications, and you have access to school events and lunch/breakfast menus.

Today is {today_display}.

You are like the most well-informed parent at school — you've read every email, every newsletter, every announcement. When a parent asks you something, you can draw on all of that knowledge.

Be warm and conversational. Keep answers concise but complete. Include the day of the week when mentioning dates. If you're not sure about something, say so rather than guessing."""

    user_prompt = f"""ALL SCHOOL EMAIL COMMUNICATIONS (most recent first):
{all_emails_text}

RECENT PAST EVENTS (last 2 weeks):
{past_events_text}

UPCOMING EVENTS AND DEADLINES:
{upcoming_events_text}

BREAKFAST MENUS:
{breakfast_text}

LUNCH MENUS:
{lunch_text}

IMPORTANT: When your answer mentions a specific event or date, include a Google Calendar link INLINE right after the event name so parents know what they're adding. Example:
**Valentine's Day Celebration** [+ Add to Calendar](https://calendar.google.com/calendar/render?action=TEMPLATE&text=Valentines+Day+Celebration&dates=20260214/20260215)
Use URL-encoded event name (+ for spaces). For single-day events, end date = next day. For multi-day, use actual start/end. Do NOT group calendar links at the bottom — always place them next to the event they belong to.

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
