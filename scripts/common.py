"""Shared helpers: site config, post loading, slugs."""

from __future__ import annotations

import datetime as dt
import re
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
        site["url"] = f"https://{site['domain']}"
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
            )
        )
    posts.sort(key=lambda p: (p.date, p.slug), reverse=True)
    return posts
