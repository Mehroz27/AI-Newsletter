"""
formatter.py — Formatter Agent for AI Weekly Newsletter

Responsibilities:
1. Receive curated JSON from the Curator agent
2. Fetch full article text for the top story (via MCP)
3. Use GPT-4o to write each section beautifully and consistently
4. Output a complete polished markdown newsletter

Model: gpt-4o (higher quality writing)
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

SYSTEM_PROMPT = """You are the editor of AI Weekly, a newsletter read by ML engineers, AI researchers, and tech practitioners.

Your writing style:
- Concise, sharp, and technically accurate
- No hype, no filler, no buzzwords
- Lead with what's actually novel or important
- Assume the reader knows what LLMs, transformers, and RAG are
- Use plain English for complex concepts — smart but not condescending

You will receive curated newsletter data and must write each section following the exact template provided.
Return ONLY the complete markdown newsletter — no explanations, no preamble, just the newsletter content.
"""

NEWSLETTER_TEMPLATE = """Write a complete newsletter using this exact markdown structure:

# AI Weekly — {edition}
*The week's most important AI developments, curated for practitioners*
*{date}*

---

## 🔥 Top Story
### [{top_story_title}]({top_story_url})
> {top_story_source}

{top_story_body}

---

## 🤖 Model Releases & Updates
{model_releases_section}

---

## 📄 Research Highlights
*Selected for genuine novelty — with plain-English breakdowns*

{research_section}

---

## ⭐ GitHub Repos of the Week
*AI-specific repos trending hard this week*

{github_section}

---

## 🛠 New Tools & Launches
*New products you can try right now*

{tools_section}

---

## 🎬 Watch This Week
{videos_section}

---

*Generated: {date} | Sources: OpenAI, Anthropic, HuggingFace, ArXiv, GitHub Trending, TechCrunch, The Verge*
*Edition {edition} — Stories filtered against last 4 weeks to avoid repeats*

---

Section writing rules:

- Top Story: 3-4 sentences. What happened, why it matters, what comes next. Use the full article text provided. Write for a smart, curious professional — no jargon without explanation.

- Model Releases: Each item as "**[Title](url)** — *(Source)* — 1-2 sentence summary. Lead with what's new and concretely different from before."

- Research: Write each paper using this exact 3-part format on ONE line:
  **[Title](url)** `🟢 Accessible` or `🟡 Technical` or `🔴 Deep Research`
  > **What they did:** [1 sentence — explain like to a smart friend who doesn't work in AI. No jargon without a quick explanation.]
  > **Why it matters:** [1 sentence — real-world practical implication, not academic significance.]
  > **Who should care:** [one tag: `Practitioners` / `Researchers` / `Everyone`]

- GitHub Repos: Write a table with these exact columns: `Repo` | `⭐ This Week` | `Stack` | `What It Does` | `Best For`
  Then under EACH repo row, add one line: `> 💡 **Quick start:** [1 sentence on the fastest way to try this repo]`
  "Best For" = one of: Builders / Researchers / Learners / Production

- Tools: Each item as:
  **[Name](url)** — `[Pricing]` · `[Audience]`
  [1-2 sentences: what problem it solves, what makes it stand out, and who should try it first.]

- Videos: Each item as:
  ▶ **[Title](url)** — *Channel*
  [1-2 sentences: what the video covers and why it's worth watching for AI practitioners. Use the summary field from the curated data as a starting point but write in your own voice.]
  Only include videos that are directly about AI — models, tools, agents, automation, LLMs, AI workflows. If a video in the curated data is not clearly about AI, omit it.
"""


async def run_formatter(curated: dict) -> str:
    """
    Main formatter pipeline:
    1. Connect to MCP server
    2. Fetch full text of top story
    3. Send everything to GPT-4o for writing
    4. Return polished markdown newsletter
    """

    server_params = StdioServerParameters(
        command="python",
        args=["mcp_server.py"],
        cwd=os.path.dirname(os.path.abspath(__file__)),
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            console.print(Panel("Formatter Agent Starting", style="blue"))

            # ── Fetch full text of top story for deeper summary ──
            top_story = curated.get("top_story", {})
            top_story_text = ""

            if top_story.get("url"):
                console.print(f"[blue]Fetching full text: {top_story['url'][:60]}...[/blue]")
                result = await session.call_tool(
                    "fetch_article_content",
                    {"url": top_story["url"], "max_chars": 3000}
                )
                top_story_text = result.content[0].text
                if top_story_text:
                    console.print("[green]Full article text fetched[/green]")
                else:
                    console.print("[yellow]Could not fetch article text — using summary[/yellow]")
                    top_story_text = top_story.get("summary", "")

            # ── Build the prompt ──
            edition = _current_edition()
            date_str = datetime.now(timezone.utc).strftime("%B %d, %Y")

            user_prompt = f"""Here is the curated newsletter data for {edition}.

TOP STORY FULL TEXT:
{top_story_text or top_story.get('summary', '')}

CURATED DATA:
{json.dumps(curated, indent=2, ensure_ascii=False)}

{NEWSLETTER_TEMPLATE.format(
    edition=edition,
    date=date_str,
    top_story_title=top_story.get('title', ''),
    top_story_url=top_story.get('url', ''),
    top_story_source=top_story.get('source', ''),
    top_story_body="[Write 3-4 sentences using the full article text above]",
    model_releases_section="[Write each model release as specified]",
    research_section="[Write each research item as specified]",
    github_section="[Write the GitHub repos table]",
    tools_section="[Write each tool as specified]",
    videos_section="[Write each video as specified]",
)}"""

            # ── Send to GPT-4o ──
            console.print("[blue]Writing newsletter with GPT-4o...[/blue]")

            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                max_tokens=4000,
            )

            newsletter = response.choices[0].message.content

            console.print(Panel(
                f"Newsletter written\n"
                f"Length: {len(newsletter)} characters\n"
                f"Edition: {edition}",
                title="Formatter Complete",
                style="blue"
            ))

            return newsletter


def _current_edition() -> str:
    now = datetime.now(timezone.utc)
    year, week, _ = now.isocalendar()
    return f"{year}-W{week:02d}"


if __name__ == "__main__":
    # Load the curated output from curator.py and format it
    # Run: python curator.py > curated.json first, or pipe directly

    import sys

    # If curated JSON is piped in via stdin
    if not sys.stdin.isatty():
        curated = json.load(sys.stdin)
    else:
        # Run curator first to get fresh data
        console.print("[yellow]No input provided. Running curator first...[/yellow]")
        from curator import run_curator
        curated = asyncio.run(run_curator())

    newsletter = asyncio.run(run_formatter(curated))

    console.print("\n" + "="*60)
    console.print(newsletter)
    console.print("="*60)
