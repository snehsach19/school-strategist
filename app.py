import json
import textwrap
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import streamlit as st
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()


def _html(markup):
    """Render HTML via st.markdown, stripping indentation and blank lines."""
    # dedent removes common leading whitespace
    # then filter out blank lines so Markdown never sees a blank line
    # (a blank line inside an HTML block terminates the block in CommonMark)
    lines = textwrap.dedent(markup).splitlines()
    clean = "\n".join(line for line in lines if line.strip())
    st.markdown(clean, unsafe_allow_html=True)


EVENTS_FILE = "events.json"
RAW_EMAILS_FILE = "raw_emails.json"

st.set_page_config(
    page_title="Rishan's School Strategist",
    page_icon="🎒",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# --- CSS ---
st.markdown("""
<style>
    /* Light background */
    .stApp {
        background: #f8f9fb;
    }

    /* Header bar */
    .header-bar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 0.75rem 0;
        border-bottom: 2px solid #6366f1;
        margin-bottom: 1.25rem;
    }
    .header-bar .app-name {
        font-size: 1.35rem;
        font-weight: 700;
        color: #1f2937;
    }
    .header-bar .header-date {
        font-size: 0.95rem;
        color: #6b7280;
        font-weight: 500;
    }

    /* Stat chips */
    .stat-chips {
        display: flex;
        gap: 0.75rem;
        margin-bottom: 1.5rem;
    }
    .stat-chip {
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        background: #eef2ff;
        color: #4338ca;
        font-size: 0.85rem;
        font-weight: 600;
        padding: 0.35rem 0.85rem;
        border-radius: 999px;
    }

    /* Section headers */
    .section-label {
        font-size: 0.7rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #9ca3af;
        margin: 1.5rem 0 0.75rem 0;
    }

    /* Cards (general) */
    .card {
        background: white;
        border-radius: 12px;
        padding: 1.25rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
        border: 1px solid #f3f4f6;
        margin-bottom: 0.75rem;
    }
    .card-header {
        font-size: 0.75rem;
        font-weight: 700;
        color: #9ca3af;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        margin-bottom: 0.5rem;
    }
    .card-value {
        font-size: 1.05rem;
        color: #1f2937;
        line-height: 1.5;
    }

    /* Menu items */
    .menu-item {
        border-radius: 10px;
        padding: 1rem;
        margin: 0.25rem 0;
        border-left: 5px solid #10b981;
    }
    .menu-item.breakfast {
        border-left-color: #f59e0b;
        background: #fffbeb;
    }
    .menu-item.lunch {
        border-left-color: #3b82f6;
        background: #eff6ff;
    }
    .menu-item .card-value {
        font-size: 1.05rem;
        font-weight: 500;
        color: #1e293b;
        line-height: 1.5;
    }

    /* Week strip */
    .week-strip-cell {
        background: white;
        border-radius: 12px;
        padding: 0.75rem 0.5rem;
        text-align: center;
        border: 1px solid #f3f4f6;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
        cursor: pointer;
        transition: border-color 0.15s;
    }
    .week-strip-cell:hover {
        border-color: #c7d2fe;
    }
    .week-strip-cell.today {
        border-color: #6366f1;
        box-shadow: 0 0 0 2px #c7d2fe;
    }
    .week-strip-cell .ws-day {
        font-size: 0.7rem;
        font-weight: 600;
        text-transform: uppercase;
        color: #9ca3af;
    }
    .week-strip-cell .ws-num {
        font-size: 1.4rem;
        font-weight: 700;
        color: #1f2937;
        margin: 0.15rem 0;
    }
    .week-strip-cell.today .ws-num {
        color: #6366f1;
    }
    .week-strip-cell .ws-dot {
        font-size: 0.55rem;
        color: #ef4444;
    }
    .week-strip-cell .ws-lunch {
        font-size: 0.65rem;
        color: #9ca3af;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        max-width: 100%;
        display: block;
        margin-top: 0.2rem;
    }

    /* Day detail panel */
    .day-detail-header {
        font-size: 1rem;
        font-weight: 600;
        color: #374151;
        margin-bottom: 0.75rem;
    }

    /* Event cards — tiered */
    .ev-card {
        background: white;
        border-radius: 12px;
        padding: 1rem 1.15rem;
        margin-bottom: 0.75rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
        border: 1px solid #e5e7eb;
        border-left: 4px solid #6366f1;
        position: relative;
        transition: box-shadow 0.15s, transform 0.15s;
    }
    .ev-card:hover {
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
        transform: translateY(-1px);
    }
    .ev-card.high {
        border-left-color: #ef4444;
        background: linear-gradient(135deg, #fff 70%, #fef2f2 100%);
    }
    .ev-card.low {
        padding: 0.65rem 1rem;
        background: #fafafa;
        border-left-color: #d1d5db;
    }
    .ev-top-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 0.25rem;
    }
    .ev-date {
        font-size: 0.75rem;
        color: #9ca3af;
        font-weight: 500;
    }
    .ev-badge {
        font-size: 0.65rem;
        font-weight: 700;
        padding: 0.15rem 0.5rem;
        border-radius: 999px;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }
    .ev-badge.today { background: #dcfce7; color: #15803d; }
    .ev-badge.soon { background: #fef3c7; color: #92400e; }
    .ev-badge.action { background: #fee2e2; color: #b91c1c; }
    .ev-icon-name {
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }
    .ev-icon {
        font-size: 1.3rem;
        flex-shrink: 0;
    }
    .ev-name {
        font-size: 0.95rem;
        font-weight: 600;
        color: #1f2937;
    }
    .ev-nudge {
        font-size: 0.85rem;
        color: #4b5563;
        line-height: 1.5;
        margin-top: 0.35rem;
        padding: 0.4rem 0.65rem;
        background: #f9fafb;
        border-radius: 8px;
        border: 1px solid #f3f4f6;
    }
    .ev-desc {
        font-size: 0.82rem;
        color: #6b7280;
        line-height: 1.4;
        margin-top: 0.25rem;
    }
    .ev-time {
        font-size: 0.75rem;
        color: #6366f1;
        font-weight: 600;
        margin-right: 0.5rem;
    }
    .ev-actions {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        margin-top: 0.5rem;
        flex-wrap: wrap;
    }
    .ev-cal {
        display: inline-flex;
        align-items: center;
        gap: 0.3rem;
        padding: 0.3rem 0.75rem;
        background: #f0fdf4;
        color: #15803d;
        border: 1px solid #bbf7d0;
        border-radius: 6px;
        font-size: 0.75rem;
        font-weight: 600;
        text-decoration: none;
        transition: background 0.15s;
    }
    .ev-cal:hover { background: #dcfce7; color: #15803d !important; }
    .ev-cta {
        display: inline-block;
        margin-top: 0;
        padding: 0.4rem 1rem;
        background: #ef4444;
        color: white !important;
        border-radius: 8px;
        font-size: 0.8rem;
        font-weight: 600;
        text-decoration: none;
        transition: background 0.15s;
    }
    .ev-cta:hover { background: #dc2626; }
    .ev-link {
        display: inline-block;
        margin-top: 0;
        padding: 0.35rem 0.85rem;
        background: #6366f1;
        color: white !important;
        border-radius: 8px;
        font-size: 0.78rem;
        font-weight: 500;
        text-decoration: none;
        transition: background 0.15s;
    }
    .ev-link:hover { background: #4f46e5; }

    /* Timeline group header */
    .timeline-group {
        font-size: 0.72rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #6b7280;
        margin: 1.25rem 0 0.6rem 0;
        padding-bottom: 0.35rem;
        border-bottom: 2px solid #e5e7eb;
    }

    /* Time-of-day section dividers */
    .time-section {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        margin: 1.25rem 0 0.6rem 0;
        padding-bottom: 0.3rem;
        border-bottom: 1px solid #e5e7eb;
    }
    .time-section .ts-icon {
        font-size: 1rem;
    }
    .time-section .ts-label {
        font-size: 0.72rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #6b7280;
    }

    /* Chat */
    .chat-response {
        background: #f8fafc;
        border-radius: 10px;
        padding: 1rem;
        margin-top: 0.75rem;
        border-left: 4px solid #6366f1;
        font-size: 0.95rem;
        color: #374151;
        line-height: 1.6;
    }

    /* Footer */
    .app-footer {
        text-align: center;
        color: #d1d5db;
        font-size: 0.7rem;
        margin-top: 2rem;
        padding: 1rem 0;
    }

    /* Hide Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}

    /* Mobile */
    @media (max-width: 768px) {
        .header-bar { flex-direction: column; gap: 0.25rem; text-align: center; }
        .stat-chips { justify-content: center; }
        .week-strip-cell .ws-lunch { display: none; }
        .ev-card { padding: 0.65rem 0.85rem; }

        /* Force day-picker columns to stay in a single row */
        [data-testid="stHorizontalBlock"] {
            flex-wrap: nowrap !important;
            gap: 0.25rem !important;
        }
        [data-testid="stHorizontalBlock"] [data-testid="stColumn"] {
            min-width: 0 !important;
            flex: 1 1 0 !important;
        }
        [data-testid="stHorizontalBlock"] button {
            font-size: 0.7rem !important;
            padding: 0.4rem 0.1rem !important;
            white-space: nowrap !important;
        }
    }
</style>
""", unsafe_allow_html=True)


@st.cache_data
def load_events():
    if not Path(EVENTS_FILE).exists():
        return []
    with open(EVENTS_FILE) as f:
        return json.load(f)


@st.cache_data
def load_raw_emails():
    if not Path(RAW_EMAILS_FILE).exists():
        return []
    with open(RAW_EMAILS_FILE) as f:
        return json.load(f)


def get_events_for_date(events, target_date):
    target_str = target_date.strftime("%Y-%m-%d")
    return [e for e in events if e.get("date") == target_str]


def get_next_event(events, today):
    today_str = today.strftime("%Y-%m-%d")
    future_events = [
        e for e in events
        if e.get("type") in ["event", "deadline"]
        and e.get("date")
        and e.get("date") >= today_str
    ]
    if future_events:
        return min(future_events, key=lambda x: x.get("date"))
    return None


def ask_assistant(question, events, emails):
    """Use Claude to answer questions about school events."""
    client = Anthropic()

    events_context = json.dumps(events[:30], indent=2)
    emails_summary = "\n".join([
        f"- {e.get('subject', 'No subject')} ({e.get('date', 'No date')})"
        for e in emails[:20]
    ])

    prompt = f"""You are a helpful assistant for a family's school calendar app called "Rishan's School Strategist".

Answer the user's question based on this school data:

## UPCOMING EVENTS & MENUS:
{events_context}

## RECENT EMAIL SUBJECTS:
{emails_summary}

User Question: {question}

Provide a helpful, concise answer. If asked about registration or sign-up, look for URLs in the events. If you don't have the information, say so clearly.
Format any dates nicely (e.g., "Friday, February 6th").
If there are relevant links, include them."""

    response = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )

    return response.content[0].text


