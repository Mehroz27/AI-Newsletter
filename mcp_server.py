"""
mcp_server.py — MCP Server for AI Weekly Newsletter

Exposes all newsletter tools via the Model Context Protocol.
All 3 agents (Curator, Formatter, Reviewer) connect to this server.

Run: python mcp_server.py
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from newsletter.feeds import fetch_all_feeds
from newsletter.scraper import fetch_github_trending, fetch_youtube_videos, fetch_article_text
from newsletter.memory import (
    filter_new_articles,
    mark_as_seen,
    log_edition,
    cleanup_old_entries,
    get_current_edition,
    load_seen,
)
from newsletter.email_sender import send_email

# ─────────────────────────────────────────────
# Setup
# ─────────────────────────────────────────────

mcp = FastMCP("ai-newsletter")

DRAFTS_DIR = Path(__file__).parent / "drafts"
DRAFTS_DIR.mkdir(exist_ok=True)


# ─────────────────────────────────────────────
# TOOL 1 — Fetch RSS Feeds
# ─────────────────────────────────────────────

@mcp.tool()
def fetch_rss_feeds(since_days: int = 7, max_per_feed: int = 20) -> str:
    """
    Fetch the latest AI news articles from all configured RSS sources.
    Returns a JSON string containing a list of articles.
    Each article has: title, url, summary, source, category, published_at.
    Call this first at the start of every newsletter run.
    """
    articles = fetch_all_feeds(since_days=since_days, max_per_feed=max_per_feed)
    return json.dumps(articles, ensure_ascii=False)


# ─────────────────────────────────────────────
# TOOL 2 — Fetch GitHub Trending
# ─────────────────────────────────────────────

@mcp.tool()
def fetch_github_trending_repos(max_results: int = 10) -> str:
    """
    Scrape GitHub Trending for AI-related repositories this week.
    Returns a JSON string with a list of repos.
    Each repo has: name, url, description, stars, stars_this_week, language.
    Use this to populate the 'GitHub Repos of the Week' section.
    """
    repos = fetch_github_trending(max_results=max_results)
    return json.dumps(repos, ensure_ascii=False)


# ─────────────────────────────────────────────
# TOOL 3 — Fetch YouTube Videos
# ─────────────────────────────────────────────

@mcp.tool()
def fetch_youtube_channel_videos(since_days: int = 7, max_per_channel: int = 2) -> str:
    """
    Fetch recent AI tutorial and explainer videos from curated YouTube channels.
    Returns a JSON string with a list of videos.
    Each video has: title, url, channel, published_at.
    Use this to populate the 'Watch This Week' section.
    """
    videos = fetch_youtube_videos(since_days=since_days, max_per_channel=max_per_channel)
    return json.dumps(videos, ensure_ascii=False)


# ─────────────────────────────────────────────
# TOOL 4 — Fetch Article Full Text
# ─────────────────────────────────────────────

@mcp.tool()
def fetch_article_content(url: str, max_chars: int = 3000) -> str:
    """
    Fetch and extract the full readable text from a single article URL.
    Use this to get the full content of the top story and key research papers
    so the Formatter can write deeper, more accurate summaries.
    Returns plain text. Returns empty string if the article can't be fetched.
    """
    return fetch_article_text(url=url, max_chars=max_chars)


# ─────────────────────────────────────────────
# TOOL 5 — Check Memory (filter already-seen articles)
# ─────────────────────────────────────────────

@mcp.tool()
def check_memory(articles_json: str) -> str:
    """
    Filter out articles that have already been featured in a previous newsletter edition.
    Pass in the raw articles JSON from fetch_rss_feeds.
    Returns a filtered JSON string with only new, unseen articles.
    Always call this after fetch_rss_feeds and before curating stories.
    """
    articles = json.loads(articles_json)
    new_articles = filter_new_articles(articles)
    return json.dumps(new_articles, ensure_ascii=False)


# ─────────────────────────────────────────────
# TOOL 6 — Update Memory (save featured articles)
# ─────────────────────────────────────────────

@mcp.tool()
def update_memory(articles_json: str, edition: str | None = None) -> str:
    """
    Save the featured articles to memory so they won't be repeated next week.
    Call this AFTER the newsletter has been saved and approved.
    Pass the articles that were actually featured (not all fetched articles).
    Edition defaults to current ISO week e.g. '2026-W11'.
    """
    articles = json.loads(articles_json)
    if not edition:
        edition = get_current_edition()

    mark_as_seen(articles, edition)
    cleanup_old_entries(days=28)

    return f"Memory updated: {len(articles)} articles saved for edition {edition}"


# ─────────────────────────────────────────────
# TOOL 7 — Save Newsletter Draft
# ─────────────────────────────────────────────

@mcp.tool()
def save_newsletter_draft(
    body: str,
    title: str | None = None,
    edition: str | None = None,
) -> str:
    """
    Save the final formatted newsletter as a markdown file in the drafts/ folder.
    Call this after the Formatter has written the newsletter and Reviewer has approved it.
    Returns the full filepath of the saved draft.
    """
    if not edition:
        edition = get_current_edition()

    if not title:
        title = f"AI Weekly — {edition}"

    filename = f"{edition}-ai-weekly.md"
    filepath = DRAFTS_DIR / filename

    # Add title header if not already present
    if not body.strip().startswith("#"):
        body = f"# {title}\n\n{body}"

    filepath.write_text(body, encoding="utf-8")

    # Log the edition
    log_edition(
        edition=edition,
        top_story_title=title,
        story_count=body.count("##"),
    )

    return str(filepath)


# ─────────────────────────────────────────────
# TOOL 8 — Send Newsletter Email
# ─────────────────────────────────────────────

@mcp.tool()
def send_newsletter_email(
    draft_filepath: str,
    subject: str | None = None,
    recipients: list[str] | None = None,
) -> str:
    """
    Send the saved newsletter draft via email.
    Requires SMTP settings in .env (SMTP_HOST, SMTP_USER, SMTP_PASS, EMAIL_TO).
    If email is not configured, returns a message saying so — does NOT crash.
    Call this as the final step after save_newsletter_draft.
    """
    return send_email(
        draft_filepath=draft_filepath,
        subject=subject,
        recipients=recipients,
    )


# ─────────────────────────────────────────────
# Run the server
# ─────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="stdio")
