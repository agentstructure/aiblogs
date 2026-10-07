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

- **Daily posts** (a Claude routine in the AI BLOGS project, every day at 7:15am Eastern): a
  Claude session follows [WRITING.md](WRITING.md). For each site it researches the day's news
  on that site's topic of the day (topics rotate through `pillars` in `sites.yaml`), writes a
  sourced article, files it with `scripts/posts.py`, and pushes to `main`. This runs on Sean's
  Claude plan, so there is no API key or API bill.
- **Deploy** (`.github/workflows/deploy.yml`): runs on every push that changes content or
  templates. It builds each site to static HTML (`scripts/build.py`) and uploads it to
  Hostinger over FTP. Fixing a typo in a post and pushing republishes it.
- **Subscribers**: every page has a signup form that posts to `subscribe.php` on the site,
  which adds the email to that site's list in [Brevo](https://www.brevo.com). Lists are created
  automatically, one per site, in a Brevo folder called "AI Blogs".
- **Weekly roundup** (`.github/workflows/weekly-roundup.yml`, Mondays 13:00 UTC): for each site
  with new posts in the last 7 days, sends a Brevo campaign to that site's list. The intro
  comes from `roundups/<site>/<date>.md`, which the Monday routine writes. Run it by hand with
  "dry run" checked to preview the emails as a downloadable artifact.

If one site's upload fails, the others still publish, and the run is marked failed so GitHub
emails you.

## Setup

Add these under **Settings > Secrets and variables > Actions > Secrets**:

| Secret | Where to get it |
|---|---|
| `BREVO_API_KEY` | Brevo > SMTP & API > API keys |
| `FTP_HOST_<SUFFIX>` | Hostinger hPanel > the website > Files > FTP Accounts (the FTP IP or hostname) |
| `FTP_USER_<SUFFIX>` | same page, FTP username |
| `FTP_PASS_<SUFFIX>` | same page, FTP password (reset it there if you don't have it) |

One `FTP_HOST_/FTP_USER_/FTP_PASS_` set per site, with the suffix from the table above. A site
without FTP secrets is still built, just not uploaded, and the run shows a warning.

Optional **Variables** (same page, Variables tab): `SENDER_EMAIL` (default `newsletter@<domain>`), `FTP_PROTOCOL` (`ftp` default, or `ftps`).

In Brevo, verify each sender domain (Senders, domains & dedicated IPs > Domains) so the
roundup can come from `newsletter@<domain>`. Brevo gives you DNS records to add in Hostinger.

`ftp_dir` in `sites.yaml` is the folder on the FTP account the site is uploaded to
(`public_html/` by default). Change it if a site's FTP account opens somewhere else, e.g.
`domains/example.com/public_html/`.

### First run

1. Add the secrets above, then run Actions > **Deploy sites** once to upload the empty sites.
2. The routine posts every morning. To post right away, run the routine now from the project.
3. Actions > **Weekly roundup email** > Run workflow with dry run checked, and download the
   `roundup-emails` artifact to preview.

## Editing

- Change a site's topics, audience or colors in `sites.yaml`.
- Edit or delete a post by changing its file in `content/<site>/`; pushing to `main` redeploys.
- Templates are in `templates/`, styles in `static/style.css`.

## Local use

```sh
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/posts.py brief                       # today's topics
.venv/bin/python scripts/posts.py add defensestocks draft.md  # check and file a draft
.venv/bin/python scripts/build.py --all                       # output in dist/<site>/
```
