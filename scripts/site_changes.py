"""One-time changes to the live sites that Sean approved on 2026-10-07 ("yes all").

  python scripts/site_changes.py block-subscribers   # defensestocks: hide subscribers.json
  python scripts/site_changes.py gamingstocks-blog   # show published posts on gamingstocks' blog
  python scripts/site_changes.py check               # HTTP status of the pages that matter

Fixes from the 2026-10-07 site check that Sean approved ("Fix all"):
  fix-gs-subscribe    gamingstocks: subscribe.php had a PHP parse error, so every signup failed
  fix-gs-home         gamingstocks: homepage signup script crashed when a form was missing
  fix-gs-placeholders gamingstocks: blog shows only real posts, not the 12 sample cards
  fix-cr-quotes       capitalraising: article pages saved with \\" instead of "
  fix-ds-sec          defensestocks: SEC filings box fetches through sec-proxy.php (SEC blocks browsers)
  check-signups       POST an invalid address to every signup endpoint (expect 400/422)

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
GS_MARKER_V2 = "<!-- aiblogs: published posts v2 -->"
GS_SCRIPT = GS_MARKER_V2 + """
<script>
// Shows only the posts sent to publish.php (the sample news and research cards are hidden)
// and opens them on post.php.
(function () {
  if (typeof researchArticles === 'undefined' || typeof renderArticles !== 'function') return;
  var tmp = document.createElement('textarea');
  function decode(s) { tmp.innerHTML = s || ''; return tmp.value; }
  var news = document.getElementById('newsContainer');
  var newsSection = news && news.closest('.news-section');
  if (newsSection) newsSection.style.display = 'none';
  document.querySelectorAll('[onclick*="filterCategory"]').forEach(function (b) {
    if (b.parentElement) b.parentElement.style.display = 'none';
  });
  researchArticles.length = 0;
  renderArticles();
  var grid = document.getElementById('articlesContainer');
  if (grid) grid.innerHTML = '<p style="opacity:.7">Loading research...</p>';
  fetch('/publish.php', {cache: 'no-store'}).then(function (r) { return r.json(); }).then(function (d) {
    var posts = (d && d.articles) || [];
    posts.forEach(function (a) {
      researchArticles.push({
        title: decode(a.title).replace(/'/g, '\\u2019').replace(/"/g, '\\u201d'),
        description: decode(a.excerpt),
        date: String(a.published_at || '').slice(0, 10),
        category: 'latest', icon: '\\ud83d\\udcf0', slug: a.slug
      });
    });
    renderArticles();
    if (!posts.length && grid) grid.innerHTML = '<p style="opacity:.7">New research is on the way.</p>';
  }).catch(function () {
    if (grid) grid.innerHTML = '<p style="opacity:.7">New research is on the way.</p>';
  });
  window.openArticle = function (title) {
    for (var i = 0; i < researchArticles.length; i++) {
      var a = researchArticles[i];
      if (a.slug && a.title === title) { location.href = '/post.php?slug=' + encodeURIComponent(a.slug); return; }
    }
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
    if GS_MARKER_V2 in blog:
        print("gamingstocks: blog.html already shows published posts")
        return
    if "</body>" not in blog or "researchArticles" not in blog:
        raise SystemExit("gamingstocks: blog.html is not shaped as expected; left unchanged")
    backup = f"blog.backup-{STAMP}{'b' if GS_MARKER in blog else ''}.html"
    h.upload(user, domain, blog.encode(), backup)
    if GS_MARKER in blog:  # replace the first version of the script
        a = blog.index(GS_MARKER)
        b = blog.index("</script>", a) + len("</script>")
        blog = blog[:a].rstrip("\n") + "\n" + blog[b:].lstrip("\n")
    i = blog.rfind("</body>")
    h.upload(user, domain, (blog[:i] + GS_SCRIPT + blog[i:]).encode(), "blog.html")
    print(f"gamingstocks: blog.html now lists only published posts (backup saved as {backup})")


def fix_gs_placeholders(h: Hostinger):
    gamingstocks_blog(h)


def replace_once(h: Hostinger, domain: str, path: str, old: str, new: str, backup: str, done_if: str) -> None:
    user = h.username_for(domain)
    text = h.read_file(user, domain, path)
    if done_if in text:
        print(f"{domain}/{path}: already fixed")
        return
    if text.count(old) != 1:
        raise SystemExit(f"{domain}/{path}: expected the text to fix once, found {text.count(old)}; left unchanged")
    h.upload(user, domain, text.encode(), backup)
    h.upload(user, domain, text.replace(old, new).encode(), path)
    print(f"{domain}/{path}: fixed (backup saved as {backup})")


def fix_gs_subscribe(h: Hostinger):
    # A ternary inside a heredoc is a PHP parse error, so subscribe.php answered every request with HTTP 500.
    user = h.username_for("gamingstocks.org")
    text = h.read_file(user, "gamingstocks.org", "subscribe.php")
    if "$greetName" in text:
        print("gamingstocks.org/subscribe.php: already fixed")
        return
    bad = "Hello{$name ? ' ' . htmlspecialchars($name) : ''}!"
    head = "function sendWelcomeEmail($email, $name) {"
    if text.count(bad) != 1 or text.count(head) != 1:
        raise SystemExit("gamingstocks.org/subscribe.php: not shaped as expected; left unchanged")
    h.upload(user, "gamingstocks.org", text.encode(), f"subscribe.backup-{STAMP}.php")
    text = text.replace(bad, "Hello{$greetName}!").replace(
        head, head + "\n    $greetName = $name ? ' ' . htmlspecialchars($name) : '';")
    h.upload(user, "gamingstocks.org", text.encode(), "subscribe.php")
    print(f"gamingstocks.org/subscribe.php: fixed (backup saved as subscribe.backup-{STAMP}.php)")


def fix_gs_home(h: Hostinger):
    # handleEmailSubmit('ctaForm', ...) runs on a page without that form and crashed the script.
    replace_once(h, "gamingstocks.org", "index.html",
                 "const btn = document.getElementById(btnId);",
                 "const btn = document.getElementById(btnId);\n            if (!form || !btn) return;",
                 f"index.backup-{STAMP}.html", "if (!form || !btn) return;")


def fix_cr_quotes(h: Hostinger):
    domain = "capitalraising.org"
    user = h.username_for(domain)
    pages = [e["path"].lstrip("/") for e in h.list_files(user, domain)
             if e["type"] == "file" and e["path"].lstrip("/").startswith("articles/")
             and e["path"].endswith(".html") and ".backup-" not in e["path"]]
    fixed = 0
    for path in pages:
        text = h.read_file(user, domain, path)
        if '\\"' not in text:
            continue
        h.upload(user, domain, text.encode(), path.replace(".html", f".backup-{STAMP}.html.txt"))
        h.upload(user, domain, text.replace('\\"', '"').encode(), path)
        fixed += 1
        print(f"capitalraising: fixed {path} ({text.count(chr(92) + chr(34))} escaped quotes)")
    print(f"capitalraising: {len(pages)} article pages checked, {fixed} fixed")


SEC_PROXY_PHP = r"""<?php
// aiblogs: SEC EDGAR blocks browser requests (no CORS), so the filings box asks this page instead.
// Returns https://data.sec.gov/submissions/CIK##########.json, cached for an hour.
header('Content-Type: application/json');
header('Cache-Control: public, max-age=900');
$cik = str_pad(substr(preg_replace('/\D/', '', $_GET['cik'] ?? ''), 0, 10), 10, '0', STR_PAD_LEFT);
if ($cik === '0000000000') { http_response_code(400); echo '{"error":"cik required"}'; exit; }
$cacheDir = sys_get_temp_dir() . '/sec-cache';
@mkdir($cacheDir, 0700, true);
$cache = "$cacheDir/$cik.json";
if (is_file($cache) && time() - filemtime($cache) < 3600) { readfile($cache); exit; }
$url = "https://data.sec.gov/submissions/CIK$cik.json";
$ua = 'DefenseStocks.org admin@defensestocks.org';
$body = false; $code = 0;
if (function_exists('curl_init')) {
    $ch = curl_init($url);
    curl_setopt_array($ch, [CURLOPT_RETURNTRANSFER => true, CURLOPT_TIMEOUT => 20, CURLOPT_ENCODING => '',
                            CURLOPT_HTTPHEADER => ["User-Agent: $ua", 'Accept: application/json']]);
    $body = curl_exec($ch);
    $code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
} else {
    $body = @file_get_contents($url, false, stream_context_create(['http' => ['header' => "User-Agent: $ua\r\n", 'timeout' => 20]]));
    $code = $body === false ? 502 : 200;
}
if ($body === false || $code !== 200) { http_response_code($code ?: 502); echo '{"error":"SEC unavailable"}'; exit; }
@file_put_contents($cache, $body);
echo $body;
"""


def fix_ds_sec(h: Hostinger):
    domain = "defensestocks.org"
    user = h.username_for(domain)
    h.upload(user, domain, SEC_PROXY_PHP.encode(), "sec-proxy.php")
    print("defensestocks: sec-proxy.php uploaded")
    text = h.read_file(user, domain, "index.html")
    old = "https://data.sec.gov/submissions/CIK"
    if old not in text:
        print("defensestocks/index.html: already uses sec-proxy.php" if "sec-proxy.php" in text
              else "defensestocks/index.html: SEC URL not found; left unchanged")
        return
    h.upload(user, domain, text.encode(), f"index.backup-{STAMP}.html")
    text = text.replace(old, "/sec-proxy.php?cik=")
    h.upload(user, domain, text.encode(), "index.html")
    for n, line in enumerate(text.splitlines(), 1):
        if "sec-proxy.php" in line or "data.sec.gov" in line:
            print(f"  {n}: {line.strip()[:200]}")
    print(f"defensestocks: index.html now fetches filings through sec-proxy.php (backup saved as index.backup-{STAMP}.html)")


def status(url: str) -> int:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Cache-Control": "no-cache"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def check_signups(_h=None):
    for url in ["https://gamingstocks.org/subscribe.php", "https://defensestocks.org/subscribers-api.php",
                "https://capitalraising.org/subscribe.php", "https://beforethebreakout.net/subscribers-api.php",
                "https://beforethebreakout.net/api/subscribe.php"]:
        req = urllib.request.Request(url, data=b'{"email":"not-an-email"}', method="POST",
                                     headers={"User-Agent": UA, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                code = r.status
        except urllib.error.HTTPError as e:
            code = e.code
        print(f"{code}  POST {url}  ({'ok' if code in (400, 422) else 'CHECK'})")
    sec = "https://defensestocks.org/sec-proxy.php?cik=0000936468"  # Lockheed Martin
    print(f"{status(sec)}  {sec}")


def check(_h=None):
    for url in ["https://defensestocks.org/", "https://defensestocks.org/blog.html",
                "https://defensestocks.org/daily-articles.json", "https://defensestocks.org/subscribers.json",
                "https://gamingstocks.org/blog.html", "https://gamingstocks.org/publish.php",
                "https://gamingstocks.org/post.php?slug=none",
                "https://capitalraising.org/", "https://beforethebreakout.net/blog.php"]:
        print(f"{status(url)}  {url}")


if __name__ == "__main__":
    steps = {"block-subscribers": block_subscribers, "gamingstocks-blog": gamingstocks_blog, "check": check,
             "fix-gs-subscribe": fix_gs_subscribe, "fix-gs-home": fix_gs_home,
             "fix-gs-placeholders": fix_gs_placeholders, "fix-cr-quotes": fix_cr_quotes,
             "fix-ds-sec": fix_ds_sec, "check-signups": check_signups}
    for name in sys.argv[1:] or ["check"]:
        steps[name](Hostinger() if not name.startswith("check") else None)