def event_icon(name):
    """Return an emoji icon based on event keywords."""
    n = name.lower()
    if "spirit" in n or "wear" in n or "dress" in n or "hat" in n or "hair" in n:
        return "\U0001F455"  # t-shirt
    if "dance" in n:
        return "\U0001F483"  # dancer
    if "book" in n or "author" in n or "read" in n:
        return "\U0001F4DA"  # books
    if "spelling" in n:
        return "\U0001F524"  # abc
    if "math" in n:
        return "\U0001F9EE"  # abacus
    if "picture" in n or "photo" in n:
        return "\U0001F4F8"  # camera
    if "tour" in n:
        return "\U0001F3EB"  # school
    if "open house" in n:
        return "\U0001F3E0"  # house
    if "recess" in n or "no school" in n or "minimum" in n:
        return "\U0001F3D6\uFE0F"  # beach
    if "deadline" in n:
        return "\u23F0"  # alarm clock
    if "yearbook" in n:
        return "\U0001F4D6"  # open book
    if "meeting" in n or "council" in n:
        return "\U0001F4CB"  # clipboard
    if "variety" in n or "show" in n:
        return "\U0001F3AD"  # performing arts
    if "bubble" in n:
        return "\U0001FAE7"  # bubbles
    if "chef" in n or "recipe" in n:
        return "\U0001F468\u200D\U0001F373"  # cook
    if "galentine" in n or "night out" in n:
        return "\U0001F377"  # wine glass
    if "concert" in n or "orchestra" in n:
        return "\U0001F3B6"  # musical notes
    return "\U0001F4C5"  # calendar


