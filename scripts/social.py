"""Share each newly published article on social media through Buffer.

Runs after scripts/publish.py. Every post in published/<site>.json from the last day
that isn't in social/<site>.json yet is scheduled on each Buffer channel social.yaml assigns
to that site, then recorded there so it is never shared twice.

  python scripts/social.py             # schedule everything new
  python scripts/social.py --dry-run   # show the posts without sending them
  python scripts/social.py --channels  # list the connected Buffer channels

Needs BUFFER_API_KEY (Buffer > Settings > API). Without it this prints a notice and exits.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

import yaml

from common import ROOT, live_url, load_posts, load_sites

API = "https://api.buffer.com"
UA = "aiblogs/1.0 (+https://github.com/agentstructure/aiblogs)"
SOCIAL = ROOT / "social"
PUBLISHED = ROOT / "published"
MAX_AGE = dt.timedelta(hours=20)  # one day's posts; Buffer's free plan holds 10 per channel
ET = ZoneInfo("America/New_York")

# Characters each network allows, and how many a link uses (Buffer's character-limits guide).
LIMITS = {"bluesky": (300, "host+16"), "twitter": (280, 23), "threads": (500, None),
          "mastodon": (500, 23), "linkedin": (3000, 24)}


class Buffer:
    def __init__(self, key: str):
        self.key = key

    def query(self, q: str, variables: dict | None = None) -> dict:
        req = urllib.request.Request(API, method="POST", data=json.dumps(
            {"query": q, "variables": variables or {}}).encode(), headers={
            "Authorization": f"Bearer {self.key}", "Content-Type": "application/json", "User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                res = json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Buffer HTTP {e.code}: {e.read().decode(errors='replace')[:300]}") from None
        if res.get("errors"):
            raise RuntimeError("Buffer: " + "; ".join(e.get("message", "?") for e in res["errors"]))
        return res["data"]

    def channels(self) -> list[dict]:
        orgs = self.query("query { account { organizations { id } } }")["account"]["organizations"]
        out = []
        for org in orgs:
            out += self.query(
                "query($org: OrganizationId!) { channels(input: {organizationId: $org}) "
                "{ id name displayName service isQueuePaused } }", {"org": org["id"]})["channels"]
        return out

    def create_post(self, channel_id: str, text: str, due: dt.datetime) -> str:
        data = self.query(
            "mutation($input: CreatePostInput!) { createPost(input: $input) {"
            " ... on PostActionSuccess { post { id } } ... on MutationError { message } } }",
            {"input": {"channelId": channel_id, "text": text, "schedulingType": "automatic",
                       "mode": "customScheduled",
                       "dueAt": due.astimezone(dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")}})
        res = data["createPost"]
        if "post" not in res:
            raise RuntimeError(f"Buffer refused the post: {res.get('message')}")
        return res["post"]["id"]


def sites_for(channel: dict, mapping: dict[str, list[str]]) -> list[str]:
    names = {str(channel.get(k) or "").lower().lstrip("@") for k in ("name", "displayName", "service")}
    specific = [s for key, sites in mapping.items() if key != "*" and key.lower().lstrip("@") in names
                for s in sites]
    return specific or list(mapping.get("*", []))


def compose(service: str, brand: str | None, blurb: str, url: str) -> str:
    limit, link_len = LIMITS.get(service, (500, None))
    prefix = f"{brand}: " if brand else ""
    if link_len == "host+16":  # Bluesky shows a link as its host plus 16 characters
        link_len = len(urllib.parse.urlsplit(url).hostname or "") + 16
    room = limit - len(prefix) - 2 - (link_len or len(url))
    if len(blurb) > room:
        blurb = blurb[:max(room - 1, 0)].rsplit(" ", 1)[0] + "…"
    return f"{prefix}{blurb}\n\n{url}"


def slot(site_slug: str, slots: dict, now: dt.datetime, index: int) -> dt.datetime:
    hh, mm = map(int, str(slots.get(site_slug, "12:00")).split(":"))
    due = now.astimezone(ET).replace(hour=hh, minute=mm, second=0, microsecond=0)
    soonest = now + dt.timedelta(minutes=15 + 20 * index)  # Buffer needs a time in the future
    return due if due > soonest else soonest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--channels", action="store_true")
    args = ap.parse_args()

    key = os.environ.get("BUFFER_API_KEY", "").strip()
    if not key:
        print("::notice title=social::BUFFER_API_KEY is not set, so nothing was shared on social media")
        return 0
    buffer = Buffer(key)
    channels = [c for c in buffer.channels() if not c.get("isQueuePaused")]
    if args.channels or not channels:
        for c in channels:
            print(f"{c['service']}: {c.get('displayName') or c['name']} ({c['id']})")
        if not channels:
            print("::warning title=social::No active Buffer channels are connected yet")
        return 0

    config = yaml.safe_load((ROOT / "social.yaml").read_text())
    mapping, slots = config.get("channels") or {}, config.get("slots_et") or {}
    routes = {c["id"]: sites_for(c, mapping) for c in channels}
    now = dt.datetime.now(dt.UTC)
    sites = load_sites()
    SOCIAL.mkdir(exist_ok=True)
    failed, n = False, 0

    for slug, site in sites.items():
        targets = [c for c in channels if slug in routes[c["id"]]]
        pub_file, log_file = PUBLISHED / f"{slug}.json", SOCIAL / f"{slug}.json"
        published = json.loads(pub_file.read_text()) if pub_file.exists() else {}
        log = json.loads(log_file.read_text()) if log_file.exists() else {}
        for post in reversed(load_posts(slug)):  # oldest first
            entry = published.get(post.slug)
            if not entry or now - dt.datetime.fromisoformat(entry["published_at"]) > MAX_AGE:
                continue
            due = slot(slug, slots, now, n)
            for c in targets:
                if c["id"] in log.get(post.slug, {}):
                    continue
                brand = site["name"] if len(routes[c["id"]]) > 1 else None
                url = live_url(slug, site, post, f"utm_source={c['service']}&utm_medium=social&utm_campaign=daily")
                text = compose(c["service"], brand, post.social or post.description or post.title, url)
                who = f"{c['service']} {c.get('displayName') or c['name']}"
                if args.dry_run:
                    print(f"[{slug}] would share on {who} at {due.astimezone(ET):%H:%M} ET:\n{text}\n")
                    continue
                try:
                    post_id = buffer.create_post(c["id"], text, due)
                except RuntimeError as e:
                    failed = True
                    print(f"::error title={slug}::{who}: {e}")
                    continue
                log.setdefault(post.slug, {})[c["id"]] = {
                    "service": c["service"], "post_id": post_id, "due": due.isoformat(timespec="minutes")}
                log_file.write_text(json.dumps(log, indent=1) + "\n")
                print(f"[{slug}] scheduled {post.title!r} on {who} for {due.astimezone(ET):%H:%M} ET")
            n += 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "scripts"))
    sys.exit(main())
