"""
email_sender.py — Premium dark editorial HTML email for AI Weekly

Design: Bloomberg Terminal meets The Economist dark edition.
- Deep #0a0a0f background throughout — no white cards, no light panels
- DM Serif Display for headlines, IBM Plex Mono for labels, Inter for body
- Per-section 2px colored left-border rules, no pill badges
- Research papers in stacked mono-label metadata rows
- GitHub in minimal borderless monospace table
- Empty sections silently skipped — no placeholder text
- Single muted footer line
"""

import smtplib
import os
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


# ─────────────────────────────────────────────
# DESIGN TOKENS
# ─────────────────────────────────────────────

C_BG       = "#0a0a0f"   # deep dark — used everywhere
C_HEADER   = "#0d0d14"   # slightly lighter for header band
C_HEADLINE = "#f0f0f8"   # near-white for titles
C_BODY     = "#c8c8d0"   # body text
C_MUTED    = "#4e4e68"   # labels, metadata, secondary text
C_DIVIDER  = "#14141e"   # subtle item separator (~6% white on bg)
C_BLUE     = "#3b7eff"   # electric blue eyebrow
C_LINK     = "#7cb9ff"   # readable link on dark

SECTION_COLORS = {
    "top_story": "#f59e0b",   # amber
    "models":    "#3b82f6",   # blue
    "research":  "#8b5cf6",   # violet
    "github":    "#10b981",   # emerald
    "tools":     "#06b6d4",   # cyan
    "videos":    "#ef4444",   # red
}

SECTION_LABELS = {
    "top_story": "TOP STORY",
    "models":    "MODEL RELEASES",
    "research":  "RESEARCH HIGHLIGHTS",
    "github":    "GITHUB REPOS",
    "tools":     "NEW TOOLS & LAUNCHES",
    "videos":    "WATCH THIS WEEK",
}

SECTION_HEADING_MAP = {
    "top story":                "top_story",
    "model releases":           "models",
    "model releases & updates": "models",
    "research highlights":      "research",
    "github repos":             "github",
    "github repos of the week": "github",
    "new tools":                "tools",
    "new tools & launches":     "tools",
    "watch this week":          "videos",
}

DM_SERIF = "'DM Serif Display', Georgia, 'Times New Roman', serif"
IBM_MONO = "'IBM Plex Mono', 'Courier New', Courier, monospace"
INTER    = "Inter, 'Helvetica Neue', Helvetica, Arial, sans-serif"


# ─────────────────────────────────────────────
# INLINE MARKDOWN HELPERS
# ─────────────────────────────────────────────

def _md_inline(text: str, headline: bool = False) -> str:
    """Convert inline markdown to HTML, styled for dark background."""
    # Bold+italic
    text = re.sub(r'\*\*\*(.+?)\*\*\*', r'<strong><em>\1</em></strong>', text)
    # Bold
    fg = C_HEADLINE if headline else "#dcdce8"
    text = re.sub(
        r'\*\*(.+?)\*\*',
        rf'<strong style="font-weight:600;color:{fg};">\1</strong>',
        text,
    )
    # Italic
    text = re.sub(
        r'\*(.+?)\*',
        rf'<em style="color:{C_MUTED};font-style:italic;">\1</em>',
        text,
    )
    # Backtick tags / badges
    text = re.sub(r'`([^`]+)`', lambda m: _tag(m.group(1)), text)
    # Links
    text = re.sub(
        r'\[([^\]]+)\]\((https?://[^\)]+)\)',
        rf'<a href="\2" style="color:{C_LINK};text-decoration:none;'
        rf'border-bottom:1px solid #2a4a6e;">\1</a>',
        text,
    )
    return text


def _tag(text: str) -> str:
    """Render a `backtick` tag — difficulty or pricing — inline with color."""
    t  = text.strip()
    lo = t.lower()
    if "🟢" in t or lo == "accessible":
        fg = "#4ade80"
    elif "🟡" in t or lo == "technical":
        fg = "#fbbf24"
    elif "🔴" in t or "deep research" in lo:
        fg = "#f87171"
    elif lo in ("free", "open source", "open-source"):
        fg = "#4ade80"
    elif lo == "freemium":
        fg = "#60a5fa"
    elif lo in ("paid", "enterprise"):
        fg = C_MUTED
    else:
        fg = "#9ca3af"
    return (
        f'<span style="font-family:{IBM_MONO};font-size:10px;font-weight:600;'
        f'color:{fg};letter-spacing:0.5px;text-transform:uppercase;">{t}</span>'
    )


