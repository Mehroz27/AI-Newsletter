"""
memory.py — Memory system for AI Weekly Newsletter

Tracks which articles have been featured in past editions.
Prevents the same story from appearing in multiple newsletters.
Rolling 28-day window — stories older than 4 weeks are forgotten.
"""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Memory files location
MEMORY_DIR = Path(__file__).parent.parent / "memory"
SEEN_PATH = MEMORY_DIR / "seen.json"
EDITIONS_PATH = MEMORY_DIR / "editions.json"


def _ensure_memory_dir():
    """Create memory/ folder and empty files if they don't exist yet."""
    MEMORY_DIR.mkdir(exist_ok=True)

    if not SEEN_PATH.exists():
        SEEN_PATH.write_text(json.dumps({"entries": []}, indent=2))

    if not EDITIONS_PATH.exists():
        EDITIONS_PATH.write_text(json.dumps({"editions": []}, indent=2))


# ─────────────────────────────────────────────
# READ
# ─────────────────────────────────────────────

def load_seen() -> list[dict]:
    """Load the list of previously seen articles."""
    _ensure_memory_dir()
    data = json.loads(SEEN_PATH.read_text())
    return data.get("entries", [])


def get_seen_urls() -> set[str]:
    """Return a set of all URLs that have already been featured."""
    return {entry["url"] for entry in load_seen()}


def get_seen_titles() -> set[str]:
    """Return a set of lowercased title prefixes (first 60 chars) already seen."""
    return {entry["title"][:60].lower().strip() for entry in load_seen()}


# ─────────────────────────────────────────────
# FILTER
# ─────────────────────────────────────────────

def filter_new_articles(articles: list[dict]) -> list[dict]:
    """
    Remove articles that have already been featured in a past edition.
    Checks both URL and title similarity.

    Args:
        articles: Raw list of article dicts from feeds.py / scraper.py

    Returns:
        Only articles that haven't been seen before
    """
    seen_urls = get_seen_urls()
    seen_titles = get_seen_titles()

    new_articles = []
    skipped = 0

    for article in articles:
        url = article.get("url", "")
        title_key = article.get("title", "")[:60].lower().strip()

        if url in seen_urls or title_key in seen_titles:
            skipped += 1
            continue

        new_articles.append(article)

    print(f"[memory] {len(new_articles)} new articles, {skipped} already seen")
    return new_articles


# ─────────────────────────────────────────────
# WRITE
# ─────────────────────────────────────────────

def mark_as_seen(articles: list[dict], edition: str):
    """
    Save featured articles to memory after a newsletter is published.

    Args:
        articles: The articles that were featured in this edition
        edition: Edition identifier e.g. "2026-W10"
    """
    _ensure_memory_dir()
    data = json.loads(SEEN_PATH.read_text())
    existing = data.get("entries", [])

    today = datetime.now(timezone.utc).date().isoformat()

    for article in articles:
        existing.append({
            "url": article.get("url", ""),
            "title": article.get("title", ""),
            "source": article.get("source", ""),
            "first_seen": today,
            "featured_in": edition,
        })

    data["entries"] = existing
    SEEN_PATH.write_text(json.dumps(data, indent=2))
    print(f"[memory] Saved {len(articles)} articles to memory for edition {edition}")


def log_edition(edition: str, top_story_title: str, story_count: int):
    """
    Log a completed newsletter edition to editions.json.

    Args:
        edition: e.g. "2026-W10"
        top_story_title: Title of the top story
        story_count: Total number of stories in the newsletter
    """
    _ensure_memory_dir()
    data = json.loads(EDITIONS_PATH.read_text())
    editions = data.get("editions", [])

    editions.append({
        "edition": edition,
        "date": datetime.now(timezone.utc).date().isoformat(),
        "top_story": top_story_title,
        "story_count": story_count,
    })

    data["editions"] = editions
    EDITIONS_PATH.write_text(json.dumps(data, indent=2))


# ─────────────────────────────────────────────
# CLEANUP
# ─────────────────────────────────────────────

def cleanup_old_entries(days: int = 28):
    """
    Remove entries older than `days` days from memory.
    Keeps the memory file from growing forever.
    Called automatically after each newsletter run.
    """
    _ensure_memory_dir()
    data = json.loads(SEEN_PATH.read_text())
    entries = data.get("entries", [])

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()

    before = len(entries)
    entries = [e for e in entries if e.get("first_seen", "9999") >= cutoff]
    after = len(entries)

    data["entries"] = entries
    SEEN_PATH.write_text(json.dumps(data, indent=2))

    removed = before - after
    if removed:
        print(f"[memory] Cleaned up {removed} entries older than {days} days")


def get_current_edition() -> str:
    """
    Return the current ISO week edition string e.g. '2026-W10'
    Used to label which edition articles were featured in.
    """
    now = datetime.now(timezone.utc)
    year, week, _ = now.isocalendar()
    return f"{year}-W{week:02d}"


# ─────────────────────────────────────────────
# QUICK TEST
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Memory System Test ===\n")

    # Show current edition
    edition = get_current_edition()
    print(f"Current edition: {edition}")

    # Show how many entries are in memory
    entries = load_seen()
    print(f"Articles in memory: {len(entries)}")

    # Simulate filtering
    fake_articles = [
        {"url": "https://example.com/article-1", "title": "GPT-5 Released Today"},
        {"url": "https://example.com/article-2", "title": "Claude 4 Announcement"},
    ]

    print("\n--- First run (nothing in memory) ---")
    new = filter_new_articles(fake_articles)
    print(f"New articles: {len(new)}")

    print("\n--- Marking as seen ---")
    mark_as_seen(fake_articles, edition)

    print("\n--- Second run (same articles) ---")
    new = filter_new_articles(fake_articles)
    print(f"New articles: {len(new)} (should be 0)")

    print("\n--- Cleanup ---")
    cleanup_old_entries(days=28)

    print("\nMemory test complete.")
