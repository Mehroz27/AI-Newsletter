# AI Weekly Newsletter

An autonomous multi-agent pipeline that researches, curates, writes, and emails a weekly AI news digest — no manual editing required.

Every run pulls fresh signal from RSS feeds, GitHub Trending, and curated YouTube channels, then hands it through three specialized agents (Curator → Formatter → Reviewer) that score, write, and QA the final issue before it's sent as a dark-themed HTML email.

## How it works

```
                ┌──────────────────────┐
                │      mcp_server.py    │
                │  (MCP tool server)    │
                │                       │
                │  RSS · GitHub · YouTube│
                │  memory · email · draft│
                └───────────┬───────────┘
                            │ MCP tools
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
 ┌─────────────┐    ┌───────────────┐    ┌──────────────┐
 │  1. Curator │───▶│ 2. Formatter  │───▶│ 3. Reviewer  │
 │ gpt-4o-mini │    │   gpt-4o      │    │  gpt-4o-mini │
 │ fetch, dedup│    │ write newsletter    │ QA + auto-fix│
 │ score, rank │    │  in house style│    │ broken links │
 └─────────────┘    └───────────────┘    └──────┬───────┘
                                                  ▼
                                    save draft → update memory → send email
```

`agent.py` is the orchestrator that runs this pipeline end-to-end.

## Features

- **Multi-source aggregation** — 20+ RSS feeds (OpenAI, Anthropic, Hugging Face, ArXiv, TechCrunch, Simon Willison, etc.), GitHub Trending scraping, and curated AI YouTube channels
- **LLM-driven curation** — scores every item for novelty/importance, removes duplicates, and enforces strict per-section relevance rules
- **Memory** — tracks previously featured stories so the newsletter never repeats itself week over week
- **Automated QA** — a dedicated reviewer agent checks required sections and broken markdown links, then auto-fixes issues before send
- **Premium HTML email** — a hand-built dark editorial template (custom fonts, section theming, responsive tables) rendered from the final markdown
- **MCP-based architecture** — all data access (feeds, scraping, memory, email) is exposed as tools on a single [Model Context Protocol](https://modelcontextprotocol.io/) server, shared by all three agents
- **Two run modes** — interactive (confirms before sending) or `--auto` (unattended, for scheduling)

## Project structure

```
agent.py                 orchestrator — runs the full pipeline
mcp_server.py             MCP server exposing all tools (feeds, scraping, memory, email, drafts)
curator.py                Agent 1 — fetch, filter, score, and rank (gpt-4o-mini)
formatter.py              Agent 2 — writes the newsletter in the house style (gpt-4o)
reviewer.py                Agent 3 — QA pass + auto-fix (gpt-4o-mini)

newsletter/
├── feeds.py               RSS fetching, cleaning, dedup
├── scraper.py              GitHub Trending + YouTube RSS + article text extraction
├── memory.py               seen-article tracking, edition logging, cleanup
└── email_sender.py         markdown → dark HTML email renderer + SMTP send

config/
├── source.json             RSS source list (url, category, enabled flag)
└── youtube_channels.json   curated YouTube channel list

memory/                    persisted state (seen articles, edition history)
drafts/                    generated newsletter markdown + HTML preview per edition
```

## Setup

**Requirements:** Python 3.10+

```bash
pip install mcp openai python-dotenv rich feedparser beautifulsoup4 httpx
```

Create a `.env` file in the project root:

```bash
OPENAI_API_KEY=sk-...

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@example.com
SMTP_PASS=your-app-password
EMAIL_FROM=you@example.com
EMAIL_TO=recipient@example.com
```

## Usage

```bash
# Interactive — asks for confirmation before sending the email
python agent.py

# Fully automated — for cron / scheduled runs
python agent.py --auto
```

Each run produces a dated markdown draft and HTML preview in [drafts/](drafts/), updates [memory/](memory/) so future editions skip already-featured stories, and (if configured) sends the finished newsletter by email.

### Customizing sources

- Add or disable RSS feeds in [config/source.json](config/source.json) — each entry supports `url`, `name`, `category`, `enabled`, and an optional `note`/`filter`.
- Add YouTube channels in [config/youtube_channels.json](config/youtube_channels.json) with a `channel_id`, `name`, `focus`, and `frequency`.

## Tech stack

Python · OpenAI (gpt-4o / gpt-4o-mini) · Model Context Protocol (MCP) · feedparser · BeautifulSoup · httpx · Rich
