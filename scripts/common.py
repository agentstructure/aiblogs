"""Shared helpers: site config, post loading, slugs."""

from __future__ import annotations

import datetime as dt
import json
import re
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path

import markdown
import yaml

ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = ROOT / "content"


def load_sites() -> dict[str, dict]:
    with open(ROOT / "sites.yaml") as f:
        sites = yaml.safe_load(f)
    for slug, site in sites.items():
        site["slug"] = slug
        site["base"] = (site.get("base_path") or "").rstrip("/")  # e.g. "/blog"
        site["home"] = f"https://{site['domain']}"
        site["url"] = site["home"] + site["base"]
    return sites


def get_site(slug: str) -> dict:
    sites = load_sites()
    if slug not in sites:
        raise SystemExit(f"Unknown site '{slug}'. Known: {', '.join(sites)}")
    return sites[slug]


def slugify(text: str, max_len: int = 80) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return text[:max_len].rstrip("-") or "post"


FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", re.S)


def parse_front_matter(text: str) -> tuple[dict, str]:
    m = FRONT_MATTER.match(text.strip() + "\n")
    if not m:
        raise ValueError("missing front matter")
    meta = yaml.safe_load(m.group(1)) or {}
    return meta, m.group(2).strip() + "\n"


@dataclass
class Post:
    site: str
    slug: str
    title: str
    date: dt.date
    description: str
    body_md: str
    tags: list[str] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)
    social: str = ""  # short social-media blurb written with the post (optional)

    @property
    def path(self) -> str:
        return f"/{self.slug}/"

    @property
    def body_html(self) -> str:
        return markdown.markdown(self.body_md, extensions=["extra", "sane_lists"])

    @property
    def reading_minutes(self) -> int:
        return max(1, round(len(self.body_md.split()) / 230))


def load_posts(site_slug: str) -> list[Post]:
    """All posts for a site, newest first."""
    posts = []
    for path in sorted((CONTENT_DIR / site_slug).glob("*.md")):
        meta, body = parse_front_matter(path.read_text())
        date = meta.get("date")
        if isinstance(date, str):
            date = dt.date.fromisoformat(date)
        posts.append(
            Post(
                site=site_slug,
                slug=meta.get("slug") or path.stem[11:],
                title=meta["title"],
                date=date,
                description=meta.get("description", ""),
                body_md=body,
                tags=meta.get("tags") or [],
                sources=meta.get("sources") or [],
                social=(meta.get("social") or "").strip(),
            )
        )
    posts.sort(key=lambda p: (p.date, p.slug), reverse=True)
    return posts


def live_url(slug: str, site: dict, post, utm: str = "") -> str:
    """Where the post lives on the site, from what its endpoint answered (published/<site>.json)."""
    home = f"https://{site.get('hosting_domain') or site['domain']}"
    log_file = ROOT / "published" / f"{slug}.json"
    result = (json.loads(log_file.read_text()) if log_file.exists() else {}).get(post.slug, {}).get("result", "")
    if result.startswith("http"):
        url = result                                                    # capitalraising: full URL
    elif slug == "gamingstocks" and result:
        url = f"{home}/post.php?slug={urllib.parse.quote(result.rsplit('/', 1)[-1])}"
    elif slug == "beforethebreakout" and result:
        url = f"{home}/daily-article.php?slug={urllib.parse.quote(result)}"
    else:
        url = f"{home}/blog.html"                                       # defensestocks lists posts on one page
    return url + ("&" if "?" in url else "?") + utm if utm else url
