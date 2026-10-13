"""Publish new posts to each live site through the same endpoint Make used.

Each site already has a PHP endpoint that turns an HTML article into a post on its blog.
This sends every post in content/<site>/ that isn't in published/<site>.json yet, then
records it there so nothing is posted twice.

  python scripts/publish.py            # publish everything new
  python scripts/publish.py --dry-run  # show what would be sent

Sites whose endpoint needs a key (defensestocks, beforethebreakout) get it at run time from
the endpoint's own code through the Hostinger API (HOSTINGER_API_TOKEN), so there is no
extra secret to manage. Keys are masked in the Actions log and never printed.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sys
import urllib.error
import urllib.request

from common import ROOT, load_posts, load_sites

PUBLISHED = ROOT / "published"
MAX_AGE_DAYS = 10  # older unpublished posts are left alone rather than backfilled (raised while Actions was blocked)
UA = "aiblogs/1.0 (+https://github.com/agentstructure/aiblogs)"

# How each site takes a post. `secret_from` is the endpoint file holding its key.
TARGETS = {
    "defensestocks": {"url": "https://defensestocks.org/save-post.php",
                      "secret_from": ("defensestocks.org", "save-post.php"), "style": "content"},
    "capitalraising": {"url": "https://capitalraising.org/save-post.php", "style": "content+fields"},
    "gamingstocks": {"url": "https://gamingstocks.org/publish.php", "style": "fields"},
    "beforethebreakout": {"url": "https://beforethebreakout.net/api/daily-article.php",
                          "secret_from": ("beforethebreakout.net", "api/daily-article.php"),
                          "style": "content"},
}


def article_html(post, site: dict) -> str:
    sources = "".join(
        f'<li><a href="{html.escape(s["url"])}" rel="noopener" target="_blank">{html.escape(s.get("title") or s["url"])}</a></li>'
        for s in post.sources)
    out = f"<h1>{html.escape(post.title, quote=False)}</h1>\n{post.body_html}"
    if sources:
        out += f"\n<h2>Sources</h2>\n<ul>{sources}</ul>"
    return out


def payload(post, site: dict, style: str) -> dict:
    content = article_html(post, site)
    if style == "content":  # the endpoint takes the title from the <h1>
        return {"content": content}
    body = content.split("\n", 1)[1]  # title goes in its own field, so drop the <h1>
    fields = {"title": post.title, "content": body, "excerpt": post.description, "slug": post.slug,
              "tags": post.tags, "meta_description": post.description}
    if style == "content+fields":  # capitalraising
        return {**fields, "date": post.date.isoformat()}
    # gamingstocks publish.php also requires category and author
    return {**fields, "category": (post.tags or ["Analysis"])[0].title(), "author": f"{site['name']} Research"}


def endpoint_key(domain: str, path: str) -> tuple[str, str]:
    """(header name, key) the endpoint checks, read from its own code."""
    from hostinger import Hostinger
    h = Hostinger()
    code = h.read_file(h.username_for(domain), domain, path)
    key = re.search(r"\$expectedSecret\s*=\s*'([^']+)'", code)
    header = re.search(r"\$_SERVER\['HTTP_([A-Z0-9_]+)'\]", code)
    if not key or not header:
        raise SystemExit(f"{domain}/{path}: could not find the key the endpoint expects")
    print(f"::add-mask::{key.group(1)}")
    name = "-".join(p.capitalize() for p in header.group(1).split("_"))
    return name, key.group(1)


def send(url: str, data: dict, headers: dict) -> tuple[int, dict | str]:
    req = urllib.request.Request(url, data=json.dumps(data).encode(), method="POST", headers={
        "Content-Type": "application/json", "Accept": "application/json", "User-Agent": UA, **headers})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            status, body = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, body = e.code, e.read()
    try:
        return status, json.loads(body)
    except ValueError:
        return status, body.decode(errors="replace")[:200]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("sites", nargs="*")
    args = ap.parse_args()
    today = dt.date.today()
    failed = False
    PUBLISHED.mkdir(exist_ok=True)

    for slug, site in load_sites().items():
        if args.sites and slug not in args.sites:
            continue
        target = TARGETS[slug]
        log_file = PUBLISHED / f"{slug}.json"
        log = json.loads(log_file.read_text()) if log_file.exists() else {}
        todo = [p for p in reversed(load_posts(slug))  # oldest first
                if p.slug not in log and (today - p.date).days <= MAX_AGE_DAYS]
        if not todo:
            print(f"[{slug}] nothing new")
            continue
        headers = {}
        if target.get("secret_from") and not args.dry_run:
            name, key = endpoint_key(*target["secret_from"])
            headers[name] = key
        for post in todo:
            data = payload(post, site, target["style"])
            if args.dry_run:
                print(f"[{slug}] would POST {post.title!r} to {target['url']} ({len(json.dumps(data))} bytes)")
                continue
            status, res = send(target["url"], data, headers)
            ok = 200 <= status < 300 and isinstance(res, dict) and (res.get("ok") or res.get("success"))
            if ok:
                url = res.get("url") or (res.get("article") or {}).get("url") or res.get("slug") or ""
                log[post.slug] = {"published_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                                  "title": post.title, "result": url}
                log_file.write_text(json.dumps(log, indent=1) + "\n")
                print(f"[{slug}] published {post.title!r} {url}")
            else:
                failed = True
                print(f"::error title={slug}::publish failed (HTTP {status}): {str(res)[:200]}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "scripts"))
    sys.exit(main())
