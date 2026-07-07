"""
agent.py — Orchestrator for AI Weekly Newsletter

The main entry point. Runs the full pipeline:
1. Curator  → fetch, filter, rank
2. Formatter → write beautiful newsletter
3. Reviewer  → QA check, auto-fix
4. Post-process → fix any remaining broken links
5. Save draft → via MCP tool
6. Update memory → mark stories as seen
7. Send email → via MCP tool (if configured)

Usage:
  python agent.py           # interactive mode — asks before sending email
  python agent.py --auto    # fully automated — for scheduling
"""

import asyncio
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

from curator import run_curator
from formatter import run_formatter
from reviewer import run_reviewer

load_dotenv()
console = Console()


# ─────────────────────────────────────────────
# POST-PROCESSING
# ─────────────────────────────────────────────

def fix_broken_links(newsletter: str) -> str:
    """
    Fix bare URLs in markdown tables that GPT sometimes generates.
    Converts (https://url) → [view](https://url)
    """
    # Match (url) not preceded by ] — broken markdown link
    fixed = re.sub(
        r'(?<!\])\((https?://[^)]+)\)',
        lambda m: f'[view]({m.group(1)})',
        newsletter
    )
    count = newsletter.count('(http') - fixed.count('(http')
    if count > 0:
        console.print(f"[green]Fixed {count} broken link(s)[/green]")
    return fixed


def current_edition() -> str:
    now = datetime.now(timezone.utc)
    year, week, _ = now.isocalendar()
    return f"{year}-W{week:02d}"


# ─────────────────────────────────────────────
# MAIN PIPELINE
# ─────────────────────────────────────────────

async def run_pipeline(auto: bool = False):
    """
    Full newsletter pipeline.

    Args:
        auto: If True, skips confirmation prompts (for scheduled runs)
    """
    start_time = datetime.now(timezone.utc)
    edition = current_edition()

    console.print(Rule(f"[bold magenta]AI Weekly Newsletter — {edition}[/bold magenta]"))
    console.print()

    # ── Step 1: Curator ──
    console.print(Rule("[cyan]Step 1 / 4 — Curation[/cyan]"))
    curated = await run_curator()
    console.print()

    # ── Step 2: Formatter ──
    console.print(Rule("[blue]Step 2 / 4 — Formatting[/blue]"))
    newsletter = await run_formatter(curated)
    console.print()

    # ── Step 3: Reviewer ──
    console.print(Rule("[yellow]Step 3 / 4 — Review[/yellow]"))
    review = await run_reviewer(newsletter)
    final_newsletter = review.get("fixed_newsletter", newsletter)
    console.print()

    # ── Step 4: Post-process ──
    console.print(Rule("[green]Step 4 / 4 — Saving & Sending[/green]"))
    final_newsletter = fix_broken_links(final_newsletter)

    # ── Save draft + update memory via MCP ──
    server_params = StdioServerParameters(
        command="python",
        args=["mcp_server.py"],
        cwd=os.path.dirname(os.path.abspath(__file__)),
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # Save draft
            console.print("[green]Saving newsletter draft...[/green]")
            result = await session.call_tool("save_newsletter_draft", {
                "body": final_newsletter,
                "edition": edition,
            })
            draft_path = result.content[0].text
            console.print(f"[green]Draft saved: {draft_path}[/green]")

            # Update memory
            console.print("[green]Updating memory...[/green]")
            all_articles = _extract_articles(curated)
            await session.call_tool("update_memory", {
                "articles_json": json.dumps(all_articles),
                "edition": edition,
            })

            # Send email
            should_send = _should_send_email(auto)

            if should_send:
                console.print("[green]Sending email...[/green]")
                result = await session.call_tool("send_newsletter_email", {
                    "draft_filepath": draft_path,
                })
                email_status = result.content[0].text
                console.print(f"[green]{email_status}[/green]")
            else:
                console.print("[yellow]Email skipped[/yellow]")

    # ── Summary ──
    elapsed = (datetime.now(timezone.utc) - start_time).seconds
    console.print()
    console.print(Panel(
        f"Edition:     {edition}\n"
        f"Draft saved: {draft_path}\n"
        f"Top story:   {curated.get('top_story', {}).get('title', 'N/A')[:60]}\n"
        f"Sections:    {_count_sections(curated)}\n"
        f"Review:      {review.get('status', 'unknown')}\n"
        f"Time taken:  {elapsed}s",
        title="Pipeline Complete",
        style="bold green"
    ))

    return draft_path


def _extract_articles(curated: dict) -> list[dict]:
    """Extract all featured articles from curated JSON for memory update."""
    articles = []

    top = curated.get("top_story")
    if top:
        articles.append({"url": top.get("url", ""), "title": top.get("title", ""), "source": top.get("source", "")})

    for section in ["model_releases", "research", "tools"]:
        for item in curated.get(section, []):
            articles.append({"url": item.get("url", ""), "title": item.get("title", ""), "source": item.get("source", "")})

    return [a for a in articles if a.get("url")]


def _count_sections(curated: dict) -> str:
    return (
        f"Top Story + "
        f"{len(curated.get('model_releases', []))} models + "
        f"{len(curated.get('research', []))} papers + "
        f"{len(curated.get('github_repos', []))} repos + "
        f"{len(curated.get('tools', []))} tools + "
        f"{len(curated.get('videos', []))} videos"
    )


def _should_send_email(auto: bool) -> bool:
    """Decide whether to send email based on mode and .env config."""
    smtp_configured = bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_USER") and os.getenv("SMTP_PASS"))

    if not smtp_configured:
        return False

    if auto:
        return True

    # Interactive mode — ask user
    answer = input("\nSend newsletter email? (y/n): ").strip().lower()
    return answer == "y"


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Weekly Newsletter Orchestrator")
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Run fully automated (no prompts) — use for scheduling"
    )
    args = parser.parse_args()

    asyncio.run(run_pipeline(auto=args.auto))
