# Reading Babe Ruth League Website

The official website for [Reading Babe Ruth League](https://readingbaberuth.com/) — youth baseball for ages 13–15 in Reading, Massachusetts.

## Tech Stack

- **[Hugo](https://gohugo.io/)** (v0.159.1 extended) — static site generator
- **[Ananke](https://github.com/theNewDynamic/gohugo-theme-ananke)** — Hugo theme, customized with brand colors and layouts
- **[GitHub Pages](https://pages.github.com/)** — hosting, deployed automatically on push to `main`
- **[Pages CMS](https://pagescms.org/)** — content management for non-technical editors
- **[GameChanger](https://www.gc.com/)** — live scores, schedule widget, and standings data

## Site Structure

| Page | Source | Description |
|------|--------|-------------|
| Home | `layouts/home.html` | Latest news, live scoreboard, standings |
| About | `content/about/index.md` | League overview |
| Schedule | `content/schedule/index.md` | GameChanger widget embed |
| Teams | `content/teams/index.md` | Team cards linking to GC schedules (data from `data/teams.yaml`) |
| News | `content/news/*.md` | Game recaps, announcements, league history |
| Sponsors | `content/sponsors/index.md` | Sponsor grid (data from `data/sponsors.yaml`) |
| History | `content/history/index.md` | League history and championship records |

## Content Management

Board members and contributors can edit content through **[Pages CMS](https://pagescms.org/)** without needing Git knowledge:

1. Go to [pagescms.org](https://pagescms.org) and sign in with GitHub
2. Select this repository
3. Edit news posts, pages, and upload images through the visual editor

### What's editable via CMS

- **News** — Create and edit posts with a rich text editor (title, date, author, body)
- **Pages** — About, Schedule, History, Teams, Sponsors (body content only; frontmatter is protected)

### Images

Images uploaded through the CMS go to `static/images/news/`. Two GitHub Actions handle image processing automatically:

- **Optimize Images** — Compresses large images to web-friendly sizes
- **Process News Images** — Converts the first markdown image in a post to the `article-image` shortcode for proper floating layout

## Automation

### GitHub Actions

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `hugo.yml` | Push to `main` | Builds and deploys site to GitHub Pages |
| `update-standings.yml` | Daily 6am ET (Apr–Jun) + manual | Fetches game results from GameChanger API, updates `data/standings.json` |
| `process-news-images.yml` | Push to `content/news/` | Converts markdown images to `article-image` shortcodes |
| `optimize-images.yml` | Push to `static/images/news/` | Compresses images over 100KB |

### Standings

During the season (April–June), standings are computed daily from the GameChanger public API:

- `scripts/update-standings.py` fetches scores, maps teams to AL/NL divisions, and calculates W/L/T/Points
- Points: 2 for a win, 1 for a tie, 0 for a loss
- Per-game results are stored in `data/standings.json` for future tiebreaker support

The standings action can also be triggered manually via workflow_dispatch.

## Data Files

| File | Description |
|------|-------------|
| `data/teams.yaml` | Team rosters by division with names, slugs, logos, and GameChanger team IDs |
| `data/sponsors.yaml` | Sponsor list with names, URLs, and logo paths |
| `data/standings.json` | Auto-generated standings (do not edit manually) |

## Local Development

```bash
# Install Hugo: https://gohugo.io/installation/
hugo server -D
```

The site will be available at `http://localhost:1313/`.

## Custom Shortcodes

- `{{< gamechanger >}}` — Embeds the GameChanger scoreboard widget
- `{{< article-image src="/images/news/photo.jpg" alt="Description" >}}` — Floating article image
- `{{< standings >}}` — Renders the standings tables
