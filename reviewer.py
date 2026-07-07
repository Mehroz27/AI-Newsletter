"""
reviewer.py — Reviewer Agent for AI Weekly Newsletter

Responsibilities:
1. Read the formatted newsletter
2. Check for quality issues (broken links, missing sections, tone, inappropriate titles)
3. Return approved or a list of specific issues to fix
4. If issues found, send back to Formatter with instructions (max 2 cycles)

Model: gpt-4o-mini (cheap — just checking)
"""

import json
import os
import asyncio
import re

from openai import OpenAI
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
console = Console()

SYSTEM_PROMPT = """You are a quality reviewer for AI Weekly, a professional newsletter for ML engineers and AI practitioners.

Your job is to review the newsletter draft and check for these specific issues:

1. BROKEN LINKS — Any URL formatted as (url) instead of [text](url) — this is a markdown error
2. INAPPROPRIATE TITLES — Video or article titles that are clickbait, offensive, or unprofessional for a technical audience
3. MISSING SECTIONS — Any of these must be present: Top Story, Model Releases, Research Highlights, GitHub Repos, New Tools, Watch This Week
4. TONE — Any hype words like "revolutionary", "game-changing", "groundbreaking" used without justification
5. EMPTY SECTIONS — Any section with placeholder text like [Write...] still in it

Return ONLY a valid JSON object:
{
  "status": "approved" or "revise",
  "issues": [
    {"type": "broken_link", "location": "GitHub section, row 1", "detail": "repo name missing from link"},
    {"type": "inappropriate_title", "location": "Watch This Week", "detail": "Title X is unprofessional — suggest replacing or adding context"},
    {"type": "missing_section", "location": "N/A", "detail": "Research Highlights section is missing"},
    {"type": "tone", "location": "Top Story", "detail": "Word 'revolutionary' used without justification"},
    {"type": "empty_section", "location": "Tools section", "detail": "Contains placeholder text"}
  ],
  "approved_with_notes": "Optional string — if approving but want to note minor things"
}

If there are no issues, return {"status": "approved", "issues": []}.
Be strict but fair. Minor stylistic preferences are NOT issues. Only flag real problems.
"""

FIX_PROMPT = """You are the editor of AI Weekly. The reviewer found these issues in the newsletter draft.
Fix ONLY the listed issues — do not change anything else.

ISSUES TO FIX:
{issues}

ORIGINAL NEWSLETTER:
{newsletter}

Return the complete fixed newsletter markdown. Nothing else.
"""


def _check_broken_links(newsletter: str) -> list[dict]:
    """Quick regex pre-check for broken markdown links before sending to GPT."""
    issues = []
    # Find bare URLs in parentheses without preceding [text] — pattern: (https://...) not preceded by ]
    bare_urls = re.findall(r'(?<!\])\(https?://[^\)]+\)', newsletter)
    for url in bare_urls:
        issues.append({
            "type": "broken_link",
            "location": "Unknown",
            "detail": f"Bare URL found without link text: {url[:60]}"
        })
    return issues


def _check_required_sections(newsletter: str) -> list[dict]:
    """Check all required sections are present."""
    required = [
        ("Top Story", "## 🔥 Top Story"),
        ("Model Releases", "## 🤖 Model Releases"),
        ("Research Highlights", "## 📄 Research Highlights"),
        ("GitHub Repos", "## ⭐ GitHub Repos"),
        ("New Tools", "## 🛠 New Tools"),
        ("Watch This Week", "## 🎬 Watch This Week"),
    ]
    issues = []
    for name, heading in required:
        if heading not in newsletter:
            issues.append({
                "type": "missing_section",
                "location": name,
                "detail": f"Section '{name}' is missing from the newsletter"
            })
    return issues


async def run_reviewer(newsletter: str, revision_count: int = 0) -> dict:
    """
    Review the newsletter for quality issues.

    Args:
        newsletter: The formatted markdown newsletter
        revision_count: How many times it has already been revised (max 2)

    Returns:
        dict with status, issues, and optionally the fixed newsletter
    """
    console.print(Panel(
        f"Reviewer Agent Starting (revision {revision_count}/2)",
        style="yellow"
    ))

    # ── Quick pre-checks (no API call needed) ──
    pre_issues = []
    pre_issues.extend(_check_broken_links(newsletter))
    pre_issues.extend(_check_required_sections(newsletter))

    if pre_issues:
        console.print(f"[yellow]Pre-check found {len(pre_issues)} issue(s)[/yellow]")

    # ── Send to GPT-4o-mini for deeper review ──
    console.print("[yellow]Reviewing with GPT-4o-mini...[/yellow]")

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Review this newsletter draft:\n\n{newsletter}"},
        ],
        temperature=0.1,
        response_format={"type": "json_object"},
    )

    review = json.loads(response.choices[0].message.content)

    # Merge pre-check issues with GPT issues
    all_issues = pre_issues + review.get("issues", [])
    review["issues"] = all_issues

    if not all_issues:
        review["status"] = "approved"

    # ── If issues found and we haven't hit max revisions ──
    if review["status"] == "revise" and revision_count < 2:
        console.print(Panel(
            "\n".join([f"• [{i['type']}] {i['location']}: {i['detail']}" for i in all_issues]),
            title=f"Issues Found ({len(all_issues)})",
            style="yellow"
        ))

        console.print("[yellow]Sending back to Formatter for fixes...[/yellow]")

        issues_text = "\n".join([
            f"- [{i['type'].upper()}] in {i['location']}: {i['detail']}"
            for i in all_issues
        ])

        fix_response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": FIX_PROMPT.format(
                        issues=issues_text,
                        newsletter=newsletter
                    )
                }
            ],
            temperature=0.3,
            max_tokens=4000,
        )

        fixed_newsletter = fix_response.choices[0].message.content
        review["fixed_newsletter"] = fixed_newsletter

        console.print("[green]Fixes applied — running final review pass...[/green]")

        # One more review pass on the fixed version
        return await run_reviewer(fixed_newsletter, revision_count + 1)

    elif review["status"] == "revise" and revision_count >= 2:
        console.print("[red]Max revisions reached — approving with notes[/red]")
        review["status"] = "approved"
        review["approved_with_notes"] = f"Max revisions reached. Remaining issues: {len(all_issues)}"

    if review["status"] == "approved":
        console.print(Panel(
            f"Newsletter approved ✓\n"
            + (f"Notes: {review.get('approved_with_notes', 'None')}" if review.get('approved_with_notes') else "No issues found"),
            title="Review Complete",
            style="green"
        ))

    return review


if __name__ == "__main__":
    import sys
    from formatter import run_formatter
    from curator import run_curator

    async def main():
        # Run full pipeline: Curator → Formatter → Reviewer
        console.print(Panel("Running Full Pipeline: Curator → Formatter → Reviewer", style="magenta"))

        curated = await run_curator()
        newsletter = await run_formatter(curated)
        review = await run_reviewer(newsletter)

        final_newsletter = review.get("fixed_newsletter", newsletter)

        console.print("\n" + "="*60)
        console.print(final_newsletter)
        console.print("="*60)

        console.print(f"\n[green]Status: {review['status']}[/green]")
        if review.get("issues"):
            console.print(f"[yellow]Issues resolved: {len(review['issues'])}[/yellow]")

    asyncio.run(main())