PTA_HOME_URL = "https://losalamitospta.membershiptoolkit.com/home"


def event_fallback_url(event):
    """Return the event URL, or a fallback for PTA events."""
    url = event.get("url")
    if url:
        return url
    n = event.get("name", "").lower()
    if "pta" in n:
        return PTA_HOME_URL
    return None


def event_start_time(event):
    """Return (display_time, hour, minute, duration_hrs, is_all_day) for an event.

    Only returns a display time when we're confident about it:
    - Events with an explicit "time" field in the data
    - All-day events (spirit days, recess, picture day)
    - Deadlines
    Otherwise returns None for display but still provides calendar defaults.
    """
    n = event.get("name", "").lower()
    etype = event.get("type", "")

    if etype in ("breakfast_menu", "lunch_menu"):
        return None  # menus don't need calendar entries

    # If the event has an explicit time field, use it
    explicit_time = event.get("time")
    if explicit_time:
        # Try to parse common formats
        for fmt in ("%I:%M %p", "%H:%M"):
            try:
                t = datetime.strptime(explicit_time, fmt)
                return (explicit_time, t.hour, t.minute, 1, False)
            except ValueError:
                continue
        return (explicit_time, None, None, None, False)

    # Confident all-day events
    if any(kw in n for kw in ["spirit", "wear", "dress", "hat", "hair", "recess",
                               "no school", "minimum", "picture", "photo"]):
        return ("All day", None, None, None, True)

    # Deadlines
    if etype == "deadline" or "deadline" in n:
        return ("Due date", None, None, None, True)

    # For everything else, don't display a time but provide a calendar default
    # so "Add to Calendar" still works with a reasonable guess
    if "dance" in n:
        return (None, 18, 0, 2, False)
    if "open house" in n:
        return (None, 17, 30, 1.5, False)
    if "meeting" in n or "council" in n:
        return (None, 18, 30, 1, False)
    if "variety" in n or "show" in n:
        return (None, 18, 0, 2, False)

    # Default: all-day for calendar
    return (None, None, None, None, True)


