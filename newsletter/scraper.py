"""
scraper.py — Web scraping for AI Weekly Newsletter

Handles sources that don't have RSS feeds:
- GitHub Trending (AI repos only)
- YouTube channel videos (via YouTube's XML feed)
- Product Hunt AI launches
- Full article text extraction
"""

import json
import httpx
from datetime import datetime, timezone, timedelta
from pathlib import Path
from bs4 import BeautifulSoup

# Path to YouTube channels config
YOUTUBE_CHANNELS_PATH = Path(__file__).parent.parent / "config" / "youtube_channels.json"

# AI keywords to filter GitHub repos
AI_REPO_KEYWORDS = [
    "llm", "gpt", "neural","gen ai", "automation", "automate","voice agents", "machine learning", "deep learning", "ai",
    "ml", "diffusion", "transformer", "language model", "agent", "chatbot",
    "embedding", "fine-tun", "inference", "stable diffusion", "mistral",
    "anthropic", "openai", "gemini", "claude", "copilot", "rag", "vector"
]

# AI keywords to filter YouTube video titles/descriptions
# A video must match at least one to be included — no matter the channel
AI_VIDEO_KEYWORDS = [
    "ai", "artificial intelligence", "llm", "large language model",
    "gpt", "chatgpt", "claude", "gemini", "copilot", "mistral", "llama",
    "openai", "anthropic", "google ai", "meta ai", "deepmind",
    "agent", "ai agent", "autonomous agent", "multi-agent",
    "automation", "automate", "n8n", "make.com", "zapier ai",
    "model", "language model", "foundation model", "fine-tun",
    "machine learning", "deep learning", "neural network", "neural net",
    "transformer", "diffusion", "stable diffusion", "midjourney", "dall-e",
    "rag", "retrieval", "embedding", "vector database",
    "chatbot", "voice ai", "text to", "image generation", "ai tools",
    "ai workflow", "ai business", "ai productivity", "ai news",
    "vibe coding", "cursor", "windsurf", "devin", "github copilot",
    "ollama", "huggingface", "langchain", "crew ai", "autogen",
]

# Shared headers to avoid being blocked
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


# ─────────────────────────────────────────────
# GITHUB TRENDING
# ─────────────────────────────────────────────

def is_ai_repo(name: str, description: str) -> bool:
    """Check if a repo is AI-related based on name and description."""
    text = (name + " " + description).lower()
    return any(keyword in text for keyword in AI_REPO_KEYWORDS)


def fetch_github_trending(max_results: int = 10) -> list[dict]:
    """
    Scrape GitHub Trending for AI-related repos (weekly).

    Returns list of dicts: {name, url, description, stars, stars_this_week, language}
    """
    repos = []
    url = "https://github.com/trending?since=weekly"

    try:
        response = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
        soup = BeautifulSoup(response.text, "lxml")

        # Each trending repo is in an <article> tag
        for article in soup.select("article.Box-row"):
            # Repo name (owner/repo)
            name_tag = article.select_one("h2 a")
            if not name_tag:
                continue
            repo_path = name_tag.get("href", "").strip("/")
            repo_name = repo_path.replace("/", " / ")
            repo_url = f"https://github.com/{repo_path}"

            # Description
            desc_tag = article.select_one("p")
            description = desc_tag.get_text(strip=True) if desc_tag else ""

            # Stars this week
            stars_tag = article.select_one("span.d-inline-block.float-sm-right")
            stars_this_week = stars_tag.get_text(strip=True) if stars_tag else "N/A"

            # Total stars
            stars_tags = article.select("a.Link--muted")
            total_stars = stars_tags[0].get_text(strip=True) if stars_tags else "N/A"

            # Language
            lang_tag = article.select_one("span[itemprop='programmingLanguage']")
            language = lang_tag.get_text(strip=True) if lang_tag else "Unknown"

            # Only keep AI-related repos
            if not is_ai_repo(repo_name, description):
                continue

            repos.append({
                "name": repo_name,
                "url": repo_url,
                "description": description,
                "stars": total_stars,
                "stars_this_week": stars_this_week,
                "language": language,
            })

            if len(repos) >= max_results:
                break

        print(f"[scraper] GitHub Trending: {len(repos)} AI repos found")

    except Exception as e:
        print(f"[scraper] GitHub Trending failed: {e}")

    return repos


# ─────────────────────────────────────────────
# YOUTUBE VIDEOS
# ─────────────────────────────────────────────

def _is_ai_video(title: str, description: str = "") -> bool:
    """
    Return True only if the video title or description contains an AI-related keyword.
    This prevents non-AI videos (physics, finance, fitness, etc.) from slipping through
    even when posted by channels that sometimes cover non-AI topics.
    """
    text = (title + " " + description).lower()
    return any(kw in text for kw in AI_VIDEO_KEYWORDS)


