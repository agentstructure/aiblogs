"""Email each site's subscribers a roundup of the last 7 days of articles (via Brevo).

The intro comes from roundups/<site>/<date>.md, written by the daily Claude routine on Mondays.

Usage: python scripts/weekly_roundup.py --all [--dry-run]
--dry-run writes the emails to dist/emails/ without sending.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys

import markdown

from build import env
from common import ROOT, get_site, load_posts, load_sites


def load_intro(site: dict, slug: str, posts, today: dt.date) -> str:
    """The routine writes roundups/<site>/<date>.md on Mondays; fall back to a plain intro."""
    path = ROOT / "roundups" / slug / f"{today.isoformat()}.md"
    if path.exists() and path.read_text().strip():
        return path.read_text().strip()
    n = len(posts)
    return (f"Here {'is' if n == 1 else 'are'} this week's {n} {site['name']} "
            f"article{'' if n == 1 else 's'}, in case you missed {'it' if n == 1 else 'any'}.")


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
            intro = load_intro(site, slug, posts, today)
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
