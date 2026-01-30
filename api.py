"""Simple API server for the React frontend to call Claude."""

import json
import os
from datetime import datetime
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


@app.route("/api/ask", methods=["POST"])
def ask_assistant():
    """Answer questions about school events using Claude."""
    data = request.get_json()
    question = data.get("question", "").strip()

    if not question:
        return jsonify({"error": "No question provided"}), 400

    events = load_events()

    # Build context
    today = datetime.now().strftime("%Y-%m-%d")
    today_display = datetime.now().strftime("%A, %B %d, %Y")

    # Pre-search: Extract meaningful words from question and search menus
    question_lower = question.lower()

    # Common words to ignore when searching
    stop_words = {'when', 'is', 'the', 'a', 'an', 'are', 'there', 'what', 'how', 'do', 'does',
                  'we', 'have', 'any', 'next', 'coming', 'up', 'for', 'lunch', 'breakfast',
                  'menu', 'school', 'day', 'week', 'today', 'tomorrow', 'this', 'that', 'it',
                  'can', 'i', 'my', 'kid', 'child', 'serve', 'served', 'serving', 'get', 'will', 'be'}

    # Extract search words (4+ chars, not in stop words)
    search_words = [w.strip('?.,!') for w in question_lower.split()
                    if len(w) >= 4 and w.strip('?.,!') not in stop_words]

    # Search menus for any matching words
    search_results = ""
    if search_words:
        all_menus = [e for e in events if e.get("type") in ["breakfast_menu", "lunch_menu"] and e.get("date", "") >= today]
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
                    matches.append(f"- {menu['date']} ({meal_type}): {menu.get('description', '')}")
                    break

        if matches:
            search_results = f"\n\nSEARCH RESULTS FOR '{', '.join(matched_words).upper()}':\n" + "\n".join(matches[:15])

    # Separate events by type for clearer context
    upcoming_events = [
        e for e in events
        if e.get("type") in ["event", "deadline"] and e.get("date", "") >= today
    ]
    upcoming_events = sorted(upcoming_events, key=lambda x: x.get("date", ""))[:25]

    # Get menus for the next 2 weeks
    breakfast_menus = [
        e for e in events
        if e.get("type") == "breakfast_menu" and e.get("date", "") >= today
    ]
    breakfast_menus = sorted(breakfast_menus, key=lambda x: x.get("date", ""))[:14]

    lunch_menus = [
        e for e in events
        if e.get("type") == "lunch_menu" and e.get("date", "") >= today
    ]
    lunch_menus = sorted(lunch_menus, key=lambda x: x.get("date", ""))[:14]

    # Format events in a readable way
    def format_event(e):
        date = e.get("date", "TBD")
        name = e.get("name", "Unnamed")
        desc = e.get("description", "")
        date_display = e.get("date_display", date)
        if desc:
            return f"- {date_display}: {name} - {desc}"
        return f"- {date_display}: {name}"

    def format_menu(e):
        date = e.get("date", "")
        desc = e.get("description", "")
        return f"- {date}: {desc}"

    events_text = "\n".join(format_event(e) for e in upcoming_events) or "No upcoming events found."
    breakfast_text = "\n".join(format_menu(e) for e in breakfast_menus) or "No breakfast menus available."
    lunch_text = "\n".join(format_menu(e) for e in lunch_menus) or "No lunch menus available."

    prompt = f"""You are a helpful assistant for Los Alamitos Elementary School parents. You help them understand school events, menus, and schedules.

Today is {today_display}.
{search_results}

UPCOMING EVENTS AND DEADLINES:
{events_text}

BREAKFAST MENUS (next 2 weeks):
{breakfast_text}

LUNCH MENUS (next 2 weeks):
{lunch_text}

INSTRUCTIONS:
- If there are SEARCH RESULTS above, use those to answer - they show ALL dates when the food is available
- Answer questions directly and concisely
- Be friendly and helpful

Question: {question}"""

    try:
        response = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}]
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