# ─────────────────────────────────────────────
# SECTION SKIP LOGIC
# ─────────────────────────────────────────────

def _has_content(lines: list[str]) -> bool:
    """Return True if a section has at least one renderable item."""
    for line in lines:
        s = line.strip()
        if s.startswith('**[') and '](' in s:
            return True
        if s.startswith('### [') and '](' in s:
            return True
        if s.startswith('▶'):
            return True
        if s.startswith('|'):
            # Non-separator table row with actual text cells
            if not re.match(r'^\|[\s\-:]+\|', s):
                cells = [c.strip() for c in s.strip('|').split('|')]
                if any(c and not re.match(r'^[-:]+$', c) for c in cells):
                    return True
    return False


# ─────────────────────────────────────────────
# ITEM SEPARATOR
# ─────────────────────────────────────────────

_ITEM_SEP = (
    f'<table width="100%" cellpadding="0" cellspacing="0" role="presentation"'
    f' style="margin:20px 0;">'
    f'<tr><td style="border-top:1px solid {C_DIVIDER};font-size:0;line-height:0;">&nbsp;</td></tr>'
    f'</table>'
)


# ─────────────────────────────────────────────
# TOP STORY RENDERER (special format)
# ─────────────────────────────────────────────

def _render_top_story(lines: list[str]) -> str:
    headline = source = ""
    body_paras: list[str] = []

    for line in lines:
        s = line.strip()
        if not s or s.startswith('---'):
            continue
        h3 = re.match(r'^###\s+(.+)$', s)
        if h3:
            headline = h3.group(1)
        elif s.startswith('> ') and not source:
            source = s.lstrip('> ').strip()
        elif s.startswith('*') and s.endswith('*') and len(s) < 120:
            pass  # sub-heading italic — skip
        else:
            body_paras.append(s)

    html = ""
    if headline:
        hl = _md_inline(headline, headline=True)
        html += (
            f'<p style="margin:0 0 8px;font-family:{DM_SERIF};font-size:24px;'
            f'font-weight:400;color:{C_HEADLINE};line-height:1.2;">{hl}</p>'
        )
    if source:
        html += (
            f'<p style="margin:0 0 16px;font-family:{INTER};font-size:12px;'
            f'color:{C_MUTED};font-style:italic;">{_md_inline(source)}</p>'
        )
    for para in body_paras:
        html += (
            f'<p style="margin:0 0 10px;font-family:{INTER};font-size:15px;'
            f'color:{C_BODY};line-height:1.7;">{_md_inline(para)}</p>'
        )
    return html


# ─────────────────────────────────────────────
# RESEARCH METADATA RENDERER
# ─────────────────────────────────────────────

def _render_research_item(item_lines: list[str]) -> str:
    title_line = ""
    what = why = who = ""
    extra: list[str] = []

    for line in item_lines:
        s = line.strip()
        if not s:
            continue
        bq = re.match(r'^>\s*\*\*(.+?):\*\*\s*(.*)', s)
        if bq:
            key = bq.group(1).lower()
            val = bq.group(2).strip()
            if "what" in key:
                what = val
            elif "why" in key:
                why = val
            elif "who" in key:
                who = val
        elif re.match(r'^\*\*\[', s):
            title_line = s
        elif not s.startswith('`') and not re.match(r'^[🟢🟡🔴]', s):
            extra.append(s)

    html = ""

    # Title + difficulty tag
    if title_line:
        clean = re.sub(r'`[^`]+`', '', title_line).strip()
        tag_m = re.search(r'`([^`]+)`', title_line)
        html += (
            f'<p style="margin:0 0 14px;font-family:{DM_SERIF};font-size:18px;'
            f'font-weight:400;color:{C_HEADLINE};line-height:1.3;">'
            f'{_md_inline(clean, headline=True)}'
        )
        if tag_m:
            html += f'&nbsp;&nbsp;{_tag(tag_m.group(1))}'
        html += '</p>'

    # Three metadata rows
    meta_label_style = (
        f'font-family:{IBM_MONO};font-size:9px;font-weight:600;'
        f'letter-spacing:2.5px;text-transform:uppercase;color:{C_MUTED};'
        f'display:block;margin:0 0 4px;'
    )
    meta_val_style = (
        f'font-family:{INTER};font-size:13px;color:{C_BODY};'
        f'line-height:1.55;margin:0 0 12px;'
    )

    for label, val in [("What they did", what), ("Why it matters", why), ("Who should care", who)]:
        if val:
            html += (
                f'<p style="{meta_label_style}">{label.upper()}</p>'
                f'<p style="{meta_val_style}">{_md_inline(val)}</p>'
            )

    return html


