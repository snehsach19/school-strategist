# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Los Alamitos Smart Calendar ingests school emails, lunch menus, PTA announcements, and district calendar data, extracts events using an LLM, and presents them in a mobile-friendly React dashboard.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DATA INGESTION (Python)                       │
├─────────────────────────────────────────────────────────────────────┤
│  ingest.py ─────────► raw_emails.json (ParentSquare via Gmail IMAP) │
│  scrape_web.py ─────► data/menu_*.json (lunch PDFs)                 │
│  scrape_pta.py ─────► data/pta_page.json (PTA website)              │
│  scrape_district.py ► data/district_calendar.json (SJUSD calendar)  │
└──────────────────────────────┬──────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        PROCESSING (Python)                           │
├─────────────────────────────────────────────────────────────────────┤
│  extract.py ───► Combines all sources + Claude API ──► events.json  │
└──────────────────────────────┬──────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        PRESENTATION                                  │
├─────────────────────────────────────────────────────────────────────┤
│  school-ui/ ────► React + Tailwind (reads events.json)              │
│  app.py ────────► Streamlit dashboard (legacy, deployed)            │
└─────────────────────────────────────────────────────────────────────┘
```

## Commands

### Python Backend (data pipeline)

```bash
pip install -r requirements.txt

python ingest.py           # Fetch emails from ParentSquare
python scrape_web.py       # Scrape lunch menus (caches by month)
python scrape_pta.py       # Scrape PTA website (24h cache)
python scrape_district.py  # Scrape district calendar (24h cache)
python extract.py          # Extract events via Claude API
```

### React Frontend (school-ui/)

```bash
cd school-ui
npm install
npm run dev      # Start dev server at http://localhost:5173
npm run build    # Production build to dist/
npm run preview  # Preview production build
```

### Streamlit (legacy)

```bash
streamlit run app.py
```

## Configuration

Environment variables in `.env`:
- `GMAIL_EMAIL`: Gmail address for IMAP access
- `GMAIL_PASSWORD`: Gmail App Password (16-character)
- `STUDENT_NUTRITION_URL`: School lunch menu page URL
- `ANTHROPIC_API_KEY`: For Claude API (extract.py)

GitHub Actions secrets (same names) enable automated daily refresh.

## Key Files

| File | Purpose |
|------|---------|
| `events.json` | Extracted events consumed by frontends |
| `raw_emails.json` | Cached ParentSquare email data |
| `data/menu_*.json` | Monthly lunch menu cache |
| `data/pta_page.json` | PTA website cache (24h TTL) |
| `data/district_calendar.json` | District calendar cache (24h TTL) |
| `school-ui/public/events.json` | Symlink to root events.json |

## Automated Refresh

GitHub Actions workflow (`.github/workflows/refresh-data.yml`) runs daily at 6 AM PT:
1. Fetches emails, scrapes menus/PTA/calendar
2. Extracts events via Claude
3. Commits updated `events.json` if changed
