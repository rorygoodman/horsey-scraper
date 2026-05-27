# horses.json Web Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A static, self-contained `index.html` that renders the latest `horses.json` as an edge-ranked table, plus a `publish.sh` that scrapes and force-pushes the page + data to a `gh-pages` branch for GitHub Pages.

**Architecture:** Mirrors the `golf-odds-scraper` pattern. `index.html` (inline CSS + vanilla JS, no deps) fetches `horses.json` client-side. `publish.sh` runs `./run.sh`, copies `index.html` + `horses.json` into a throwaway `public/` git repo, and force-pushes it to `gh-pages` (served by Pages at `https://rorygoodman.github.io/horsey-scraper/`). A committed `examples/horses.example.json` enables offline preview; a thin `tests/test_site.py` guards the sample's validity and the page↔schema field references.

**Tech Stack:** Static HTML/CSS/JS, bash, GitHub Pages, `gh` CLI. Python only for the guard test (pytest, existing `arb_finder.validation`).

**Spec:** `docs/superpowers/specs/2026-05-27-horses-web-page-design.md`

---

### Task 1: Sample data + `test_example_validates`

**Files:**
- Create: `examples/horses.example.json`
- Create: `tests/test_site.py`

- [ ] **Step 1: Write the failing test** — create `tests/test_site.py`:

```python
"""Tests guarding the static site: the sample data stays schema-valid and
index.html references the fields it renders. (The page/script themselves are
verified by manual preview + end-to-end publish.)"""

from __future__ import annotations

from pathlib import Path

from arb_finder.validation import validate_horses_output

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "horses.example.json"


def test_example_validates():
    assert validate_horses_output(EXAMPLE.read_text()) == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_site.py -q`
Expected: FAIL — `FileNotFoundError` (examples/horses.example.json does not exist).

- [ ] **Step 3: Create `examples/horses.example.json`** with exactly:

```json
{
  "computedAt": "2026-05-27T20:34:11Z",
  "betfairScrapedAt": "2026-05-27T20:34:01Z",
  "paddypowerScrapedAt": "2026-05-27T20:34:05Z",
  "horseCount": 3,
  "horses": [
    {
      "venue": "Cartmel",
      "country": "GB",
      "offTime": "2026-05-27T18:38:00+01:00",
      "marketName": "18:38 Cartmel",
      "betfairWinMarketId": "1.258587656",
      "runner": { "name": "Clean Getaway", "selectionId": 66112233 },
      "paddypower": { "winPrice": 15.0, "winPriceRaw": "14/1", "eachWayTerms": { "fraction": 0.2, "places": 3 } },
      "betfair": { "winLay": 19.0, "placeLay": 3.45, "placeMarket": "TOP_3" },
      "edge": 0.0469
    },
    {
      "venue": "Kempton",
      "country": "GB",
      "offTime": "2026-05-27T21:00:00+01:00",
      "marketName": "21:00 Kempton",
      "betfairWinMarketId": "1.258587732",
      "runner": { "name": "Gooloogong", "selectionId": 66445566 },
      "paddypower": { "winPrice": 7.0, "winPriceRaw": "6/1", "eachWayTerms": { "fraction": 0.2, "places": 3 } },
      "betfair": { "winLay": 7.8, "placeLay": 2.04, "placeMarket": "TOP_3" },
      "edge": -0.0121
    },
    {
      "venue": "Kempton",
      "country": "GB",
      "offTime": "2026-05-27T21:00:00+01:00",
      "marketName": "21:00 Kempton",
      "betfairWinMarketId": "1.258587732",
      "runner": { "name": "Filibustering", "selectionId": 66778899 },
      "paddypower": { "winPrice": 6.5, "winPriceRaw": "11/2", "eachWayTerms": { "fraction": 0.2, "places": 3 } },
      "betfair": { "winLay": 7.0, "placeLay": 2.04, "placeMarket": "TOP_3" },
      "edge": -0.0210
    }
  ]
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_site.py -q`
Expected: PASS (1 test). If it fails, the example doesn't match the schema — read the validator error and fix the JSON (do not weaken the test).

- [ ] **Step 5: Commit**

```bash
git add examples/horses.example.json tests/test_site.py
git commit -m "site: add schema-valid horses.example.json + guard test"
```

---

### Task 2: The page (`index.html`)

**Files:**
- Create: `index.html`
- Modify: `tests/test_site.py`

- [ ] **Step 1: Add the failing test** — append to `tests/test_site.py`:

```python
INDEX = ROOT / "index.html"


def test_index_references_schema_fields():
    html = INDEX.read_text()
    assert "horses.json" in html
    for field in ("computedAt", "horseCount", "edge", "winPrice",
                  "winLay", "placeLay", "placeMarket"):
        assert field in html, f"index.html missing reference to {field!r}"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_site.py::test_index_references_schema_fields -q`
Expected: FAIL — `FileNotFoundError` (index.html does not exist).

- [ ] **Step 3: Create `index.html`** with exactly:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="refresh" content="600">
  <title>Horsey — each-way edges</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { background:#1a1a1a; color:#eee;
      font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
      padding:20px; min-height:100vh; }
    .container { max-width:1100px; margin:0 auto; }
    h1 { color:#9aa; font-size:1.6em; margin-bottom:6px; }
    .summary { color:#888; margin-bottom:16px; font-size:.9em; }
    .summary b { color:#00d4ff; }
    .controls { display:flex; gap:14px; align-items:center; margin-bottom:16px; flex-wrap:wrap; }
    select { background:#222; color:#eee; border:1px solid #555; border-radius:6px;
      padding:8px 10px; font-size:.95em; }
    label { color:#ccc; display:flex; gap:6px; align-items:center; cursor:pointer; font-size:.95em; }
    table { width:100%; border-collapse:collapse; background:#222; border-radius:8px; overflow:hidden; }
    th, td { padding:9px 10px; text-align:right; border-bottom:1px solid #333; white-space:nowrap; }
    th { color:#9aa; font-weight:600; font-size:.8em; text-transform:uppercase; letter-spacing:.03em; }
    td.l, th.l { text-align:left; }
    tr.pos td { background:#10331f; }
    td.edge { font-variant-numeric:tabular-nums; font-weight:600; }
    td.edge.pos { color:#00ff88; }
    .raw { color:#888; font-size:.85em; }
    .msg { color:#bbb; padding:30px; text-align:center; background:#222; border-radius:8px; }
    .err { color:#ff6b6b; }
  </style>
</head>
<body>
  <div class="container">
    <h1>🐎 Horsey — each-way edges</h1>
    <div class="summary" id="summary">Loading…</div>
    <div class="controls" id="controls" style="display:none">
      <select id="venue"><option value="">All venues</option></select>
      <label><input type="checkbox" id="posonly"> edge &gt; 0 only</label>
    </div>
    <div id="content"></div>
  </div>
  <script>
    const fmtPct = e => (e >= 0 ? "+" : "") + (e * 100).toFixed(2) + "%";
    const hhmm = iso => (iso || "").slice(11, 16);
    let HORSES = [];

    function render() {
      const venue = document.getElementById("venue").value;
      const posonly = document.getElementById("posonly").checked;
      let rows = HORSES;
      if (venue) rows = rows.filter(h => h.venue === venue);
      if (posonly) rows = rows.filter(h => h.edge > 0);
      const content = document.getElementById("content");
      if (!rows.length) {
        content.innerHTML = '<div class="msg">No runners match.</div>';
        return;
      }
      const body = rows.map(h => {
        const cls = h.edge > 0 ? " pos" : "";
        const pp = h.paddypower, bf = h.betfair;
        return `<tr class="${h.edge > 0 ? 'pos' : ''}">
          <td class="edge${cls}">${fmtPct(h.edge)}</td>
          <td>${hhmm(h.offTime)}</td>
          <td class="l">${h.venue}</td>
          <td class="l">${h.runner.name}</td>
          <td>${pp.winPrice.toFixed(2)} <span class="raw">${pp.winPriceRaw}</span></td>
          <td>${bf.winLay.toFixed(2)}</td>
          <td>${bf.placeMarket}</td>
          <td>${bf.placeLay.toFixed(2)}</td>
        </tr>`;
      }).join("");
      content.innerHTML = `<table>
        <thead><tr>
          <th>edge</th><th>time</th><th class="l">venue</th><th class="l">runner</th>
          <th>PP win</th><th>BF win</th><th>place</th><th>BF plc</th>
        </tr></thead>
        <tbody>${body}</tbody></table>`;
    }

    async function load() {
      const summary = document.getElementById("summary");
      try {
        const res = await fetch("horses.json", { cache: "no-store" });
        if (!res.ok) throw new Error("HTTP " + res.status);
        const data = await res.json();
        HORSES = data.horses || [];
        const pos = HORSES.filter(h => h.edge > 0).length;
        const updated = data.computedAt ? new Date(data.computedAt).toLocaleString() : "unknown";
        summary.innerHTML =
          `updated <b>${updated}</b> &middot; <b>${data.horseCount}</b> horses &middot; ` +
          `<b>${pos}</b> with edge&gt;0`;
        if (!HORSES.length) {
          document.getElementById("content").innerHTML =
            '<div class="msg">No fully-priced runners right now.</div>';
          return;
        }
        const venueSel = document.getElementById("venue");
        [...new Set(HORSES.map(h => h.venue))].sort().forEach(v => {
          const o = document.createElement("option");
          o.value = v; o.textContent = v; venueSel.appendChild(o);
        });
        document.getElementById("controls").style.display = "flex";
        venueSel.addEventListener("change", render);
        document.getElementById("posonly").addEventListener("change", render);
        render();
      } catch (e) {
        summary.innerHTML = '<span class="err">Failed to load horses.json: ' + e.message + '</span>';
        document.getElementById("content").innerHTML =
          '<div class="msg err">Could not load data.</div>';
      }
    }
    load();
  </script>
</body>
</html>
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_site.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Manual preview (verify it actually renders)**

```bash
mkdir -p /tmp/horsey-preview
cp index.html /tmp/horsey-preview/
cp examples/horses.example.json /tmp/horsey-preview/horses.json
( cd /tmp/horsey-preview && python3 -m http.server 8099 ) &
sleep 1
# open http://localhost:8099 in a browser
```
Confirm: 3 rows; "Clean Getaway" (+4.69%) is green and at the top; the venue `<select>` lists Cartmel + Kempton and filters; "edge > 0 only" leaves just the one green row; the summary reads "3 horses · 1 with edge>0". Then in another check, point it at an empty file
(`echo '{"computedAt":"2026-05-27T20:34:11Z","horseCount":0,"horses":[]}' > /tmp/horsey-preview/horses.json`)
and reload → "No fully-priced runners right now."; delete it → the error message shows. Stop the server: `kill %1` (or `pkill -f "http.server 8099"`).

- [ ] **Step 6: Commit**

```bash
git add index.html tests/test_site.py
git commit -m "site: add index.html page rendering horses.json"
```

---

### Task 3: `publish.sh` + `.gitignore`

**Files:**
- Create: `publish.sh`
- Modify: `.gitignore`, `tests/test_site.py`

- [ ] **Step 1: Add the failing test** — append to `tests/test_site.py`:

```python
import os


def test_publish_script_shape():
    sh = ROOT / "publish.sh"
    assert sh.exists(), "publish.sh missing"
    assert os.access(sh, os.X_OK), "publish.sh not executable"
    text = sh.read_text()
    for token in ("./run.sh", "index.html", "horses.json", "gh-pages", "push -f"):
        assert token in text, f"publish.sh missing {token!r}"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_site.py::test_publish_script_shape -q`
Expected: FAIL — assertion "publish.sh missing".

- [ ] **Step 3: Create `publish.sh`** with exactly:

```bash
#!/usr/bin/env bash
# Scrape today's racing and publish horses.json + index.html to GitHub Pages.
# Usage: ./publish.sh [regions]   (default gb-ie; passed through to run.sh)
#
# Force-pushes a throwaway public/ tree to the gh-pages branch of `origin`
# (authenticated by the gh https credential helper). Run after `gh` login.
set -euo pipefail
cd "$(dirname "$0")"
REGIONS="${1:-gb-ie}"

# 1. Scrape → horses.json at repo root. Aborts (set -e) if the scrape fails.
./run.sh "$REGIONS"

# 2. Stage the site.
rm -rf public
mkdir -p public
cp index.html horses.json public/

# 3. Force-push public/ as the gh-pages branch.
ORIGIN_URL="$(git remote get-url origin)"
cd public
git init -q
git checkout -q -B gh-pages
git add -A
git commit -q -m "Publish $(date -u '+%Y-%m-%dT%H:%MZ')"
git push -fq "$ORIGIN_URL" gh-pages

echo "Published → https://rorygoodman.github.io/horsey-scraper/"
```

- [ ] **Step 4: Make it executable + syntax-check**

```bash
chmod +x publish.sh
bash -n publish.sh && echo "syntax ok"
```
Expected: `syntax ok` (no output from `bash -n` means valid). Do NOT run `./publish.sh` here — it scrapes (needs credentials) and force-pushes; that's the Task 4 end-to-end step.

- [ ] **Step 5: Add `public/` to `.gitignore`** — in the "Local scraper output" section, add a `public/` line (the throwaway publish tree must never be committed to master):

```gitignore
# Local scraper output
scraper.log
betfair.json
paddypower.json
horses.json
arbs.json
debug-page.html
public/
```

Verify: `git check-ignore public` → prints `public`.

- [ ] **Step 6: Run to verify the test passes**

Run: `uv run pytest tests/test_site.py -q`
Expected: PASS (3 tests).

- [ ] **Step 7: Commit**

```bash
git add publish.sh .gitignore tests/test_site.py
git commit -m "site: add publish.sh (scrape + force-push to gh-pages) + ignore public/"
```

---

### Task 4: README + Pages enablement + end-to-end

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a "Web page" section to `README.md`** — insert this block immediately before the `## Tests` section (read the file to find it):

```markdown
## Web page (GitHub Pages)

The latest output is published as a static page at
**https://rorygoodman.github.io/horsey-scraper/** — an edge-ranked table of
every fully-priced runner (positive-edge rows highlighted).

To scrape and publish in one step:

```
./publish.sh            # GB + IE
./publish.sh us         # US only
```

`publish.sh` runs the pipeline, then force-pushes `index.html` + `horses.json`
to the `gh-pages` branch (via the `gh` https credential helper). Preview the
page locally without publishing:

```
mkdir -p /tmp/horsey-preview && cp index.html /tmp/horsey-preview/
cp examples/horses.example.json /tmp/horsey-preview/horses.json
( cd /tmp/horsey-preview && python3 -m http.server 8099 )   # open http://localhost:8099
```
```

Verify: `grep -n "github.io/horsey-scraper" README.md` → one match.

- [ ] **Step 2: Full suite + import smoke**

Run: `uv run pytest -q`
Expected: PASS (existing suite + the 3 new `test_site.py` tests; 2 integration skipped).

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "README: document the GitHub Pages web page + publish.sh"
```

- [ ] **Step 4: (Manual, one-time, needs credentials + racing hours) End-to-end publish + enable Pages**

```bash
./publish.sh us         # or gb-ie during UK racing hours — creates gh-pages on first run
gh api -X POST "repos/rorygoodman/horsey-scraper/pages" \
  -f 'source[branch]=gh-pages' -f 'source[path]=/' 2>/dev/null \
  || gh api -X PUT "repos/rorygoodman/horsey-scraper/pages" \
       -f 'source[branch]=gh-pages' -f 'source[path]=/'
```
First command may already be configured if Pages was enabled before — the `||` falls back to a PUT update. Then open **https://rorygoodman.github.io/horsey-scraper/** (Pages can take ~1 min to build the first time) and confirm the table renders the day's runners with positive edges highlighted. If outside racing hours, the page shows the empty state — that's correct; the rendering is already proven by Task 2's preview.

---

## Self-review

**Spec coverage:**
- `index.html` (self-contained, dark theme, 10-min refresh, summary, venue filter + edge>0 toggle, edge-ranked table with the 8 columns, green positive rows, empty + error states, reads only schema-guaranteed fields) → Task 2.
- `publish.sh` (scrape via `./run.sh [regions]` → copy index.html + horses.json → force-push throwaway `public/` to `gh-pages` via https origin) → Task 3.
- `examples/horses.example.json` (schema-valid sample, one positive + negatives) → Task 1.
- `.gitignore` ignores `public/` → Task 3 Step 5.
- `tests/test_site.py` (example validates; index references schema fields; publish.sh shape) → Tasks 1–3.
- README "Web page" section + Pages enablement (one-time `gh api`) + end-to-end → Task 4.
- Local-preview verification → Task 2 Step 5 + README.

**Placeholder scan:** none — complete code/commands in every step.

**Type/consistency:** `tests/test_site.py` uses `ROOT = parent.parent` (repo root) and references `examples/horses.example.json`, `index.html`, `publish.sh` consistently across the three tasks that grow it. The page's field references (`edge`, `winPrice`, `winLay`, `placeLay`, `placeMarket`, `computedAt`, `horseCount`) match both the `horses.json` schema and the `test_index_references_schema_fields` assertion. `publish.sh`'s `git push -fq` contains the `push -f` token the test checks. The example's fields/values satisfy `validate_horses_output` (fraction 0.2 ∈ (0,1], places 3 ∈ 2..5, placeMarket TOP_3, edge numeric, horseCount 3 == len).