# ─────────────────────────────────────────────
# GITHUB TABLE RENDERER
# ─────────────────────────────────────────────

def _render_github_table(rows: list[str]) -> str:
    """Minimal borderless table with monospace repo names."""
    th_style = (
        f'font-family:{IBM_MONO};font-size:9px;font-weight:600;'
        f'letter-spacing:2px;text-transform:uppercase;color:{C_MUTED};'
        f'padding:0 16px 10px 0;text-align:left;'
        f'border-bottom:1px solid {C_DIVIDER};'
    )
    td_style = (
        f'font-family:{INTER};font-size:13px;color:{C_BODY};'
        f'padding:10px 16px 10px 0;vertical-align:top;'
        f'border-bottom:1px solid {C_DIVIDER};'
    )
    mono_style = (
        f'font-family:{IBM_MONO};font-size:12px;color:{C_LINK};'
        f'padding:10px 16px 10px 0;vertical-align:top;'
        f'border-bottom:1px solid {C_DIVIDER};'
    )

    html = (
        f'<table width="100%" cellpadding="0" cellspacing="0" role="presentation"'
        f' style="border-collapse:collapse;margin-top:8px;">'
    )
    is_header = True
    for row in rows:
        if re.match(r'^\s*\|?\s*[-:]+', row):
            continue
        cells = [c.strip() for c in row.strip().strip('|').split('|')]
        if is_header:
            html += '<thead><tr>'
            for c in cells:
                html += f'<th style="{th_style}">{c}</th>'
            html += '</tr></thead><tbody>'
            is_header = False
        else:
            html += '<tr>'
            for i, c in enumerate(cells):
                style = mono_style if i == 0 else td_style
                html += f'<td style="{style}">{_md_inline(c)}</td>'
            html += '</tr>'
    html += '</tbody></table>'
    return html


# ─────────────────────────────────────────────
# GENERIC SECTION RENDERER
# ─────────────────────────────────────────────

