"""
feeds.py — RSS fetching for AI Weekly Newsletter

Loads all sources from config/sources.json, fetches each feed,
filters by date, deduplicates, and returns a clean list of articles.
"""

import json
import feedparser
from datetime import datetime, timezone, timedelta
from pathlib import Path
from bs4 import BeautifulSoup

# Path to sources config
SOURCES_PATH = Path(__file__).parent.parent / "config" / "source.json"

# HN keywords to filter for AI-relevant posts
HN_AI_KEYWORDS = [
    "llm", "gpt", "ai ","gen ai","automation","automate" "machine learning", "deep learning", "neural",
    "openai", "anthropic", "gemini", "claude", "mistral", "transformer",
    "diffusion", "agent", "model", "chatgpt", "copilot","agents", "embedding"
]


def load_sources() -> list[dict]:
    """Load RSS sources from config file."""
    with open(SOURCES_PATH, "r") as f:
        sources = json.load(f)
    return [s for s in sources if s.get("enabled", True)]


def clean_html(text: str) -> str:
    """Strip HTML tags from a string."""
    if not text:
        return ""
    return BeautifulSoup(text, "lxml").get_text(separator=" ").strip()


def parse_date(entry) -> datetime:
    """Parse a feedparser entry's published date to a timezone-aware datetime."""
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
    if hasattr(entry, "updated_parsed") and entry.updated_parsed:
        return datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
    # Default to now if no date found
    return datetime.now(timezone.utc)


def is_ai_relevant(title: str, summary: str) -> bool:
    """Check if a Hacker News post is AI-relevant."""
    text = (title + " " + summary).lower()
    return any(keyword in text for keyword in HN_AI_KEYWORDS)


def fetch_feed(source: dict, since: datetime, max_items: int) -> list[dict]:
    """Fetch and parse a single RSS feed."""
    articles = []
    try:
        feed = feedparser.parse(source["url"])

        for entry in feed.entries[:max_items]:
            title = entry.get("title", "").strip()
            url = entry.get("link", "").strip()
            summary = clean_html(entry.get("summary", entry.get("description", "")))
            published = parse_date(entry)

            # Skip if older than cutoff
            if published < since:
                continue

            # Skip empty entries
            if not title or not url:
                continue

            # For Hacker News, only keep AI-relevant posts
            if source["name"] == "Hacker News" and not is_ai_relevant(title, summary):
                continue

            articles.append({
                "title": title,
                "url": url,
                "summary": summary[:500],  # Cap summary length
                "source": source["name"],
                "category": source["category"],
                "published_at": published.isoformat(),
            })

    except Exception as e:
        print(f"[feeds] Failed to fetch {source['name']}: {e}")

    return articles


def deduplicate(articles: list[dict]) -> list[dict]:
    """Remove duplicate articles by URL and similar titles."""
    seen_urls = set()
    seen_titles = set()
    unique = []

    for article in articles:
        url = article["url"]
        title_key = article["title"][:60].lower().strip()

        if url in seen_urls or title_key in seen_titles:
            continue

        seen_urls.add(url)
        seen_titles.add(title_key)
        unique.append(article)

    return unique


def fetch_all_feeds(
    since_days: int = 7,
    max_per_feed: int = 20,
    sources: list[dict] | None = None
) -> list[dict]:
    """
    Fetch articles from all enabled RSS sources.

    Args:
        since_days: Only include articles published within this many days
        max_per_feed: Max articles to pull from each feed
        sources: Override source list (uses config/source.json by default)

    Returns:
        List of article dicts: {title, url, summary, source, category, published_at}
    """
    if sources is None:
        sources = load_sources()

    since = datetime.now(timezone.utc) - timedelta(days=since_days)
    all_articles = []

    for source in sources:
        articles = fetch_feed(source, since, max_per_feed)
        all_articles.extend(articles)
        print(f"[feeds] {source['name']}: {len(articles)} articles")

    all_articles = deduplicate(all_articles)
    print(f"[feeds] Total after dedup: {len(all_articles)} articles")

    return all_articles


if __name__ == "__main__":
    # Quick test — run: python -m newsletter.feeds
    articles = fetch_all_feeds(since_days=7)
    print(f"\nFetched {len(articles)} articles total\n")
    for a in articles[:5]:
        print(f"  [{a['category']}] {a['source']}: {a['title'][:80]}")
