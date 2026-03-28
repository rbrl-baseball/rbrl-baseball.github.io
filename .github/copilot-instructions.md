# Copilot Instructions for RBRL Website

## Hugo Conventions

- Hugo version: **0.159.1 extended**. Theme: **Ananke** (submodule in `themes/ananke/`).
- Content pages use YAML frontmatter delimited by `---`.
- Pages with custom layouts (teams, sponsors) must have `type: "page"` and `layout: "<name>"` in frontmatter. **Do not remove these fields** — the page will break.
- The homepage layout is `layouts/home.html` (not a content file). It directly embeds the GameChanger widget and standings partial.

## Content & Data

- News posts go in `content/news/` as individual `.md` files. The `_index.md` is the list page — don't touch it.
- Team data lives in `data/teams.yaml`. Each team has a `gc_team_id` from the GameChanger public API. These IDs are **not** UUIDs — they're short alphanumeric strings like `H31Y5RGs1o5n`.
- Sponsor data lives in `data/sponsors.yaml` as a top-level YAML array.
- `data/standings.json` is **auto-generated** by `scripts/update-standings.py`. Don't edit it manually.

## GameChanger Integration

- The league org ID is `fCGlFdY1Z4hj`. The scoreboard widget ID is `65041549-7a93-400a-a9ee-d67d9a3f8c9e`.
- Public API base: `https://api.team-manager.gc.com`
  - Scoreboard: `GET /public/widgets/scoreboard/{widget_id}` (no auth)
  - Team games: `GET /public/teams/{team_id}/games` (no auth, but **CORS-blocked** from browsers)
  - Org teams: `GET /public/organizations/{org_id}/teams` (no auth)
- The team schedule widget (`GC.team.schedule`) requires UUID widget IDs that are only accessible via authenticated GC endpoints. We don't use it.
- The scoreboard widget SDK is at `https://widgets.gc.com/static/js/sdk.v1.js`. It supports: `target`, `widgetId`, `layout` ("vertical"/"horizontal"), `maxVerticalGamesVisible`, `maxHorizontalGamesVisible`, `refreshDisabled`.

## Images

- News images: `static/images/news/`. The optimize-images action auto-compresses files >100KB.
- Team logos: `static/images/teams/` (SVG preferred).
- Sponsor logos: `static/images/sponsors/` (roughly 200x100px, PNG/JPG).
- The `process-news-images` action converts the first markdown image `![alt](src)` in a news post to the `{{< article-image >}}` shortcode. Posts that already have the shortcode are skipped.

## Pages CMS

- Config is in `.pages.yml`. All page frontmatter fields except `body` are marked `hidden: true` to prevent CMS editors from accidentally stripping them.
- News posts have visible fields: title, date, description, author, body.
- Media sources route uploads to the correct `static/images/` subdirectory.

## CSS

- Custom styles are in `static/css/custom.css`. Brand colors are CSS variables:
  - `--rbrl-blue: #284090`
  - `--rbrl-blue-dark: #1e3070`
  - `--rbrl-blue-light: #3a52a8`
  - `--rbrl-red: #e03038`
- `.bg-dark-blue` is overridden to use `--rbrl-blue`.
- Header heading/subheading font weights are overridden from the Tachyons defaults (200/100) to 400 for readability.

## GitHub Actions

- `hugo.yml` deploys on every push to `main`. Uses `actions/configure-pages@v5` (v6 tag not yet published).
- `update-standings.yml` uses `[skip ci]` — **do not add** `[skip ci]` to this workflow. It needs the hugo deploy to trigger after it commits.
  - Wait, actually it does NOT use `[skip ci]`. The standings commit triggers a redeploy intentionally.
- `process-news-images.yml` and `optimize-images.yml` **do** use `[skip ci]` to avoid infinite loops.

## Standings

- Points system: 2 for win, 1 for tie, 0 for loss. Sorted by points, then wins, then fewest losses.
- The standings script stores per-game results (`games` array in standings.json) for future tiebreaker support (head-to-head, intra-division record).
- The script maps GC team names (which may differ, e.g., "RBRL Padres", "A's", "Mariners - RBRL") to canonical names via `gc_team_id` lookup against `data/teams.yaml`.