def _render_section_body(lines: list[str], section_key: str) -> str:
    """Parse and render all items in a section."""

    if section_key == "top_story":
        return _render_top_story(lines)

    color = SECTION_COLORS[section_key]
    html  = ""
    i     = 0
    items: list[str] = []  # collect rendered items, join with separator

    # Skip leading italic subtitle
    if lines and lines[0].strip().startswith('*') and lines[0].strip().endswith('*'):
        i = 1

    while i < len(lines):
        line = lines[i]
        s    = line.strip()

        if not s or s.startswith('---'):
            i += 1
            continue

        # ── GitHub table ──
        if s.startswith('|'):
            table_rows: list[str] = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                table_rows.append(lines[i])
                i += 1
            table_html = _render_github_table(table_rows)
            # Collect Quick Start notes after the table
            qs_html = ""
            while i < len(lines):
                qs = lines[i].strip()
                if qs.startswith('> 💡') or qs.startswith('> 💡'):
                    inner = _md_inline(qs.lstrip('> ').strip())
                    qs_html += (
                        f'<p style="margin:10px 0 0;font-family:{INTER};font-size:12px;'
                        f'color:{C_MUTED};line-height:1.5;">{inner}</p>'
                    )
                    i += 1
                elif not qs:
                    i += 1
                    break
                else:
                    break
            items.append(table_html + qs_html)
            continue

        # ── Video item ──
        if s.startswith('▶'):
            content  = s.lstrip('▶ ').strip()
            # Collect description line(s) that follow
            desc_lines: list[str] = []
            i += 1
            while i < len(lines):
                nxt = lines[i].strip()
                if not nxt:
                    i += 1
                    break
                if nxt.startswith('▶') or nxt.startswith('**') or nxt.startswith('---'):
                    break
                desc_lines.append(nxt)
                i += 1
            vid_html = (
                f'<p style="margin:0 0 4px;font-family:{INTER};font-size:15px;'
                f'font-weight:500;color:{C_HEADLINE};line-height:1.3;">'
                f'{_md_inline(content)}</p>'
            )
            if desc_lines:
                desc = " ".join(desc_lines)
                vid_html += (
                    f'<p style="margin:0;font-family:{INTER};font-size:13px;'
                    f'color:{C_MUTED};line-height:1.55;">{_md_inline(desc)}</p>'
                )
            items.append(vid_html)
            continue

        # ── Bold-title item (models, tools, research) ──
        if s.startswith('**'):
            item_lines = [s]
            i += 1
            while i < len(lines):
                nxt = lines[i].strip()
                if not nxt:
                    # Look ahead — new item starts after blank?
                    j = i + 1
                    while j < len(lines) and not lines[j].strip():
                        j += 1
                    if j < len(lines) and lines[j].strip().startswith('**'):
                        i += 1
                        break
                    else:
                        i += 1
                        continue
                if nxt.startswith('---') or nxt.startswith('## '):
                    break
                item_lines.append(nxt)
                i += 1

            if section_key == "research":
                items.append(_render_research_item(item_lines))
            else:
                items.append(_render_standard_item(item_lines, section_key))
            continue

        # Blockquote
        if s.startswith('> '):
            inner = _md_inline(s.lstrip('> ').strip())
            html += (
                f'<p style="margin:8px 0;font-family:{INTER};font-size:13px;'
                f'color:{C_MUTED};font-style:italic;">{inner}</p>'
            )
            i += 1
            continue

        # Default paragraph
        html += (
            f'<p style="margin:8px 0;font-family:{INTER};font-size:15px;'
            f'color:{C_BODY};line-height:1.65;">{_md_inline(s)}</p>'
        )
        i += 1

    # Join items with thin separator
    if items:
        html += _ITEM_SEP.join(items)

    return html


def _render_standard_item(item_lines: list[str], section_key: str) -> str:
    """Render a standard bold-title item (models, tools)."""
    color = SECTION_COLORS[section_key]
    html  = ""
    title_done = False

    for line in item_lines:
        s = line.strip()
        if not s:
            continue
        if s.startswith('**') and not title_done:
            # Extract optional tags (pricing, audience) from same line
            # e.g. **[Name](url)** — `Free` · `Developers`
            clean = re.sub(r'`[^`]+`', '', s).strip().rstrip('·').strip()
            tags  = re.findall(r'`([^`]+)`', s)
            html += (
                f'<p style="margin:0 0 5px;font-family:{INTER};font-size:15px;'
                f'font-weight:600;color:{C_HEADLINE};line-height:1.3;">'
                f'{_md_inline(clean)}'
            )
            if tags:
                html += '&nbsp;&nbsp;' + '&nbsp;'.join(_tag(t) for t in tags)
            html += '</p>'
            title_done = True
        elif s.startswith('> '):
            inner = _md_inline(s.lstrip('> ').strip())
            html += (
                f'<p style="margin:4px 0;font-family:{INTER};font-size:12px;'
                f'color:{C_MUTED};font-style:italic;">{inner}</p>'
            )
        else:
            html += (
                f'<p style="margin:6px 0 0;font-family:{INTER};font-size:14px;'
                f'color:{C_BODY};line-height:1.6;">{_md_inline(s)}</p>'
            )
    return html


# ─────────────────────────────────────────────
# SECTION WRAPPER (left-border rule)
# ─────────────────────────────────────────────