def google_calendar_url(event):
    """Generate a Google Calendar 'Add Event' URL."""
    name = event.get("name", "Untitled")
    desc = event.get("description") or ""
    date_str = event.get("date")
    if not date_str:
        return None

    time_info = event_start_time(event)
    if time_info is None:
        return None  # skip menus

    _, hour, minute, duration_hrs, is_all_day = time_info

    if is_all_day or hour is None or minute is None:
        # All-day: use YYYYMMDD format
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        next_day = dt + timedelta(days=1)
        dates_param = f"{dt.strftime('%Y%m%d')}/{next_day.strftime('%Y%m%d')}"
    else:
        dt = datetime.strptime(date_str, "%Y-%m-%d").replace(hour=hour, minute=minute)
        end = dt + timedelta(hours=duration_hrs)
        dates_param = f"{dt.strftime('%Y%m%dT%H%M%S')}/{end.strftime('%Y%m%dT%H%M%S')}"

    url = event_fallback_url(event)
    details = desc
    if url:
        details = f"{desc}\n\nMore info: {url}" if desc else url

    return (
        "https://calendar.google.com/calendar/render?action=TEMPLATE"
        f"&text={quote(name)}"
        f"&dates={dates_param}"
        f"&details={quote(details)}"
    )


def event_nudge(event, days_away):
    """Generate a brief, parent-friendly action nudge for an event. Always returns a non-empty string."""
    name = event.get("name", "")
    desc = event.get("description", "")
    n = name.lower()
    etype = event.get("type", "event")
    url = event.get("url")

    # When is it relative to now
    if days_away == 0:
        when = "today"
    elif days_away == 1:
        when = "tomorrow"
    elif days_away < 7:
        when = f"on {datetime.strptime(event['date'], '%Y-%m-%d').strftime('%A')}"
    else:
        event_date = datetime.strptime(event['date'], '%Y-%m-%d')
        when = f"on {event_date.strftime('%b %d')}"

    # Spirit days
    if "spirit" in n:
        clothing = name.split(":")[-1].strip() if ":" in name else desc
        return f"Rishan should {clothing.lower()} {when}!".replace("  ", " ").strip("!") + "!"

    # Dances
    if "father" in n and "daughter" in n:
        return f"Father/Daughter Dance is {when} \u2014 grab tickets if you haven\u2019t!"
    if "mother" in n and "son" in n:
        return f"Mother/Son Dance is {when} \u2014 grab tickets if you haven\u2019t!"

    # Deadlines
    if etype == "deadline" or "deadline" in n:
        action = desc.replace("Deadline to ", "").replace("Deadline for ", "").replace("Last day to ", "")
        if days_away <= 3 and days_away >= 0:
            return f"Hurry \u2014 {action.lower()} is due {when}!"
        return f"Don\u2019t forget: {action}. Due {when}."

    # No school / recess
    if "recess" in n or "no school" in n:
        return f"No school {when} \u2014 enjoy the break!"
    if "minimum" in n:
        return f"Early dismissal {when} \u2014 plan pickup accordingly."

    # Pictures
    if "picture" in n or "photo" in n:
        return f"Picture day is {when} \u2014 free dress!"

    # Specific event blurbs for known types
    if "math kangaroo" in n:
        return f"International math competition for students. Happening {when} \u2014 check with PTA for details."
    if "spelling bee" in n:
        return f"PTA Spelling Bee {when}. Good luck to the participants!"
    if "author" in n or "assembly" in n:
        extra = f": {desc}" if desc and desc.lower() != n else ""
        return f"Guest author assembly {when}{extra}."
    if "book fair" in n:
        return f"Book fair {when} \u2014 send Rishan with some spending money!"
    if "variety show" in n:
        return f"Variety show {when} \u2014 come watch the performances!"
    if "bubblefest" in n:
        return f"Bubblefest {when} \u2014 fun science show! Volunteers may be needed."
    if "open house" in n:
        return f"Open house {when} \u2014 visit Rishan\u2019s classroom and meet the teacher."
    if "tour" in n:
        return f"School tour {when}. Register if you\u2019re interested."
    if "yearbook" in n:
        return f"Yearbook-related {when}. Check details so you don\u2019t miss out."
    if "chef" in n or "recipe" in n:
        return f"Future Chefs competition {when} \u2014 submit a recipe!"
    if "meeting" in n or "council" in n:
        return f"Meeting {when}. Open to parents who want to attend."
    if "galentine" in n:
        return f"Galentine\u2019s Night Out {when} \u2014 free workout + bubbles at F45 Branham Park! Text LAMOMS to 408.549.7760 (max 30 spots)."
    if "concert" in n or "orchestra" in n:
        return f"Fundraising concert {when} \u2014 don\u2019t miss the live performance!"

    # Registration/signup events with URL
    if url:
        return f"Happening {when}. Sign up or register if you haven\u2019t yet!"

    # Generic fallback — always has content
    return f"School event happening {when}. Check with the school for details."


