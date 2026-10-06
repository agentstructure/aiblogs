"""Write today's post for one or more sites with Claude (with live web search).

Usage:
    python scripts/generate_post.py beforethebreakout capitalraising ...
    python scripts/generate_post.py --all [--count 3]
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
import textwrap

import anthropic
import yaml

from common import CONTENT_DIR, get_site, load_posts, load_sites, parse_front_matter, slugify

MODEL = os.environ.get("CLAUDE_MODEL") or "claude-opus-5-5"
EFFORT = os.environ.get("POST_EFFORT") or "high"
MIN_WORDS = 600

SYSTEM = """\
You are the staff writer for {name} ({domain}), a blog whose tagline is "{tagline}".

Audience: {audience}

You write one original, genuinely useful article per day. House rules:
- Research first. Use web search to find what actually happened in the last few days on the
  assigned topic, and build the article on real, current, verifiable facts. Never invent numbers,
  quotes, deals, tickers, prices or dates. If you cannot verify something, leave it out.
- Name specific companies with their tickers in parentheses, e.g. Lockheed Martin (LMT).
- Link to your sources inline with markdown links where you cite a fact.
- Be specific and analytical, not generic. Explain why it matters to this audience and what to
  watch next. No filler, no hype, no "in today's fast-paced world" intros.
- This is information and commentary, not personalized investment advice. Do not tell readers
  to buy or sell anything.
- Length: 900 to 1,400 words. Use a few `##` subheadings and short paragraphs. Bullet lists are
  fine where they help. Do not include an H1 title in the body.
"""

FORMAT = """\
When your research is done, reply with the finished article only, in exactly this format and
with nothing before or after it:

---
title: "<headline under 75 characters, specific, no clickbait>"
description: "<one-sentence summary under 160 characters for search results and the email roundup>"
tags: ["<tag>", "<tag>", "<tag>"]
---
<article body in markdown>
"""


def pick_pillar(site: dict, date: dt.date, offset: int = 0) -> str:
    pillars = site["pillars"]
    return pillars[(date.toordinal() + offset) % len(pillars)]


def extract_article(message) -> tuple[str, list[dict]]:
    """Join the final text blocks and collect cited sources."""
    text_parts, sources, seen = [], [], set()
    for block in message.content:
        if block.type != "text":
            continue
        text_parts.append(block.text)
        for c in getattr(block, "citations", None) or []:
            url = getattr(c, "url", None)
            if url and url not in seen:
                seen.add(url)
                sources.append({"title": getattr(c, "title", None) or url, "url": url})
    text = "".join(text_parts)
    start = text.rfind("---\ntitle:")
    if start == -1:
        raise ValueError("Claude's reply did not contain the article front matter")
    return text[start:], sources


def call_claude(client: anthropic.Anthropic, system: str, prompt: str):
    messages = [{"role": "user", "content": prompt}]
    for _ in range(6):  # web search turns can pause; resume until done
        with client.beta.messages.stream(
            model=MODEL,
            max_tokens=32000,
            system=system,
            messages=messages,
            thinking={"type": "adaptive"},
            output_config={"effort": EFFORT},
            tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 8}],
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        ) as stream:
            message = stream.get_final_message()
        if message.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": message.content})
            continue
        if message.stop_reason == "refusal":
            raise RuntimeError(f"Claude declined the request: {message.stop_details}")
        if message.stop_reason == "max_tokens":
            raise RuntimeError("Claude hit max_tokens before finishing the article")
        return message
    raise RuntimeError("Too many paused turns while researching")


def generate(client: anthropic.Anthropic, site: dict, date: dt.date, offset: int = 0) -> str:
    posts = load_posts(site["slug"])
    recent = "\n".join(f"- {p.date}: {p.title}" for p in posts[:60]) or "- (none yet)"
    pillar = pick_pillar(site, date, offset)
    prompt = textwrap.dedent(f"""\
        Today is {date:%A, %B %-d, %Y}.

        Today's topic area: {pillar}

        Pick the single most timely and interesting angle within that topic area based on news
        from the last few days, research it, and write the article.

        Recent articles on this blog. Do not repeat these angles; cover something new:
        {recent}

        """) + FORMAT

    system = SYSTEM.format(**site)
    message = call_claude(client, system, prompt)
    article, sources = extract_article(message)
    meta, body = parse_front_matter(article)

    words = len(body.split())
    if not meta.get("title") or words < MIN_WORDS:
        raise RuntimeError(f"Article failed checks (title={meta.get('title')!r}, words={words})")

    slug = slugify(meta["title"])
    if any(p.slug == slug for p in posts):
        slug = f"{slug}-{date:%Y%m%d}"
    front = {
        "title": meta["title"],
        "description": meta.get("description", ""),
        "date": date.isoformat(),
        "slug": slug,
        "tags": meta.get("tags") or [],
        "pillar": pillar,
        "sources": sources[:15],
        "model": message.model,
    }
    out = CONTENT_DIR / site["slug"] / f"{date.isoformat()}-{slug}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("---\n" + yaml.safe_dump(front, sort_keys=False, allow_unicode=True) + "---\n\n" + body)
    print(f"[{site['slug']}] wrote {out.relative_to(CONTENT_DIR.parent)} ({words} words)")
    return str(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("sites", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--count", type=int, default=1, help="posts per site (for backfilling a new site)")
    ap.add_argument("--date", type=dt.date.fromisoformat, default=dt.date.today())
    args = ap.parse_args()

    slugs = list(load_sites()) if args.all else args.sites
    if not slugs:
        ap.error("name at least one site or pass --all")

    client = anthropic.Anthropic()
    failures = []
    for slug in slugs:
        site = get_site(slug)
        for i in range(args.count):
            try:
                generate(client, site, args.date, offset=i)
            except Exception as e:  # keep going so one site can't block the others
                print(f"::error title={slug}::{e}", file=sys.stderr)
                failures.append(slug)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