def _section_wrapper(content_html: str, section_key: str) -> str:
    color = SECTION_COLORS[section_key]
    label = SECTION_LABELS[section_key]
    return (
        # Section block
        f'<table width="100%" cellpadding="0" cellspacing="0" role="presentation">'
        f'<tr>'
        # 2px color rule
        f'<td width="2" style="background-color:{color};border-radius:1px;">&nbsp;</td>'
        # Content
        f'<td style="padding:0 0 0 24px;">'
        # Section label
        f'<p style="margin:0 0 20px;font-family:{IBM_MONO};font-size:10px;'
        f'font-weight:600;letter-spacing:3px;text-transform:uppercase;color:{color};">'
        f'{label}</p>'
        + content_html +
        f'</td>'
        f'</tr>'
        f'</table>'
        # Inter-section spacer
        f'<table width="100%" cellpadding="0" cellspacing="0" role="presentation"'
        f' style="margin:36px 0 0;">'
        f'<tr><td style="border-top:1px solid #1a1a28;font-size:0;">&nbsp;</td></tr>'
        f'</table>'
        f'<table width="100%" cellpadding="0" cellspacing="0" role="presentation"'
        f' style="margin:0 0 36px;">'
        f'<tr><td style="font-size:0;">&nbsp;</td></tr>'
        f'</table>'
    )


# ─────────────────────────────────────────────
# MAIN CONVERTER
# ─────────────────────────────────────────────

def _markdown_to_html(markdown_text: str) -> str:
    """Convert newsletter markdown to dark editorial HTML email."""
    lines = markdown_text.splitlines()

    # Extract edition
    edition = "AI Weekly"
    for line in lines[:5]:
        if line.strip().startswith("# AI Weekly"):
            m = re.search(r'(\d{4}-W\d{2})', line)
            if m:
                edition = m.group(1)
            break

    # Parse into sections
    sections: list[tuple[str, list[str]]] = []
    current_key   = "preamble"
    current_lines: list[str] = []

    for line in lines:
        if line.strip().startswith("# AI Weekly"):
            continue
        if line.strip().startswith("*The week's") or line.strip().startswith("*Generated"):
            continue

        h2 = re.match(r'^##\s+(.+)$', line.strip())
        if h2:
            if current_lines:
                sections.append((current_key, current_lines))
            heading_clean = re.sub(r'[^\w\s&]', '', h2.group(1)).strip().lower()
            current_key   = SECTION_HEADING_MAP.get(heading_clean, "other")
            current_lines = []
            continue

        current_lines.append(line)

    if current_lines:
        sections.append((current_key, current_lines))

    # Render sections — skip empties
    body_html = ""
    for key, sec_lines in sections:
        if key not in SECTION_COLORS:
            continue
        if not _has_content(sec_lines):
            continue
        content = _render_section_body(sec_lines, key)
        body_html += _section_wrapper(content, key)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>AI Weekly — {edition}</title>
  <link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=IBM+Plex+Mono:wght@400;500;600&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    body  {{ margin:0;padding:0;background-color:{C_BG}; }}
    a     {{ color:{C_LINK};text-decoration:none; }}
    img   {{ border:0;display:block; }}
    @media only screen and (max-width:640px) {{
      .outer-wrap   {{ padding:0 !important; }}
      .main-table   {{ width:100% !important; }}
      .hero-pad     {{ padding:40px 24px 36px !important; }}
      .content-pad  {{ padding:36px 24px !important; }}
      .section-left {{ padding-left:18px !important; }}
    }}
  </style>
</head>
<body style="margin:0;padding:0;background-color:{C_BG};">

<!-- Outer wrapper -->
<table class="outer-wrap" width="100%" cellpadding="0" cellspacing="0"
       role="presentation" style="background-color:{C_BG};padding:32px 16px;">
