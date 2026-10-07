"""Helpers for the daily Claude routine that writes the posts.

    python scripts/posts.py brief                 # today's topic + recent titles for every site
    python scripts/posts.py add <site> <draft.md> # check a draft and file it under content/<site>/

A draft is markdown with front matter:

    ---
    title: "..."
    description: "..."
    tags: ["...", "..."]
    sources:
      - title: "..."
        url: "https://..."
    ---
    <body>
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

import yaml

from common import CONTENT_DIR, get_site, load_posts, load_sites, parse_front_matter, slugify

MIN_WORDS = 600


def pillar_for(site: dict, date: dt.date) -> str:
    pillars = site["pillars"]
    return pillars[date.toordinal() % len(pillars)]


def brief(date: dt.date) -> None:
    for slug, site in load_sites().items():
        posts = load_posts(slug)
        done = any(p.date == date for p in posts)
        print(f"## {slug} — {site['name']} ({site['domain']})")
        print(f"Tagline: {site['tagline']}")
        print(f"Audience: {' '.join(site['audience'].split())}")
        print(f"Today's topic area: {pillar_for(site, date)}")
        print(f"Already posted today: {'YES, skip this site' if done else 'no'}")
        print("Recent titles (don't repeat these angles):")
        for p in posts[:30]:
            print(f"  - {p.date}: {p.title}")
        if not posts:
            print("  - (none yet)")
        print()


def add(slug: str, draft: Path, date: dt.date) -> int:
    site = get_site(slug)
    meta, body = parse_front_matter(draft.read_text())
    problems = []
    title = (meta.get("title") or "").strip()
    if not title:
        problems.append("missing title")
    elif len(title) > 90:
        problems.append(f"title is {len(title)} characters (keep it under 75)")
    if not (meta.get("description") or "").strip():
        problems.append("missing description")
    words = len(body.split())
    if words < MIN_WORDS:
        problems.append(f"body is {words} words (minimum {MIN_WORDS})")
    if re.search(r"^# ", body, re.M):
        problems.append("body contains an H1 (# ...); use ## for subheadings")
    sources = meta.get("sources") or []
    if not sources or not all(isinstance(s, dict) and str(s.get("url", "")).startswith("http") for s in sources):
        problems.append("sources must be a list of {title, url} with at least one http(s) url")
    if problems:
        print(f"[{slug}] draft rejected:\n  - " + "\n  - ".join(problems), file=sys.stderr)
        return 1

    posts = load_posts(slug)
    post_slug = slugify(title)
    if any(p.slug == post_slug for p in posts):
        post_slug = f"{post_slug}-{date:%Y%m%d}"
    front = {
        "title": title,
        "description": meta["description"].strip(),
        "date": date.isoformat(),
        "slug": post_slug,
        "tags": meta.get("tags") or [],
        "pillar": pillar_for(site, date),
        "sources": sources[:15],
    }
    out = CONTENT_DIR / slug / f"{date.isoformat()}-{post_slug}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("---\n" + yaml.safe_dump(front, sort_keys=False, allow_unicode=True) + "---\n\n" + body)
    print(f"[{slug}] filed {out.relative_to(CONTENT_DIR.parent)} ({words} words)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("brief")
    b.add_argument("--date", type=dt.date.fromisoformat, default=dt.date.today())
    a = sub.add_parser("add")
    a.add_argument("site")
    a.add_argument("draft", type=Path)
    a.add_argument("--date", type=dt.date.fromisoformat, default=dt.date.today())
    args = ap.parse_args()
    if args.cmd == "brief":
        brief(args.date)
        return 0
    return add(args.site, args.draft, args.date)


if __name__ == "__main__":
    sys.exit(main())
