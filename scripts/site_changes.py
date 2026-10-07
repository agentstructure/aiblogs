"""One-time changes to the live sites that Sean approved on 2026-10-07 ("yes all").

  python scripts/site_changes.py block-subscribers   # defensestocks: hide subscribers.json
  python scripts/site_changes.py gamingstocks-blog   # show published posts on gamingstocks' blog
  python scripts/site_changes.py check               # HTTP status of the pages that matter

Every step keeps a dated copy of any file it changes next to the original, and is safe to re-run.
"""

from __future__ import annotations

import sys
import urllib.error
import urllib.request

from hostinger import Hostinger, HostingerError

STAMP = "2026-10-07"
UA = "aiblogs/1.0 (+https://github.com/agentstructure/aiblogs)"

HTACCESS_BLOCK = """
# aiblogs: subscriber list is read by subscribers-api.php only, never served directly
<Files "subscribers.json">
  <IfModule mod_authz_core.c>
    Require all denied
  </IfModule>
  <IfModule !mod_authz_core.c>
    Order allow,deny
    Deny from all
  </IfModule>
</Files>
"""

GS_MARKER = "<!-- aiblogs: published posts -->"
GS_SCRIPT = GS_MARKER + """
<script>
// Adds the posts sent to publish.php to the research grid and opens them on post.php.
(function () {
  if (typeof researchArticles === 'undefined' || typeof renderArticles !== 'function') return;
  var tmp = document.createElement('textarea');
  function decode(s) { tmp.innerHTML = s || ''; return tmp.value; }
  fetch('/publish.php', {cache: 'no-store'}).then(function (r) { return r.json(); }).then(function (d) {
    var posts = (d && d.articles) || [];
    posts.slice().reverse().forEach(function (a) {
      researchArticles.unshift({
        title: decode(a.title).replace(/'/g, '\\u2019').replace(/"/g, '\\u201d'),
        description: decode(a.excerpt),
        date: String(a.published_at || '').slice(0, 10),
        category: 'latest', icon: '\\ud83d\\udcf0', slug: a.slug
      });
    });
    if (posts.length) renderArticles();
  }).catch(function () {});
  var original = window.openArticle;
  window.openArticle = function (title) {
    for (var i = 0; i < researchArticles.length; i++) {
      var a = researchArticles[i];
      if (a.slug && a.title === title) { location.href = '/post.php?slug=' + encodeURIComponent(a.slug); return; }
    }
    if (original) original(title);
  };
})();
</script>
"""

