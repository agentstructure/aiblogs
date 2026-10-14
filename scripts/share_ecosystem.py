"""Share new agentstructure.ai ecosystem posts on social media.

Reads https://agentstructure.ai/api/blog/feed (the posts the daily writer publishes) and sends each
one from the last day to the same accounts as social.py (Buffer channels plus direct Bluesky,
Telegram and Discord), skipping what social.yaml's `skip` list turns off. Each share is recorded in
social/agentstructure.json so a post is never shared twice on the same account.

  python scripts/share_ecosystem.py             # share what is new
  python scripts/share_ecosystem.py --dry-run   # show the posts without sending them
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.parse
import urllib.request

import yaml

sys.path.insert(0, os.path.dirname(__file__))
import social  # noqa: E402

FEED = os.environ.get("ECOSYSTEM_FEED", "https://agentstructure.ai/api/blog/feed")
LOG = social.SOCIAL / "agentstructure.json"


def fetch_feed() -> list[dict]:
    req = urllib.request.Request(FEED, headers={"User-Agent": social.UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())["posts"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    channels, buffer = [], None
    key = os.environ.get("BUFFER_API_KEY", "").strip()
    if key:
        buffer = social.Buffer(key)
        channels += [c for c in buffer.channels()
                     if not c.get("isQueuePaused") and str(c.get("service", "")).lower() not in social.MEDIA_ONLY]
    clients = {}
    for c, client in social.direct_accounts():
        channels.append({**c, "direct": True})
        clients[c["id"]] = client
    if not channels:
        print("::notice title=social::No social accounts are set up, so nothing was shared")
        return 0

    config = yaml.safe_load((social.ROOT / "social.yaml").read_text())
    skip = {str(k).lower().lstrip("@") for k in config.get("ecosystem_skip") or []}
    channels = [c for c in channels if not skip & {str(c.get(k) or "").lower().lstrip("@")
                                                   for k in ("name", "displayName", "service")}]

    now = dt.datetime.now(dt.UTC)
    social.SOCIAL.mkdir(exist_ok=True)
    log = json.loads(LOG.read_text()) if LOG.exists() else {}
    failed, n = False, 0
    for post in reversed(fetch_feed()):  # oldest first
        published = dt.datetime.fromisoformat(post["date"]).replace(tzinfo=dt.UTC)
        if now - published > dt.timedelta(days=2):  # the feed only has a date, so allow for the day boundary
            continue
        for c in channels:
            if c["id"] in log.get(post["slug"], {}):
                continue
            url = f"{post['url']}?" + urllib.parse.urlencode(
                {"utm_source": c["service"], "utm_medium": "social", "utm_campaign": "ecosystem"})
            blurb = post.get("hook") or post.get("description") or post["title"]
            text = social.compose(c["service"], None, blurb, "" if c.get("direct") else url)
            who = f"{c['service']} {c.get('displayName') or c['name']}"
            if args.dry_run:
                print(f"would share on {who}:\n{text}\n")
                continue
            due = now + dt.timedelta(minutes=15 + 20 * n)
            try:
                if c.get("direct"):
                    post_id = clients[c["id"]].post(text, url, post["title"], post["description"])
                else:
                    post_id = buffer.create_post(c["id"], text, due)
            except RuntimeError as e:
                failed = True
                print(f"::error title={post['slug']}::{who}: {e}")
                continue
            log.setdefault(post["slug"], {})[c["id"]] = {
                "service": c["service"], "post_id": post_id,
                "due": (now if c.get("direct") else due).isoformat(timespec="minutes")}
            LOG.write_text(json.dumps(log, indent=1) + "\n")
            print(f"shared {post['title']!r} on {who}")
            n += 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
