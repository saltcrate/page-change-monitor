# Web Page Change Monitor — a GitHub Action

**Know when a web page changed, without a database, an API key, or a SaaS subscription.**

```yaml
- uses: saltcrate/page-change-monitor@v1
  with:
    urls: |
      https://example.com/pricing
      https://example.com/status
    create-issue: "true"
```

That's the whole setup. First run records a baseline. Every run after it reports
`changed` / `unchanged` / `error` per page, prints a table in the job summary, and
(optionally) opens a single GitHub issue listing what changed.

---

## Why this one

Most "watch a page" actions make you commit a state file back into your repo or
wire up a cache. This one keeps the content hashes **on the server** (keyed by
URL), so:

- **Zero repo pollution** — no `state.json` commits, no merge conflicts, no extra permissions.
- **Nothing to bootstrap** — the first run just records the baseline.
- **Shared state** — two workflows (e.g. a daily cron and a manual run) see the same history.
- **No signup, no key** — 200 checks/hour free per IP. Attach a key only if you go past that.

Comparison normalises text (lowercase, whitespace-collapsed) so a change in
ad-view IDs, cache-busters or a rotated nonce does **not** trip the alarm. It
fires on real copy changes.

## Requirements

`runs-on: ubuntu-latest` (or any Linux runner with Python 3.9+). The action
uses only the standard library — no `pip install`, no Docker image, ~1s startup.

## Inputs

| Input | Default | Description |
|---|---|---|
| `urls` | — | Newline- or comma-separated URLs. |
| `urls-file` | — | File with one URL per line (`#` comments allowed). Ignored when `urls` is set. |
| `report-changes-only` | `false` | Print only pages that changed or failed. |
| `fail-on-change` | `false` | Exit non-zero when anything changed — use as a CI gate. |
| `create-issue` | `false` | Open/update an issue `[page-change-monitor] N page(s) changed`. |
| `oracle-url` | `https://oracle.saltcrate.com` | Service base URL. |
| `oracle-key` | — | Optional `orc_…` key for >200 checks/hour (see below). |
| `timeout` | `30` | Per-request timeout, seconds. |

## Outputs

| Output | Description |
|---|---|
| `changed` | Newline-separated URLs that changed this run. |
| `changed-count` | Count of changed pages. |
| `checked-count` | Count of pages checked. |
| `failed` | URLs that could not be fetched. |

```yaml
- uses: saltcrate/page-change-monitor@v1
  id: watch
  with:
    urls: https://example.com/pricing
- if: steps.watch.outputs.changed-count != '0'
  run: echo "pricing page moved — review it"
```

## Recipes

**Daily watch, alert via issue** (`permissions: issues: write` required):

```yaml
on:
  schedule: [{cron: "0 13 * * *"}]
  workflow_dispatch:
permissions:
  contents: read
  issues: write
jobs:
  watch:
    runs-on: ubuntu-latest
    steps:
      - uses: saltcrate/page-change-monitor@v1
        with:
          urls-file: .github/watched-pages.txt
          create-issue: "true"
```

**CI gate on a vendor's terms page** (fails the build when they change it):

```yaml
- uses: saltcrate/page-change-monitor@v1
  with:
    urls: https://vendor.example.com/terms
    fail-on-change: "true"
```

**Bulk check a docs site:**

```yaml
- uses: saltcrate/page-change-monitor@v1
  with:
    urls-file: sitemap-urls.txt
    report-changes-only: "true"
```

## Rate limits and the paid tier

The free tier allows **200 checks per hour per IP** on the hosted service. Public
CI runners share IP pools, so if you watch hundreds of URLs on a tight schedule
you may hit that ceiling and see `paywall` rows in the summary. Two options:

| Plan | Price | Checks |
|---|---|---|
| Free | $0 | 200/hour, no key |
| Starter pass | $1 one-off | 100 checks |
| Full pass | $5 one-off | 1,000 checks |

Passes are one-off (not a subscription), paid by ordinary card — no wallet
needed: **https://oracle.saltcrate.com/buy**

Add the key as a secret:

```yaml
- uses: saltcrate/page-change-monitor@v1
  with:
    urls-file: watched.txt
    oracle-key: ${{ secrets.ORACLE_KEY }}
```

## How it works

Each URL is sent to `POST /check_change` with `X-Oracle-Free: 1`. The service
fetches the page, strips boilerplate (nav, ads, scripts), normalises the text and
compares the SHA-256 with the stored hash for that URL. Response:

```json
{"url": "https://example.com/pricing", "status": "changed", "chars": 4211, "delta_chars": 118}
```

`status` is one of `new` (baseline recorded), `unchanged`, `changed`, `error`.
Nothing is stored in your repository at any point.

The same engine is available as an **MCP server** for AI agents
(7 tools: `fetch`, `search`, `extract`, `check_link`, `check_change`, `verify`,
`monitor`) at `https://oracle.saltcrate.com/mcp` — see
[the docs](https://oracle.saltcrate.com/).

## Development

```bash
INPUT_URLS="https://example.com" python3 monitor.py   # run locally
```

No third-party dependencies; Python 3.9+ standard library only.

## License

MIT
