"""Email each site's subscribers a roundup of the last 7 days of articles (via Brevo).

Usage: python scripts/weekly_roundup.py --all [--dry-run]
--dry-run writes the emails to dist/emails/ without sending.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys

import anthropic
import markdown

from build import env
from common import ROOT, get_site, load_posts, load_sites

MODEL = os.environ.get("CLAUDE_MODEL") or "claude-opus-5-5"


def write_intro(client: anthropic.Anthropic, site: dict, posts) -> str:
    listing = "\n".join(f"- {p.title}: {p.description}" for p in posts)
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=4000,
        output_config={"effort": "low"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=(f"You write the weekly email newsletter for {site['name']} ({site['tagline']}). "
                f"Audience: {site['audience']}"),
        messages=[{"role": "user", "content": (
            "Write a 2 to 4 sentence intro for this week's roundup email that ties together the "
            "themes of these articles and gives readers a reason to click. Plain, confident, no hype, "
            "no greeting line, no sign-off, no investment advice. Reply with the intro only.\n\n" + listing
        )}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("Claude declined to write the intro")
    return "".join(b.text for b in response.content if b.type == "text").strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("sites", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    slugs = list(load_sites()) if args.all else args.sites
    if not slugs:
        ap.error("name at least one site or pass --all")

    today = dt.date.today()
    since = today - dt.timedelta(days=args.days)
    client = anthropic.Anthropic()
    brevo = None if args.dry_run else __import__("brevo").Brevo()
    failures = []

    for slug in slugs:
        site = get_site(slug)
        posts = [p for p in load_posts(slug) if since <= p.date < today + dt.timedelta(days=1)]
        if not posts:
            print(f"[{slug}] no posts since {since}, skipping")
            continue
        posts.sort(key=lambda p: p.date)
        try:
            intro = write_intro(client, site, posts)
            week_label = f"{posts[0].date:%b %-d} to {posts[-1].date:%b %-d, %Y}"
            subject = f"{site['name']} weekly: {posts[-1].title}"
            if len(posts) > 1:
                subject += f" + {len(posts) - 1} more"
            html = env.get_template("email.html").render(
                site=site, posts=posts, subject=subject, week_label=week_label,
                intro_html=markdown.markdown(intro))

            if args.dry_run:
                out = ROOT / "dist" / "emails" / f"{slug}-{today}.html"
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(html)
                print(f"[{slug}] dry run: {subject!r} -> {out.relative_to(ROOT)}")
                continue

            campaign_id = brevo.send_campaign(
                name=f"{site['name']} roundup {today}",
                subject=subject[:150],
                preview=intro[:140],
                html=html,
                sender_name=site["name"],
                sender_email=site.get("sender_email") or os.environ.get("SENDER_EMAIL") or f"newsletter@{site['domain']}",
                list_id=brevo.ensure_list(site),
            )
            print(f"[{slug}] sent campaign {campaign_id}: {subject!r} ({len(posts)} posts)")
        except Exception as e:
            print(f"::error title={slug}::{e}", file=sys.stderr)
            failures.append(slug)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