def event_badge(days_away, priority):
    """Return (label, css_class) for a countdown badge, or None."""
    if days_away == 0:
        return ("Today", "today")
    if days_away == 1:
        return ("Tomorrow", "soon")
    if priority == "high" and days_away <= 7:
        return ("Action needed", "action")
    if days_away <= 3:
        return (f"In {days_away} days", "soon")
    return None


def event_time_of_day(event):
    """Classify an event into morning, afternoon, or evening."""
    n = event.get("name", "").lower()
    etype = event.get("type", "")
    if etype == "breakfast_menu":
        return "morning"
    if etype == "lunch_menu":
        return "afternoon"
    # Evening: dances, meetings, open house
    if any(kw in n for kw in ["dance", "meeting", "council", "open house", "variety show"]):
        return "evening"
    # Morning: spirit days, dress code (you prepare in the morning)
    if any(kw in n for kw in ["spirit", "wear", "dress", "hat", "hair"]):
        return "morning"
    # Default school-hours events to afternoon
    return "afternoon"


def classify_event_period(event_date, today):
    """Return a group label for the event based on how far away it is."""
    delta = (event_date - today).days
    if delta < 0:
        return None
    # Current week: Mon-Sun containing today
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    next_week_end = end_of_week + timedelta(days=7)

    if event_date <= end_of_week:
        return "This Week"
    elif event_date <= next_week_end:
        return "Next Week"
    else:
        return event_date.strftime("%B")


