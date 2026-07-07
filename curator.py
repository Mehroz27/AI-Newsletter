"""
curator.py — Curator Agent for AI Weekly Newsletter

Responsibilities:
1. Fetch all raw data (RSS articles, GitHub repos, YouTube videos)
2. Filter out already-seen articles via memory
3. Use GPT-4o-mini to score, rank, and assign each item to a newsletter section
4. Return a structured JSON ready for the Formatter agent

Model: gpt-4o-mini (cheap — just ranking and filtering)
"""

import json
import os
import asyncio
from datetime import datetime, timezone

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import OpenAI
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
console = Console()

SYSTEM_PROMPT = """You are a strict AI news curator for a weekly newsletter read by ML engineers, AI practitioners, and curious professionals.

Your job is to analyze raw articles, GitHub repos, and YouTube videos, then:
1. Score each item 1-10 for genuine novelty and importance to AI practitioners
2. Remove duplicates (same story from different sources — keep the best one)
3. Filter out anything not directly about AI technology (no general tech, no opinion pieces unless highly significant)
4. Assign each item to the correct section
5. Select the single most important story as the Top Story

Sections:
- top_story: The single biggest AI development this week (1 item only)
- model_releases: New models, fine-tuned variants, major API changes, or benchmark results — must be about a specific model
- research: NEW papers about novel AI techniques, architectures, or training methods. STRICT rules:
  * Must be about AI/ML specifically — not general data science, statistics, or sports analytics
  * Must present new findings, not just explain existing concepts
  * Strongly prefer papers from ArXiv cs.AI, cs.LG, cs.CL or major lab blogs (OpenAI, DeepMind, Anthropic, Meta AI)
  * Score 8+ only for papers that could change how practitioners work
- github_repos: AI-specific trending repos only. Minimum 200 stars gained this week — skip low-traction repos.
  Must be AI/ML related (LLMs, agents, diffusion, training tools, inference, RAG, etc.)
  Add a "best_for" field: one of "builders" / "researchers" / "learners" / "production"
- tools: New AI product launches or MAJOR updates — something practitioners can go use right now.
  Must be a specific product, not an article about tools. Prefer items from Ben's Bites, TLDR AI, The Rundown.
  Add a "pricing" field: one of "Free" / "Freemium" / "Paid" / "Open Source" / "Unknown"
  Add an "audience" field: one of "developers" / "non-technical" / "enterprise" / "researchers"
- videos: STRICT AI-only selection — only include videos that are directly about AI models, tools, agents, automation, LLMs, AI news, or AI business/workflows.
  EXCLUDE anything about physics, math, personal finance, general tech unrelated to AI, fitness, lifestyle, or non-AI topics — even if from a trusted channel.
  If a channel has nothing AI-related that week, skip it silently — do NOT force-include a video to fill the section.
  For each video, write a 1-2 sentence "summary" field describing what the video covers and why it's relevant to AI practitioners.

Return ONLY a valid JSON object in this exact format:
{
  "top_story": {"title": "", "url": "", "source": "", "summary": "", "why_important": ""},
  "model_releases": [{"title": "", "url": "", "source": "", "summary": ""}],
  "research": [{"title": "", "url": "", "source": "", "summary": "", "difficulty": "accessible|technical|deep_research"}],
  "github_repos": [{"name": "", "url": "", "description": "", "stars_this_week": "", "language": "", "best_for": "builders|researchers|learners|production"}],
  "tools": [{"title": "", "url": "", "source": "", "summary": "", "pricing": "", "audience": ""}],
  "videos": [{"title": "", "url": "", "channel": "", "summary": ""}]
}

Limits: max 5 items per section, max 3 research papers, max 4 github repos, max 5 videos.
Be ruthless — only include genuinely noteworthy items. Quality over quantity.
"""


async def run_curator() -> dict:
    """
    Main curator pipeline:
    1. Connect to MCP server
    2. Fetch all data via MCP tools
    3. Filter via memory
    4. Send to GPT-4o-mini for curation
    5. Return structured curated JSON
    """

    server_params = StdioServerParameters(
        command="python",
        args=["mcp_server.py"],
        cwd=os.path.dirname(os.path.abspath(__file__)),
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            console.print(Panel("Curator Agent Starting", style="cyan"))

            # ── Step 1: Fetch RSS articles ──
            console.print("[cyan]Fetching RSS feeds...[/cyan]")
            result = await session.call_tool("fetch_rss_feeds", {"since_days": 7})
            raw_articles_json = result.content[0].text
            raw_articles = json.loads(raw_articles_json)
            console.print(f"[green]Fetched {len(raw_articles)} articles[/green]")

            # ── Step 2: Filter via memory ──
            console.print("[cyan]Checking memory for duplicates...[/cyan]")
            result = await session.call_tool("check_memory", {"articles_json": raw_articles_json})
            new_articles = json.loads(result.content[0].text)
            console.print(f"[green]{len(new_articles)} new articles after memory filter[/green]")

            # ── Step 3: Fetch GitHub repos ──
            console.print("[cyan]Fetching GitHub trending repos...[/cyan]")
            result = await session.call_tool("fetch_github_trending_repos", {"max_results": 10})
            github_repos = json.loads(result.content[0].text)
            console.print(f"[green]Found {len(github_repos)} AI repos[/green]")

            # ── Step 4: Fetch YouTube videos ──
            console.print("[cyan]Fetching YouTube videos...[/cyan]")
            result = await session.call_tool("fetch_youtube_channel_videos", {"since_days": 7})
            videos = json.loads(result.content[0].text)
            console.print(f"[green]Found {len(videos)} videos[/green]")

            # ── Step 5: Send everything to GPT-4o-mini for curation ──
            console.print("[cyan]Curating and ranking with GPT-4o-mini...[/cyan]")

            # Build the prompt with all raw data
            curation_input = {
                "articles": new_articles[:80],  # cap to avoid token limits
                "github_repos": github_repos,
                "videos": videos,
                "week": _current_week(),
            }

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"Here is the raw data for week {curation_input['week']}. "
                            f"Curate and rank these into the newsletter sections.\n\n"
                            f"{json.dumps(curation_input, ensure_ascii=False, indent=2)}"
                        ),
                    },
                ],
                temperature=0.3,  # low temp = consistent, factual output
                response_format={"type": "json_object"},
            )

            curated_json = response.choices[0].message.content
            curated = json.loads(curated_json)

            # Summary
            console.print(Panel(
                f"Top Story: {curated.get('top_story', {}).get('title', 'N/A')[:70]}\n"
                f"Model Releases: {len(curated.get('model_releases', []))}\n"
                f"Research: {len(curated.get('research', []))}\n"
                f"GitHub Repos: {len(curated.get('github_repos', []))}\n"
                f"Tools: {len(curated.get('tools', []))}\n"
                f"Videos: {len(curated.get('videos', []))}",
                title="Curation Complete",
                style="green"
            ))

            return curated


def _current_week() -> str:
    """Return current ISO week string e.g. '2026-W11'"""
    now = datetime.now(timezone.utc)
    year, week, _ = now.isocalendar()
    return f"{year}-W{week:02d}"


if __name__ == "__main__":
    result = asyncio.run(run_curator())
    print("\n=== Curated Output ===")
    print(json.dumps(result, indent=2, ensure_ascii=False))
