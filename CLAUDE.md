# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

School Strategist ingests school emails and lunch menus, extracts events using an LLM, and presents them in a dashboard and daily digest.

## Architecture

**Data Ingestion:**
- `ingest.py` → Fetches ParentSquare emails via Gmail IMAP → `raw_emails.json`
- `scrape_web.py` → Scrapes school lunch menu PDF → `data/menu_data_MMM_YYYY.json`

**Processing:**
- `extract.py` → Combines emails + menu, sends to Claude API → `events.json`

**Presentation (planned):**
- `app.py` → Streamlit dashboard
- `digest.py` → HTML email digest

**Data Flow:**
```
Gmail IMAP ──► raw_emails.json ──┐
                                 ├──► extract.py ──► events.json ──► Dashboard
School Website ──► data/menu_*.json ─┘
```

## Configuration

Environment variables in `.env`:
- `GMAIL_EMAIL`: Gmail address
- `GMAIL_PASSWORD`: Gmail App Password (16-character)
- `STUDENT_NUTRITION_URL`: School lunch menu page URL
- `ANTHROPIC_API_KEY`: For Claude API (extract.py)

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Fetch emails from ParentSquare
python ingest.py

# Scrape lunch menu (caches by month)
python scrape_web.py

# Extract events using Claude
python extract.py
```

## Key Files

- `raw_emails.json`: Cached email data
- `data/menu_data_MMM_YYYY.json`: Monthly menu cache (auto-generated filename)
- `events.json`: Extracted structured events
- `.env`: Credentials (not in git)