POST_PHP = r"""<?php
// aiblogs: shows one article saved by publish.php (blog-articles/<slug>_<time>.json).
$slug = preg_replace('/[^a-z0-9\-]/', '', strtolower($_GET['slug'] ?? ''));
$article = null;
if ($slug !== '') {
    $files = glob(__DIR__ . '/blog-articles/' . $slug . '_*.json') ?: [];
    rsort($files);
    if ($files) $article = json_decode((string) file_get_contents($files[0]), true);
}
if (!$article) { http_response_code(404); }
function e($s) { return htmlspecialchars(html_entity_decode((string) $s, ENT_QUOTES, 'UTF-8'), ENT_QUOTES, 'UTF-8'); }
$title = $article ? e($article['title']) : 'Article not found';
$desc = $article ? e($article['seo']['meta_description'] ?? $article['excerpt'] ?? '') : '';
$date = $article ? date('M j, Y', strtotime($article['published_at'])) : '';
$url = 'https://gamingstocks.org/post.php?slug=' . $slug;
?><!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title><?= $title ?> | GamingStocks</title>
<meta name="description" content="<?= $desc ?>">
<link rel="canonical" href="<?= e($url) ?>">
<meta property="og:type" content="article"><meta property="og:title" content="<?= $title ?>"><meta property="og:description" content="<?= $desc ?>">
<style>
  :root { --bg:#0a0a14; --panel:#12121f; --text:#e6e6f0; --muted:#9a9ab0; --cyan:#00d9ff; --purple:#9d4edd; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--text); font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; line-height:1.7; }
  header { border-bottom:1px solid #22223a; padding:16px; }
  header a { color:var(--text); text-decoration:none; font-weight:800; font-size:20px; }
  header a span { background:linear-gradient(135deg,var(--cyan),var(--purple)); -webkit-background-clip:text; background-clip:text; color:transparent; }
  main { max-width:760px; margin:0 auto; padding:32px 16px 64px; }
  .back { color:var(--cyan); text-decoration:none; font-size:14px; }
  h1 { font-size:clamp(26px,5vw,38px); line-height:1.2; margin:16px 0 8px; }
  .meta { color:var(--muted); font-size:14px; margin-bottom:28px; }
  article h2 { margin-top:36px; font-size:22px; }
  article a { color:var(--cyan); }
  article img { max-width:100%; height:auto; }
  .note { margin-top:40px; padding:16px; background:var(--panel); border-radius:8px; color:var(--muted); font-size:13px; }
</style>
</head>
<body>
<header><a href="/">🎮 Gaming<span>Stocks</span></a></header>
<main>
  <a class="back" href="/blog.html">← All research</a>
<?php if ($article): ?>
  <h1><?= $title ?></h1>
  <div class="meta"><?= e($article['author'] ?? 'GamingStocks Research') ?> · <?= e($date) ?></div>
  <article><?= $article['content'] ?></article>
  <div class="note">For informational purposes only. Nothing here is financial advice. Always do your own research.</div>
<?php else: ?>
  <h1>Article not found</h1>
  <p>That article does not exist or may have moved.</p>
<?php endif; ?>
</main>
</body>
</html>
"""


def site(h: Hostinger, domain: str):
    return h.username_for(domain), domain


def block_subscribers(h: Hostinger):
    user, domain = site(h, "defensestocks.org")
    try:
        current = h.read_file(user, domain, ".htaccess")
    except HostingerError:
        current = ""
    if "subscribers.json" in current:
        print("defensestocks: .htaccess already blocks subscribers.json")
        return
    if current:
        h.upload(user, domain, current.encode(), f".htaccess.backup-{STAMP}")
    h.upload(user, domain, (current.rstrip() + "\n" + HTACCESS_BLOCK).lstrip().encode(), ".htaccess")
    print("defensestocks: .htaccess now blocks subscribers.json")


def gamingstocks_blog(h: Hostinger):
    user, domain = site(h, "gamingstocks.org")
    h.upload(user, domain, POST_PHP.encode(), "post.php")
    print("gamingstocks: post.php uploaded")
    blog = h.read_file(user, domain, "blog.html")
    if GS_MARKER in blog:
        print("gamingstocks: blog.html already shows published posts")
        return
    if "</body>" not in blog or "researchArticles" not in blog:
        raise SystemExit("gamingstocks: blog.html is not shaped as expected; left unchanged")
    h.upload(user, domain, blog.encode(), f"blog.backup-{STAMP}.html")
    i = blog.rfind("</body>")
    h.upload(user, domain, (blog[:i] + GS_SCRIPT + blog[i:]).encode(), "blog.html")
    print("gamingstocks: blog.html now lists published posts (backup saved as blog.backup-%s.html)" % STAMP)


def status(url: str) -> int:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Cache-Control": "no-cache"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def check(_h=None):
    for url in ["https://defensestocks.org/", "https://defensestocks.org/blog.html",
                "https://defensestocks.org/daily-articles.json", "https://defensestocks.org/subscribers.json",
                "https://gamingstocks.org/blog.html", "https://gamingstocks.org/publish.php",
                "https://gamingstocks.org/post.php?slug=none",
                "https://capitalraising.org/", "https://beforethebreakout.net/blog.php"]:
        print(f"{status(url)}  {url}")


if __name__ == "__main__":
    steps = {"block-subscribers": block_subscribers, "gamingstocks-blog": gamingstocks_blog, "check": check}
    for name in sys.argv[1:] or ["check"]:
        steps[name](Hostinger() if name != "check" else None)