def fetch_youtube_videos(since_days: int = 7, max_per_channel: int = 3) -> list[dict]:
    """
    Fetch recent AI-related videos from curated YouTube channels via their RSS feeds.

    Strict filtering: only videos whose title or description contains an AI keyword
    are included. Videos on non-AI topics (physics, finance, lifestyle, etc.) are
    silently skipped even if posted by channels in the config.

    Returns list of dicts: {title, url, channel, description, published_at}
    """
    videos = []
    since = datetime.now(timezone.utc) - timedelta(days=since_days)

    try:
        with open(YOUTUBE_CHANNELS_PATH, "r") as f:
            channels = json.load(f)
    except Exception as e:
        print(f"[scraper] Could not load YouTube channels config: {e}")
        return []

    for channel in channels:
        channel_id   = channel["channel_id"]
        channel_name = channel["name"]
        feed_url     = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

        try:
            response = httpx.get(feed_url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(response.text, "xml")

            count = 0
            checked = 0
            for entry in soup.find_all("entry"):
                title_tag   = entry.find("title")
                link_tag    = entry.find("link")
                pub_tag     = entry.find("published")
                # YouTube RSS includes <media:description> for video description
                desc_tag    = entry.find("media:description") or entry.find("description")

                if not title_tag or not link_tag:
                    continue

                title_text = title_tag.get_text(strip=True)
                video_url  = link_tag.get("href", "")
                desc_text  = desc_tag.get_text(strip=True)[:300] if desc_tag else ""
                pub_text   = pub_tag.get_text(strip=True) if pub_tag else ""

                checked += 1

                # Parse publish date
                try:
                    pub_date = datetime.fromisoformat(pub_text.replace("Z", "+00:00"))
                except Exception:
                    pub_date = datetime.now(timezone.utc)

                # Skip if older than since_days
                if pub_date < since:
                    continue

                # ── AI keyword filter — the core gate ──
                if not _is_ai_video(title_text, desc_text):
                    continue

                videos.append({
                    "title":        title_text,
                    "url":          video_url,
                    "channel":      channel_name,
                    "description":  desc_text,
                    "published_at": pub_date.isoformat(),
                })

                count += 1
                if count >= max_per_channel:
                    break

            print(f"[scraper] YouTube {channel_name}: {count} AI videos (checked {checked})")

        except Exception as e:
            print(f"[scraper] YouTube {channel_name} failed: {e}")

    return videos


# ─────────────────────────────────────────────
# AI TOOLS
# Product Hunt uses JavaScript rendering so it can't be scraped directly.
# AI tools now come from "There's An AI For That" RSS feed in source.json
# which feeds.py handles automatically alongside all other RSS sources.
# ─────────────────────────────────────────────


# ─────────────────────────────────────────────
# ARTICLE FULL TEXT
# ─────────────────────────────────────────────

def fetch_article_text(url: str, max_chars: int = 3000) -> str:
    """
    Fetch and extract the readable text from an article URL.
    Used by the Formatter to get full content for top stories.

    Returns plain text string, empty string on failure.
    """
    try:
        response = httpx.get(url, headers=HEADERS, timeout=10, follow_redirects=True)
        soup = BeautifulSoup(response.text, "lxml")

        # Remove noise
        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "ads"]):
            tag.decompose()

        # Try to find the main content area
        content = (
            soup.find("article") or
            soup.find("main") or
            soup.find("div", {"class": lambda c: c and "content" in c.lower()}) or
            soup.find("body")
        )

        if not content:
            return ""

        text = content.get_text(separator=" ", strip=True)

        # Truncate at sentence boundary near max_chars
        if len(text) > max_chars:
            truncated = text[:max_chars]
            last_period = truncated.rfind(".")
            if last_period > max_chars * 0.8:
                text = truncated[:last_period + 1]
            else:
                text = truncated

        return text

    except Exception as e:
        print(f"[scraper] Article fetch failed for {url}: {e}")
        return ""


# ─────────────────────────────────────────────
# QUICK TEST
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("\n=== GitHub Trending ===")
    repos = fetch_github_trending()
    for r in repos[:3]:
        print(f"  {r['name']} — {r['description'][:60]} | ⭐ {r['stars_this_week']}")

    print("\n=== YouTube Videos ===")
    videos = fetch_youtube_videos()
    for v in videos[:3]:
        print(f"  [{v['channel']}] {v['title'][:70]}")

    print("\n=== AI Tools (from There's An AI For That - via feeds.py) ===")
