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

# Configure CORS for production
FRONTEND_URL = os.getenv("FRONTEND_URL", "*")
CORS(app, origins=[FRONTEND_URL] if FRONTEND_URL != "*" else "*")

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
    emails = load_emails()

    # Build context
    today = datetime.now().strftime("%Y-%m-%d")
    today_display = datetime.now().strftime("%A, %B %d, %Y")

    # Upcoming events summary
    upcoming = [
        e for e in events
        if e.get("type") in ["event", "deadline"] and e.get("date", "") >= today
    ]
    upcoming = sorted(upcoming, key=lambda x: x.get("date", ""))[:30]

    # Upcoming menus (breakfast and lunch)
    upcoming_menus = [
        e for e in events
        if e.get("type") in ["breakfast_menu", "lunch_menu"] and e.get("date", "") >= today
    ]
    upcoming_menus = sorted(upcoming_menus, key=lambda x: x.get("date", ""))[:40]

    events_context = json.dumps(upcoming, indent=2)
    menus_context = json.dumps(upcoming_menus, indent=2)

    # Recent email subjects for context
    email_summary = "\n".join([
        f"- {e.get('subject', 'No subject')} ({e.get('date', 'No date')})"
        for e in emails[:20]
    ])

    prompt = f"""You are a helpful assistant for a school calendar app called "Los Alamitos Elementary Smart Calendar".

Today is {today_display}.

Here are the upcoming school events:
{events_context}

Here are the upcoming school menus (breakfast and lunch):
{menus_context}

Recent email subjects from ParentSquare:
{email_summary}

Answer the user's question concisely and helpfully. If you're not sure about something, say so.
Focus on being practical and giving actionable information.

User's question: {question}"""

    try:
        response = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=500,
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