def main():
    events = load_events()
    emails = load_raw_emails()
    today = datetime.now().date()

    if not events:
        st.error("No events found. Run `python extract.py` first.")
        return

    today_str = today.strftime("%Y-%m-%d")

    # ── 1. Header Bar ──
    _html(f"""\
        <div class="header-bar">
            <span class="app-name">Rishan's School Strategist</span>
            <span class="header-date">{today.strftime('%A, %B %d, %Y')}</span>
        </div>
    """)

    # ── 2. Stat Chips ──
    next_event = get_next_event(events, today)
    upcoming_count = len([
        e for e in events
        if e.get("type") in ["event", "deadline"] and e.get("date", "") >= today_str
    ])

    days_chip = "No upcoming events"
    if next_event and next_event.get("date"):
        event_date = datetime.strptime(next_event["date"], "%Y-%m-%d").date()
        d = (event_date - today).days
        if d == 0:
            days_chip = "Next event is today"
        elif d == 1:
            days_chip = "1 day to next event"
        else:
            days_chip = f"{d} days to next event"

    _html(f"""\
        <div class="stat-chips">
            <span class="stat-chip">{days_chip}</span>
            <span class="stat-chip">{upcoming_count} upcoming events</span>
        </div>
    """)

    # ── 3. Week Strip + Day Detail ──
    _html('<div class="section-label">This Week</div>')

    start_of_week = today - timedelta(days=today.weekday())
    week_dates = [start_of_week + timedelta(days=i) for i in range(5)]
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri"]

    if "selected_day" not in st.session_state:
        st.session_state.selected_day = today

    selected_day = st.session_state.selected_day

    # Week strip: All + Mon-Fri as 6 columns
    cols = st.columns(6, gap="small")
    with cols[0]:
        btn_type = "primary" if selected_day == "all" else "secondary"
        if st.button("All", key="day_all", use_container_width=True, type=btn_type):
            st.session_state.selected_day = "all"
            st.rerun()

    for i, (col, date) in enumerate(zip(cols[1:], week_dates)):
        with col:
            day_events = get_events_for_date(events, date)
            other_events = [e for e in day_events if e.get("type") in ["event", "deadline"]]

            dot = " \u2022" if other_events else ""
            label = f"{day_names[i]} {date.day}{dot}"

            btn_type = "primary" if date == selected_day else "secondary"
            if st.button(label, key=f"day_{i}", use_container_width=True, type=btn_type):
                st.session_state.selected_day = date
                st.rerun()

    # Day detail panel
    selected_day = st.session_state.selected_day

    if selected_day == "all":
        # Show all weekdays' meals
        _html(f'<div class="day-detail-header">This Week\'s Meals</div>')
        for date, day_name in zip(week_dates, day_names):
            day_events = get_events_for_date(events, date)
            breakfast = [e for e in day_events if e.get("type") == "breakfast_menu"]
            lunch = [e for e in day_events if e.get("type") == "lunch_menu"]
            b_text = breakfast[0].get("description", "—") if breakfast else "—"
            l_text = lunch[0].get("description", "—") if lunch else "—"
            is_today = date == today
            today_marker = ' style="border-left:3px solid #6366f1"' if is_today else ""
            _html(f"""\
                <div class="card"{today_marker}>
                    <div class="card-header">{day_name} {date.day}{"  ·  Today" if is_today else ""}</div>
                    <div class="menu-item breakfast"><div class="card-value">{b_text}</div></div>
                    <div class="menu-item lunch"><div class="card-value">{l_text}</div></div>
                </div>
            """)
        # Show all week's events
        all_week_events = []
        for date in week_dates:
            for e in get_events_for_date(events, date):
                if e.get("type") in ["event", "deadline"]:
                    all_week_events.append((date, e))
        selected_other = []
        selected_events_with_dates = all_week_events
    else:
        selected_events = get_events_for_date(events, selected_day)
        selected_breakfast = [e for e in selected_events if e.get("type") == "breakfast_menu"]
        selected_lunch = [e for e in selected_events if e.get("type") == "lunch_menu"]
        selected_other = [e for e in selected_events if e.get("type") in ["event", "deadline"]]

        _html(f'<div class="day-detail-header">{selected_day.strftime("%A, %B %d")}</div>')

        # Classify events by time of day
        morning_events = [e for e in selected_other if event_time_of_day(e) == "morning"]
        afternoon_events = [e for e in selected_other if event_time_of_day(e) == "afternoon"]
        evening_events = [e for e in selected_other if event_time_of_day(e) == "evening"]

        time_sections = {
            "morning": ("\u2600\uFE0F", "Morning"),
            "afternoon": ("\U0001F324\uFE0F", "Afternoon"),
            "evening": ("\U0001F319", "Evening"),
        }

        def render_event_card(ev):
            priority = ev.get("priority", "medium")
            url = event_fallback_url(ev)
            ev_date = datetime.strptime(ev["date"], "%Y-%m-%d").date() if ev.get("date") else today
            d_away = (ev_date - today).days
            icon = event_icon(ev.get("name", ""))
            nudge = event_nudge(ev, d_away)
            badge_info = event_badge(d_away, priority)
            time_info = event_start_time(ev)
            badge_html = (
                f'<span class="ev-badge {badge_info[1]}">{badge_info[0]}</span>'
                if badge_info else ""
            )
            time_html = f'<span class="ev-time">{time_info[0]}</span>' if time_info and time_info[0] else ""
            nudge_html = f'<div class="ev-nudge">{nudge}</div>' if nudge else ""
            link_html = (
                f'<a href="{url}" target="_blank" class="ev-cta">Register &rarr;</a>'
                if url and priority == "high"
                else (f'<a href="{url}" target="_blank" class="ev-link">Details &rarr;</a>' if url else "")
            )
            cal_url = google_calendar_url(ev)
            cal_html = f'<a href="{cal_url}" target="_blank" class="ev-cal">+ Add to Calendar</a>' if cal_url else ""
            actions_html = ""
            if link_html or cal_html:
                actions_html = f'<div class="ev-actions">{link_html}{cal_html}</div>'
            _html(f"""\
                <div class="ev-card {priority}">
                    <div class="ev-top-row">
                        <div class="ev-icon-name">
                            {time_html}
                            <span class="ev-icon">{icon}</span>
                            <span class="ev-name">{ev.get('name', '')}</span>
                        </div>
                        {badge_html}
                    </div>
                    {nudge_html}
                    {actions_html}
                </div>
            """)

        # ── Morning ──
        _html(f'<div class="time-section"><span class="ts-icon">{time_sections["morning"][0]}</span><span class="ts-label">{time_sections["morning"][1]}</span></div>')
        breakfast_text = (
            selected_breakfast[0].get("description", "No menu")
            if selected_breakfast
            else "No school or menu not available"
        )
        _html(f"""\
            <div class="card">
                <div class="card-header">Breakfast</div>
                <div class="menu-item breakfast">
                    <div class="card-value">{breakfast_text}</div>
                </div>
            </div>
        """)
        for ev in morning_events:
            render_event_card(ev)

        # ── Afternoon ──
        _html(f'<div class="time-section"><span class="ts-icon">{time_sections["afternoon"][0]}</span><span class="ts-label">{time_sections["afternoon"][1]}</span></div>')
        lunch_text = (
            selected_lunch[0].get("description", "No menu")
            if selected_lunch
            else "No school or menu not available"
        )
        _html(f"""\
            <div class="card">
                <div class="card-header">Lunch</div>
                <div class="menu-item lunch">
                    <div class="card-value">{lunch_text}</div>
                </div>
            </div>
        """)
        for ev in afternoon_events:
            render_event_card(ev)

        # ── Evening (only show if there are evening events) ──
        if evening_events:
            _html(f'<div class="time-section"><span class="ts-icon">{time_sections["evening"][0]}</span><span class="ts-label">{time_sections["evening"][1]}</span></div>')
            for ev in evening_events:
                render_event_card(ev)

    # ── 4. Upcoming Events Timeline ──
    _html('<div class="section-label">Upcoming Events</div>')

    upcoming_events = sorted(
        [e for e in events if e.get("type") in ["event", "deadline"] and e.get("date", "") >= today_str],
        key=lambda x: x.get("date", ""),
    )[:12]

    if upcoming_events:
        current_group = None
        for ev in upcoming_events:
            ev_date = datetime.strptime(ev["date"], "%Y-%m-%d").date() if ev.get("date") else None
            if ev_date:
                group = classify_event_period(ev_date, today)
                if group and group != current_group:
                    current_group = group
                    _html(f'<div class="timeline-group">{group}</div>')

            priority = ev.get("priority", "medium")
            date_str = ev_date.strftime("%a, %b %d") if ev_date else "TBD"
            days_away = (ev_date - today).days if ev_date else 0

            icon = event_icon(ev.get("name", ""))
            nudge = event_nudge(ev, days_away)
            badge_info = event_badge(days_away, priority)
            time_info = event_start_time(ev)
            url = event_fallback_url(ev)
            cal_url = google_calendar_url(ev)

            badge_html = (
                f'<span class="ev-badge {badge_info[1]}">{badge_info[0]}</span>'
                if badge_info else ""
            )
            time_html = f'<span class="ev-time">{time_info[0]}</span>' if time_info and time_info[0] else ""
            nudge_html = f'<div class="ev-nudge">{nudge}</div>' if nudge else ""
            cal_html = f'<a href="{cal_url}" target="_blank" class="ev-cal">+ Add to Calendar</a>' if cal_url else ""

            if priority == "high":
                link_html = (
                    f'<a href="{url}" target="_blank" class="ev-cta">Register &rarr;</a>' if url else ""
                )
                actions_html = f'<div class="ev-actions">{link_html}{cal_html}</div>' if (link_html or cal_html) else ""
                _html(f"""\
                    <div class="ev-card high">
                        <div class="ev-top-row">
                            <div class="ev-date">{time_html}{date_str}</div>
                            {badge_html}
                        </div>
                        <div class="ev-icon-name">
                            <span class="ev-icon">{icon}</span>
                            <span class="ev-name">{ev.get('name', 'Untitled')}</span>
                        </div>
                        {nudge_html}
                        {actions_html}
                    </div>
                """)
            elif priority == "low":
                _html(f"""\
                    <div class="ev-card low">
                        <span class="ev-icon" style="font-size:1.1rem">{icon}</span>
                        <div>
                            <div class="ev-name">{ev.get('name', 'Untitled')}</div>
                            <div class="ev-date">{time_html}{date_str}</div>
                        </div>
                        {badge_html}
                    </div>
                """)
            else:
                link_html = (
                    f'<a href="{url}" target="_blank" class="ev-link">Details &rarr;</a>' if url else ""
                )
                actions_html = f'<div class="ev-actions">{link_html}{cal_html}</div>' if (link_html or cal_html) else ""
                _html(f"""\
                    <div class="ev-card">
                        <div class="ev-top-row">
                            <div class="ev-date">{time_html}{date_str}</div>
                            {badge_html}
                        </div>
                        <div class="ev-icon-name">
                            <span class="ev-icon">{icon}</span>
                            <span class="ev-name">{ev.get('name', 'Untitled')}</span>
                        </div>
                        {nudge_html}
                        {actions_html}
                    </div>
                """)
    else:
        st.info("No upcoming events found.")

    # ── 5. Ask Assistant (collapsed) ──
    _html('<div class="section-label">Ask Assistant</div>')

    with st.expander("Ask a question about school events", expanded=False):
        question = st.text_input(
            "Ask a question",
            placeholder="e.g., When is the Mother/Son Dance? How do I register for the TK tour?",
            label_visibility="collapsed",
        )
        if question:
            with st.spinner("Thinking..."):
                try:
                    answer = ask_assistant(question, events, emails)
                    _html(f'<div class="chat-response">{answer}</div>')
                except Exception as e:
                    st.error(f"Error: {e}")

    # ── 6. Footer ──
    _html(f"""\
        <div class="app-footer">
            Last updated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')} &middot; {len(events)} items
        </div>
    """)


if __name__ == "__main__":
    main()
