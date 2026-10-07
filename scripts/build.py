"""Build the static site for one or more blogs into dist/<site>/.

Usage: python scripts/build.py beforethebreakout ... | --all
If BREVO_API_KEY is set, the subscribe endpoint is configured with the site's list.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil

from jinja2 import Environment, FileSystemLoader, select_autoescape
import markdown

from common import ROOT, get_site, load_posts, load_sites

PER_PAGE = 20
DIST = ROOT / "dist"

env = Environment(
    loader=FileSystemLoader(ROOT / "templates"),
    autoescape=select_autoescape(["html", "xml"]),
    trim_blocks=True,
    lstrip_blocks=True,
)

ABOUT = """\
{name} publishes a new article every day on {focus}.

**Who it's for:** {audience}

Each article is researched from current news and public sources, drafted with AI assistance,
and links to its sources so you can check the facts yourself. Nothing here is investment,
legal or financial advice.

Want the week's articles in one email? Subscribe below and you'll get a short roundup every Monday.
"""

PRIVACY = """\
We collect your email address only if you subscribe to the weekly roundup. It is stored with
our email provider, Brevo, and used only to send you the roundup. Every email has an
unsubscribe link, and you can ask us to delete your address at any time.

This site does not use advertising trackers. Our host may keep standard server logs.
"""


def write(path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def build_site(site: dict) -> None:
    out = DIST / site["slug"]
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    posts = load_posts(site["slug"])
    ctx = {"site": site, "year": dt.date.today().year, "build_id": dt.datetime.now(dt.UTC).strftime("%Y%m%d%H%M")}

    # Index pages
    pages = [posts[i:i + PER_PAGE] for i in range(0, len(posts), PER_PAGE)] or [[]]
    for n, chunk in enumerate(pages, start=1):
        path = "/" if n == 1 else f"/page/{n}/"
        html = env.get_template("index.html").render(
            **ctx, posts=chunk, page=n, page_path=path,
            prev_path=None if n == 1 else ("/" if n == 2 else f"/page/{n - 1}/"),
            next_path=f"/page/{n + 1}/" if n < len(pages) else None,
        )
        write(out / path.strip("/") / "index.html", html)

    # Posts
    for i, p in enumerate(posts):
        jsonld = json.dumps({
            "@context": "https://schema.org", "@type": "BlogPosting",
            "headline": p.title, "description": p.description,
            "datePublished": p.date.isoformat(), "url": site["url"] + p.path,
            "publisher": {"@type": "Organization", "name": site["name"]},
        }).replace("</", "<\\/")
        related = [q for q in posts[max(0, i - 3):i + 4] if q is not p][:4]
        write(out / p.slug / "index.html",
              env.get_template("post.html").render(**ctx, post=p, related=related, jsonld=jsonld))

    # Static pages
    focus = "; ".join(x.split(",")[0].lower() for x in site["pillars"][:4])
    for slug, title, body in [
        ("about", f"About {site['name']}", ABOUT.format(focus=focus, **site)),
        ("privacy", "Privacy", PRIVACY),
    ]:
        write(out / slug / "index.html", env.get_template("page.html").render(
            **ctx, title=title, path=f"/{slug}/", body=markdown.markdown(body)))

    write(out / "feed.xml", env.get_template("feed.xml").render(**ctx, posts=posts[:30]))
    write(out / "sitemap.xml", env.get_template("sitemap.xml").render(**ctx, posts=posts))
    if not site["base"]:  # in a subfolder the main site owns robots.txt
        write(out / "robots.txt", f"User-agent: *\nAllow: /\nSitemap: {site['url']}/sitemap.xml\n")
    write(out / ".htaccess", f"Options -Indexes\nErrorDocument 404 {site['base']}/\n")
    shutil.copy(ROOT / "static" / "style.css", out / "style.css")
    shutil.copy(ROOT / "php" / "subscribe.php", out / "subscribe.php")

    if os.environ.get("BREVO_API_KEY"):
        from brevo import Brevo
        list_id = Brevo().ensure_list(site)
        cfg = "<?php return " + _php_array({
            "api_key": os.environ["BREVO_API_KEY"], "list_id": list_id}) + ";\n"
        write(out / "subscribe-config.php", cfg)
        print(f"[{site['slug']}] subscribe form -> Brevo list {list_id}")

    print(f"[{site['slug']}] built {len(posts)} posts into {out.relative_to(ROOT)}")


def _php_array(d: dict) -> str:
    def lit(v):
        return str(int(v)) if isinstance(v, int) else "'" + str(v).replace("\\", "\\\\").replace("'", "\\'") + "'"
    return "[" + ", ".join(f"{lit(k)} => {lit(v)}" for k, v in d.items()) + "]"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sites", nargs="*")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    slugs = list(load_sites()) if args.all else args.sites
    if not slugs:
        ap.error("name at least one site or pass --all")
    for slug in slugs:
        build_site(get_site(slug))


if __name__ == "__main__":
    main()