<tr><td align="center">

  <!-- Main card (dark throughout) -->
  <table class="main-table" width="660" cellpadding="0" cellspacing="0"
         role="presentation" style="max-width:660px;width:100%;">

    <!-- ══════════ HEADER ══════════ -->
    <tr>
      <td class="hero-pad"
          style="background-color:{C_HEADER};padding:52px 48px 44px;
                 border-bottom:1px solid #18182a;">

        <!-- Eyebrow -->
        <p style="margin:0 0 22px;font-family:{IBM_MONO};font-size:9px;
                   font-weight:600;letter-spacing:4px;text-transform:uppercase;
                   color:{C_BLUE};">WEEKLY INTELLIGENCE DIGEST</p>

        <!-- Title -->
        <h1 style="margin:0 0 24px;font-family:{DM_SERIF};font-size:52px;
                   font-weight:400;color:{C_HEADLINE};line-height:1;
                   letter-spacing:-1px;">AI Weekly</h1>

        <!-- Edition + tagline with vertical rule -->
        <table cellpadding="0" cellspacing="0" role="presentation">
          <tr>
            <!-- Vertical rule -->
            <td width="1" style="background-color:#2a2a45;padding:0;">&nbsp;</td>
            <td style="padding:2px 0 2px 16px;">
              <p style="margin:0 0 4px;font-family:{IBM_MONO};font-size:11px;
                         font-weight:500;color:#3d3d5c;letter-spacing:1px;">
                {edition}
              </p>
              <p style="margin:0;font-family:{INTER};font-size:13px;
                         color:{C_MUTED};line-height:1.4;">
                Signal over noise — curated for builders, researchers &amp; practitioners
              </p>
            </td>
          </tr>
        </table>

      </td>
    </tr>

    <!-- ══════════ CONTENT ══════════ -->
    <tr>
      <td class="content-pad"
          style="background-color:{C_BG};padding:44px 48px 40px;">
        {body_html}
      </td>
    </tr>

    <!-- ══════════ FOOTER ══════════ -->
    <tr>
      <td style="background-color:{C_BG};padding:0 48px 40px;text-align:center;
                 border-top:1px solid #14141e;">
        <p style="margin:24px 0 0;font-family:{IBM_MONO};font-size:10px;
                   color:#2e2e48;letter-spacing:1px;">
          AI Weekly &nbsp;&middot;&nbsp; {edition}
          &nbsp;&middot;&nbsp; Stories deduplicated against last 4 weeks
        </p>
      </td>
    </tr>

  </table>

</td></tr>
</table>

</body>
</html>"""


# ─────────────────────────────────────────────
# SEND
# ─────────────────────────────────────────────

def send_email(
    draft_filepath: str,
    subject: str | None = None,
    recipients: list[str] | None = None,
) -> str:
    """Send the newsletter draft as a premium dark HTML email via SMTP."""
    smtp_host  = os.getenv("SMTP_HOST", "")
    smtp_port  = int(os.getenv("SMTP_PORT", 587))
    smtp_user  = os.getenv("SMTP_USER", "")
    smtp_pass  = os.getenv("SMTP_PASS", "")
    email_from = os.getenv("EMAIL_FROM", smtp_user)
    email_to   = os.getenv("EMAIL_TO", "")

    if not smtp_host or not smtp_user or not smtp_pass:
        return (
            f"Email not configured — newsletter saved at {draft_filepath}\n"
            "To enable email, add SMTP_HOST, SMTP_USER, SMTP_PASS to your .env file."
        )

    if not recipients:
        if not email_to:
            return f"No recipients configured. Draft saved at {draft_filepath}"
        recipients = [r.strip() for r in email_to.split(",")]

    draft_path = Path(draft_filepath)
    if not draft_path.exists():
        return f"Draft file not found: {draft_filepath}"

    markdown_body = draft_path.read_text(encoding="utf-8")

    if not subject:
        stem    = draft_path.stem
        edition = stem.replace("-ai-weekly", "")
        subject = f"AI Weekly — {edition}"

    html_body = _markdown_to_html(markdown_body)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = email_from
    msg["To"]      = ", ".join(recipients)

    msg.attach(MIMEText(markdown_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body,     "html",  "utf-8"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(email_from, recipients, msg.as_string())
        return f"Newsletter sent to {len(recipients)} recipient(s): {', '.join(recipients)}"
    except Exception as e:
        return f"Email send failed: {e}"
