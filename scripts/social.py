"""Share each newly published article on social media through Buffer.

Runs after scripts/publish.py. Every post in published/<site>.json from the last day
that isn't in social/<site>.json yet is scheduled on each Buffer channel social.yaml assigns
to that site, then recorded there so it is never shared twice.

  python scripts/social.py             # schedule everything new
  python scripts/social.py --dry-run   # show the posts without sending them
  python scripts/social.py --channels  # list the connected Buffer channels

Accounts: everything connected in Buffer (BUFFER_API_KEY, from Buffer > Settings > API), plus
accounts posted to directly for free, which keeps Buffer's free-plan slots for other networks:
Bluesky (BLUESKY_HANDLE + BLUESKY_APP_PASSWORD), a Telegram channel (TELEGRAM_BOT_TOKEN of a
bot that is admin there + TELEGRAM_CHAT, e.g. @AgentStructure) and Discord (DISCORD_WEBHOOK_URL).
Buffer holds each post until its slot; direct posts go out on the first run after the slot (the Share on social media workflow runs every
30 minutes). With neither set this prints a notice and exits.
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

# Networks that need a video or image on every post, so the daily text posts skip them.
MEDIA_ONLY = {"youtube", "tiktok", "instagram", "pinterest"}

# Characters each network allows, and how many a link uses (Buffer's character-limits guide).
LIMITS = {"telegram": (4000, None), "discord": (1900, None), "bluesky": (300, "host+16"), "twitter": (280, 23), "threads": (500, None),
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


class Bluesky:
    """Posts straight to a Bluesky account (free, no limits) with an app password."""
    HOST = "https://bsky.social/xrpc"

    def __init__(self, handle: str, password: str):
        self.handle, self.password, self.session = handle.lstrip("@"), password, None

    @classmethod
    def from_env(cls) -> "Bluesky | None":
        handle = os.environ.get("BLUESKY_HANDLE", "").strip()
        password = os.environ.get("BLUESKY_APP_PASSWORD", "").strip()
        return cls(handle, password) if handle and password else None

    def call(self, method: str, body: dict, auth: bool = True) -> dict:
        headers = {"Content-Type": "application/json", "User-Agent": UA}
        if auth:
            headers["Authorization"] = f"Bearer {self.login()['accessJwt']}"
        req = urllib.request.Request(f"{self.HOST}/{method}", method="POST",
                                     data=json.dumps(body).encode(), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Bluesky HTTP {e.code}: {e.read().decode(errors='replace')[:300]}") from None

    def login(self) -> dict:
        if not self.session:
            self.session = self.call("com.atproto.server.createSession",
                                     {"identifier": self.handle, "password": self.password}, auth=False)
        return self.session

    def post(self, text: str, url: str, title: str, description: str) -> str:
        record = {"$type": "app.bsky.feed.post", "text": text,
                  "createdAt": dt.datetime.now(dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
                  "embed": {"$type": "app.bsky.embed.external",
                            "external": {"uri": url, "title": title, "description": description}}}
        res = self.call("com.atproto.repo.createRecord",
                        {"repo": self.login()["did"], "collection": "app.bsky.feed.post", "record": record})
        return res["uri"]


class Telegram:
    """Posts to a Telegram channel through a bot that is an admin there (free)."""

    def __init__(self, token: str, chat: str):
        self.token, self.chat = token, chat

    def post(self, text: str, url: str, title: str, description: str) -> str:
        body = {"chat_id": self.chat, "text": f"{text}\n\n{url}"}
        res = _post_json(f"https://api.telegram.org/bot{self.token}/sendMessage", body, "Telegram")
        if not res.get("ok"):
            raise RuntimeError(f"Telegram: {res.get('description')}")
        return str(res["result"]["message_id"])


class Discord:
    """Posts to a Discord channel through its webhook URL (free)."""

    def __init__(self, webhook: str):
        self.webhook = webhook

    def post(self, text: str, url: str, title: str, description: str) -> str:
        res = _post_json(self.webhook + "?wait=true", {"content": f"{text}\n{url}"}, "Discord")
        return str(res.get("id", ""))


def _post_json(url: str, body: dict, name: str) -> dict:
    req = urllib.request.Request(url, method="POST", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{name} HTTP {e.code}: {e.read().decode(errors='replace')[:300]}") from None


def direct_accounts() -> list[tuple[dict, object]]:
    """Accounts posted to without Buffer, from whichever secrets are set."""
    out = []
    sky = Bluesky.from_env()
    if sky:
        out.append(({"id": f"bluesky:{sky.handle}", "name": sky.handle, "service": "bluesky"}, sky))
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(), os.environ.get("TELEGRAM_CHAT", "").strip()
    if token and chat:
        print(f"::add-mask::{token}")
        out.append(({"id": f"telegram:{chat}", "name": chat, "service": "telegram"}, Telegram(token, chat)))
    hook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if hook:
        print(f"::add-mask::{hook}")
        out.append(({"id": "discord:webhook", "name": "Discord", "service": "discord"}, Discord(hook)))
    return out


INTROSPECT = """query($n: String!) { __type(name: $n) { name kind inputFields { name type { kind name ofType
  { kind name ofType { kind name } } } } enumValues { name } } }"""


def describe(buffer: Buffer, names: list[str]) -> None:
    """Print Buffer input types, e.g. PostInputMetaData, to see what a network needs."""
    for n in names:
        t = buffer.query(INTROSPECT, {"n": n})["__type"]
        if not t:
            print(f"{n}: not found")
            continue
        print(f"{n} ({t['kind']}):")
        for f in t.get("inputFields") or []:
            ty, label = f["type"], ""
            while ty:
                label += "!" if ty["kind"] == "NON_NULL" else ("[]" if ty["kind"] == "LIST" else ty["name"] or "")
                ty = ty.get("ofType")
            print(f"  {f['name']}: {label}")
        for v in t.get("enumValues") or []:
            print(f"  = {v['name']}")


def share_once(buffer: Buffer, text: str, video: str, title: str, services: list[str], metadata: dict,
               image: str = "") -> int:
    """Post one message (optionally with a video or an image) to the named Buffer networks, 5 minutes from now."""
    due = dt.datetime.now(dt.UTC) + dt.timedelta(minutes=5)
    failed = 0
    for c in buffer.channels():
        if services and c["service"].lower() not in services:
            continue
        inp = {"channelId": c["id"], "text": text, "schedulingType": "automatic", "mode": "customScheduled",
               "dueAt": due.isoformat(timespec="seconds").replace("+00:00", "Z")}
        if video:
            inp["assets"] = [{"video": {"url": video}}]
        elif image:
            inp["assets"] = [{"image": {"url": image}}]
        meta = metadata.get(c["service"].lower())
        if meta:
            inp["metadata"] = {c["service"].lower(): {k: (title if v == "$title" else v) for k, v in meta.items()}}
        data = buffer.query(
            "mutation($input: CreatePostInput!) { createPost(input: $input) {"
            " ... on PostActionSuccess { post { id dueAt } } ... on MutationError { message } } }", {"input": inp})
        res = data["createPost"]
        if "post" in res:
            print(f"{c['service']} {c.get('displayName') or c['name']}: scheduled {res['post']['id']} for {res['post']['dueAt']}")
        else:
            failed = 1
            print(f"::error title={c['service']}::{res.get('message')}")
    return failed


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
    room = limit - len(prefix) - (2 + (link_len or len(url)) if url else 0)
    if len(blurb) > room:
        blurb = blurb[:max(room - 1, 0)].rsplit(" ", 1)[0] + "…"
    return f"{prefix}{blurb}\n\n{url}" if url else f"{prefix}{blurb}"


def slot_time(site_slug: str, slots: dict, now: dt.datetime) -> dt.datetime:
    hh, mm = map(int, str(slots.get(site_slug, "12:00")).split(":"))
    return now.astimezone(ET).replace(hour=hh, minute=mm, second=0, microsecond=0)


def slot(site_slug: str, slots: dict, now: dt.datetime, index: int) -> dt.datetime:
    due = slot_time(site_slug, slots, now)
    soonest = now + dt.timedelta(minutes=15 + 20 * index)  # Buffer needs a time in the future
    return due if due > soonest else soonest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--channels", action="store_true")
    ap.add_argument("--describe", nargs="+", metavar="TYPE", help="print Buffer input types")
    ap.add_argument("--once", metavar="TEXT", help="post this text once instead of the daily posts")
    ap.add_argument("--video", default="", help="public video URL for --once")
    ap.add_argument("--image", default="", help="public image URL for --once")
    ap.add_argument("--title", default="", help="video title for --once (YouTube)")
    ap.add_argument("--services", default="", help="comma list for --once, e.g. twitter,linkedin,youtube")
    ap.add_argument("--metadata", default="{}", help='JSON per network for --once; "$title" is replaced')
    args = ap.parse_args()
    if args.describe or args.once:
        key = os.environ.get("BUFFER_API_KEY", "").strip()
        if not key:
            raise SystemExit("BUFFER_API_KEY is not set")
        if args.describe:
            describe(Buffer(key), args.describe)
            return 0
        services = [x.strip().lower() for x in args.services.split(",") if x.strip()]
        return share_once(Buffer(key), args.once, args.video, args.title, services, json.loads(args.metadata),
                          args.image)

    if not (yaml.safe_load((ROOT / "social.yaml").read_text()) or {}).get("enabled", True):
        print("::notice title=social::Social sharing is off (enabled: false in social.yaml), so nothing was shared")
        return 0

    channels, buffer = [], None
    key = os.environ.get("BUFFER_API_KEY", "").strip()
    if key:
        buffer = Buffer(key)
        channels += [c for c in buffer.channels()
                     if not c.get("isQueuePaused") and str(c.get("service", "")).lower() not in MEDIA_ONLY]
    clients = {}
    for c, client in direct_accounts():
        channels.append({**c, "direct": True})
        clients[c["id"]] = client
    if args.channels or not channels:
        for c in channels:
            print(f"{c['service']}: {c.get('displayName') or c['name']} ({c['id']})")
        if not channels:
            print("::notice title=social::No social accounts are set up (BUFFER_API_KEY, "
                  "BLUESKY_APP_PASSWORD, TELEGRAM_BOT_TOKEN or DISCORD_WEBHOOK_URL), so nothing was shared")
        return 0

    config = yaml.safe_load((ROOT / "social.yaml").read_text())
    mapping, slots = config.get("channels") or {}, config.get("slots_et") or {}
    skip = {str(k).lower().lstrip("@") for k in config.get("skip") or []}
    channels = [c for c in channels if not skip & {str(c.get(k) or "").lower().lstrip("@")
                                                   for k in ("name", "displayName", "service")}]
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
                # Buffer holds a post until its time; direct accounts wait for a later run
                if c.get("direct") and slot_time(slug, slots, now) > now:
                    continue
                brand = site["name"] if len(routes[c["id"]]) > 1 else None
                url = live_url(slug, site, post, f"utm_source={c['service']}&utm_medium=social&utm_campaign=daily")
                blurb = post.social or post.description or post.title
                who = f"{c['service']} {c.get('displayName') or c['name']}"
                when = "now" if c.get("direct") else f"at {due.astimezone(ET):%H:%M} ET"
                if c.get("direct"):
                    text = compose(c["service"], brand, blurb, "")  # each client adds the link itself
                else:
                    text = compose(c["service"], brand, blurb, url)
                if args.dry_run:
                    print(f"[{slug}] would share on {who} {when}:\n{text}\n")
                    continue
                try:
                    if c.get("direct"):
                        post_id = clients[c["id"]].post(text, url, post.title, post.description)
                    else:
                        post_id = buffer.create_post(c["id"], text, due)
                except RuntimeError as e:
                    failed = True
                    print(f"::error title={slug}::{who}: {e}")
                    continue
                log.setdefault(post.slug, {})[c["id"]] = {
                    "service": c["service"], "post_id": post_id,
                    "due": (now if c.get("direct") else due).isoformat(timespec="minutes")}
                log_file.write_text(json.dumps(log, indent=1) + "\n")
                print(f"[{slug}] shared {post.title!r} on {who} {when}")
            n += 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "scripts"))
    sys.exit(main())
