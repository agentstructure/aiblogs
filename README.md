# AI Blogs

Daily, Claude-written articles for four blogs, published to Hostinger by GitHub Actions, plus a
weekly email roundup for subscribers.

| Site | Folder | Secret suffix |
|---|---|---|
| beforethebreakout.com | `content/beforethebreakout/` | `BEFORETHEBREAKOUT` |
| capitalraising.org | `content/capitalraising/` | `CAPITALRAISING` |
| defensestocks.org | `content/defensestocks/` | `DEFENSESTOCKS` |
| gamingstocks.org | `content/gamingstocks/` | `GAMINGSTOCKS` |

## How it works

- **Daily posts** (`.github/workflows/daily-posts.yml`, every day at 11:15 UTC): for each site,
  Claude researches the day's news with web search on that site's topic of the day (topics
  rotate through `pillars` in `sites.yaml`), writes an article with sources, and the workflow
  commits it to `content/<site>/`. Then each site is rebuilt and uploaded.
- **Deploy** (`.github/workflows/deploy.yml`): builds each site to static HTML
  (`scripts/build.py`) and uploads it to Hostinger over FTP. It also runs whenever you edit
  content or templates on `main`, so fixing a typo in a post republishes it.
- **Subscribers**: every page has a signup form that posts to `subscribe.php` on the site,
  which adds the email to that site's list in [Brevo](https://www.brevo.com). Lists are created
  automatically, one per site, in a Brevo folder called "AI Blogs".
- **Weekly roundup** (`.github/workflows/weekly-roundup.yml`, Mondays 13:00 UTC): for each site
  with new posts in the last 7 days, Claude writes a short intro and the workflow sends a Brevo
  campaign to that site's list. Run it by hand with "dry run" checked to preview the emails as a
  downloadable artifact.

If one site fails, the others still publish, and the workflow run is marked failed so GitHub
emails you.

## Setup

Add these under **Settings > Secrets and variables > Actions > Secrets**:

| Secret | Where to get it |
|---|---|
| `ANTHROPIC_API_KEY` | console.anthropic.com > API keys |
| `BREVO_API_KEY` | Brevo > SMTP & API > API keys |
| `FTP_HOST_<SUFFIX>` | Hostinger hPanel > the website > Files > FTP Accounts (the FTP IP or hostname) |
| `FTP_USER_<SUFFIX>` | same page, FTP username |
| `FTP_PASS_<SUFFIX>` | same page, FTP password (reset it there if you don't have it) |

One `FTP_HOST_/FTP_USER_/FTP_PASS_` set per site, with the suffix from the table above. A site
without FTP secrets is still built, just not uploaded, and the run shows a warning.

Optional **Variables** (same page, Variables tab): `CLAUDE_MODEL` (default `claude-opus-5-5`),
`SENDER_EMAIL` (default `newsletter@<domain>`), `FTP_PROTOCOL` (`ftp` default, or `ftps`).

In Brevo, verify each sender domain (Senders, domains & dedicated IPs > Domains) so the
roundup can come from `newsletter@<domain>`. Brevo gives you DNS records to add in Hostinger.

`ftp_dir` in `sites.yaml` is the folder on the FTP account the site is uploaded to
(`public_html/` by default). Change it if a site's FTP account opens somewhere else, e.g.
`domains/example.com/public_html/`.

### First run

1. Actions > **Daily posts** > Run workflow, with count `3` to give each new site a few articles.
2. Check the sites, then let the schedule take over.
3. Actions > **Weekly roundup email** > Run workflow with dry run checked, and download the
   `roundup-emails` artifact to preview.

## Editing

- Change a site's topics, audience or colors in `sites.yaml`.
- Edit or delete a post by changing its file in `content/<site>/`; pushing to `main` redeploys.
- Templates are in `templates/`, styles in `static/style.css`.

## Local use

```sh
python -m venv .venv && .venv/bin/pip install -r requirements.txt
ANTHROPIC_API_KEY=... .venv/bin/python scripts/generate_post.py defensestocks
.venv/bin/python scripts/build.py --all   # output in dist/<site>/
```
