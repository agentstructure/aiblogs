# Daily writing routine

A Claude routine runs this every morning. It writes one new article for each blog, files it
with `scripts/posts.py`, and pushes to `main`. GitHub Actions then builds the sites and uploads
them to Hostinger. On Mondays it also writes the intro for each site's weekly roundup email.

## Steps

1. Set up: `pip install -q -r requirements.txt`, then `git pull origin main`.
2. Run `python scripts/posts.py brief`. For each site it prints the audience, today's topic
   area, whether it already has a post today, and recent titles. Skip any site that already
   posted today.
3. For each remaining site, research and write the article (rules below) and save it as a draft,
   e.g. `/tmp/drafts/<site>.md`.
4. File it: `python scripts/posts.py add <site> /tmp/drafts/<site>.md`. If it's rejected, fix
   what it says and run it again.
5. **Mondays only:** for each site with posts in the last 7 days, write
   `roundups/<site>/<today YYYY-MM-DD>.md` holding a 2 to 4 sentence intro for this week's email
   that ties the week's articles together and gives readers a reason to click. Plain and
   confident, no greeting, no sign-off, no investment advice.
6. Check the build: `python scripts/build.py --all` must finish without errors.
7. Commit only `content/` and `roundups/` with the message `Daily posts for <date>` and run
   `git push origin main`. If the push is rejected, `git pull --rebase origin main` and push again.
8. Finish with one line per site: the headline, or why that site was skipped.

If one site fails, still publish the others and say which one failed and why.

## Writing rules

- Research first. Search the web for what actually happened in the last few days in that
  site's topic area, then pick the single most timely and interesting angle that the recent
  titles haven't covered.
- Build the article on real, current, checkable facts. Never invent numbers, quotes, deals,
  tickers, prices or dates. If you can't verify something, leave it out.
- Name companies with their tickers in parentheses, e.g. Lockheed Martin (LMT).
- Link to sources inline with markdown links where you cite a fact, and list every source in
  the front matter `sources`.
- Be specific and analytical, not generic. Say why it matters to this site's audience and what
  to watch next. No filler, no hype, no "in today's fast-paced world" openings.
- Information and commentary only, never personalized investment advice. Don't tell readers to
  buy or sell anything.
- 900 to 1,400 words, a few `##` subheadings, short paragraphs. No `#` H1 in the body (the
  title is rendered separately).
- Headline under 75 characters, specific, no clickbait. Description: one sentence under 160
  characters (used for search results and the email roundup).

## Draft format

```markdown
---
title: "Pentagon's $9B Munitions Award Lifts Backlog at Lockheed Martin (LMT)"
description: "What this week's munitions contracts mean for LMT, RTX and their suppliers."
tags: ["contracts", "munitions", "LMT"]
sources:
  - title: "Contracts for Oct. 6, 2026"
    url: "https://www.defense.gov/News/Contracts/"
---
## What happened

...
```
