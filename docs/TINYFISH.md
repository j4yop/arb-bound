# TinyFish Builder Challenge — project plan

**Hack in Hills '26 · side challenge · owner:** jay20gopal@gmail.com
**Sponsor:** TinyFish (enterprise infrastructure for AI web agents)
**Primary asset this plan builds on:** [`arb-bound`](../arb-bound) — the main Track 03 project, already
built, tested (73 tests), and deployed.

---

## 0. The decision, up front

**Build a TinyFish-backed live-data plane for `arb-bound` — but only after a free, 30-minute gate.**

The graded artifact of this challenge is *not* the code. It is the submission package: one
successful TinyFish run, a dashboard screenshot, two social posts, and the form. So the plan is
deliberately inverted: **the compliance package is hour one**, and the project is contingent and
gated, never load-bearing.

Three advisors and all three peer-reviewers converged on the same rule:

> Never make an unverified vendor capability the thing your demo stands on.

TinyFish's marketing says its stealth defeats Cloudflare/DataDome. Nobody — including us — has
verified it against `mcxindia.com`, which is Akamai-protected and which we already know returns
**HTTP 403 to datacenter IPs**. So we treat that as a hypothesis with a test, not a premise.

---

## 1. Problem

Two problems, nested.

### 1.1 The problem the *challenge* is really scoring

The TinyFish side challenge asks: can you take a natural-language goal and get real work done on
the live web? The measurable expression is "complete your first successful run." Everything else —
the screenshot, the posts, the form — is packaging. A builder who spends a weekend on architecture
and never produces a screenshot scores nothing.

### 1.2 The problem the *project* solves (if it passes the gate)

`arb-bound` tests whether cross-contract MCX gold spreads (`GOLDGUINEA`, `GOLDM`, `GOLDPETAL`,
`GOLDTEN`) are arbitrageable, against a structural cost bound built from real contract specs. It is
honest about three limits it cannot fix by itself:

| Limit | What it costs the project | Can TinyFish fix it? |
|---|---|---|
| **No live data.** It ingests a committed historical CSV (`data/fixture_gold_2023_2026.csv`, 11,771 traded rows) | It is a method demo, not a running product | **Yes** — this is the one real gap |
| **No circular archive.** MCX's circular listing is JS-driven; we could not reach the archive endpoint at all, and closed a research question only via an alternate mirror | The Nov-2024 attribution rests on secondary sources | **Maybe** — needs testing |
| **Settlement, not executable quotes.** The bhavcopy carries closing prices only | The executability audit is an upper bound, not a fill estimate | No — needs an order-book feed |

So the sharpest, most honest framing is not "we bypassed the block." It is:

> `arb-bound` proved a method but was never live. TinyFish gives it a live tick — here is data
> fetched while you watch, and here is the verdict the same 73-test engine prints on it.

**Framing rule (from the Outsider advisor, sharpened by peer review):** lead with *live data → real
engine → real verdict*. Do **not** lead with "we beat Akamai" — to a sponsor's own judges, a story
about circumventing a regulated exchange's bot defence can read as a red flag rather than a flex.
MCX is the arena; it is not the pitch.

---

## 2. Solution

**`arb-bound-live`** — a thin ingestion plane with one job: satisfy a request for *today's* MCX
data by driving a real browser, hand it to the existing engine, and return the same verdict the
engine already produces.

```
judge asks for a date
        │
        ▼
┌──────────────────────────────┐
│  TinyFish Fetch / Agent      │   URL + natural-language goal
│  (real browser, stealth,     │   → clean JSON / markdown / HTML
│   rotating proxies)          │
└──────────────┬───────────────┘
               │  raw page
               ▼
┌──────────────────────────────┐
│  arbbound.ingest             │   unchanged: symbol padding, MCX date
│  (pandas normalise)          │   formats, OPTFUT filter, per-gram-of-fine
└──────────────┬───────────────┘
               │  tidy frame
               ▼
┌──────────────────────────────┐
│  arbbound.cli.build_report   │   unchanged: bound, walk-forward,
│  (the existing 73 tests)     │   regime breaks, attribution
└──────────────┬───────────────┘
               │  report dict
               ▼
┌──────────────────────────────┐
│  /scan endpoint + link into  │   same verdict text, now on live data
│  the existing dashboard      │
└──────────────────────────────┘
```

The critical design point: **zero new domain logic.** The engine is not touched. Every test it has
still applies. If the web layer fails, the project degrades to exactly what it is today, and nothing
breaks. That is what makes the project safe to attach to a finished, working deliverable.

A second, optional loop: **a Monitor** (`$0.005/run`) on MCX circulars and SEBI notices, emitting a
single field — `contract_spec_changed_at` — that the engine's attribution can read. Monitor is the
only TinyFish primitive that adds a *sense* `arb-bound` structurally lacks: time.

---

## 3. Architecture

### Components

| Component | Responsibility | New/changed |
|---|---|---|
| `tinyfish_plane/` | Fetch or Agent MCX URLs given a date; return raw page bytes/JSON | **New** — the only new code |
| `arbbound/ingest.py` | Normalisation | **Unchanged** |
| `arbbound/analysis.py` | Bound, walk-forward, break detection, attribution | **Unchanged** |
| `arbbound/cli.py` | `build_report()` | **Unchanged** (one new optional arg) |
| `server.py` | `GET /scan?date=YYYY-MM-DD` → plane → engine → JSON | **New**, thin |
| `docs/tinyfish.html` | Live view: progress stream + final verdict | **New**, reuses the inline-SVG/zero-JS-debt style already in `docs/` |
| TinyFish Monitor | Optional scheduled circular change detection | Config only |
| GitHub Actions | Nightly `/scan` to keep a live corpus | One added step |

### Why each TinyFish primitive is used

| Primitive | Cost | Use | Why not the others |
|---|---|---|---|
| **Fetch** | **Free** | MCX bhavcopy + circular PDFs | You already know the URL; you need clean content, not navigation |
| **Search** | **Free** | Find today's circular PDF when the archive listing is unreachable | Cheap fallback that skips the JS listing entirely |
| **Agent** | ~$0.016/step | Only if a goal must be completed (form fill, archive date-filter) | Metered; **use sparingly** — $8 is ≈500 agent steps |
| **Browser** | Metered | Only if the page resists Fetch | Needs your own Playwright/CDP driver |
| **Monitor** | ~$0.005/run | Circular-spec change detection | The one thing that adds temporal capability |

**Budget discipline:** the plan is built on *free* primitives. Agent is the escalation path, capped
and logged, not the default.

---

## 4. Tech stack

| Layer | Choice | Why |
|---|---|---|
| Web plane | **TinyFish Fetch + Search API** (free), Agent as fallback | No new dependency to hold a demo up |
| Python glue | **`tinyfish` SDK** (`from tinyfish import TinyFish`) | Official; one client for all primitives |
| Engine | Existing `arb-bound` CLI + 73 tests | Untouched — no regression risk to the main deliverable |
| HTTP | **FastAPI** + uvicorn | ~40 lines; the endpoint is trivial |
| Front end | Static HTML + inline SVG, reused dashboard style | Opens with no `npm install`; works from GitHub Pages |
| Secrets | `.env`, `TINYFISH_API_KEY` | The key is shown once, never committed |
| Deploy | Same GitHub Pages + Vercel tree | No new host to break |
| CI | Existing GitHub Actions, one nightly step | Evidence the thing really ran |

**Explicitly rejected:** a new database, a broker/API integration, and any rewrite of the engine.
Each is a failure mode for a demo that must not fail.

---

## 5. Workflow plan

### Phase 0 — Compliance package (60 min · zero risk · do this first)

This *is* the graded artifact. Do it before writing any project code.

1. Sign up through the official HIH referral link.
2. Create an API key; store it in `.env`.
3. Connect TinyFish to your AI assistant (MCP or plugin).
4. Run one real automation to completion.
5. Screenshot the dashboard.
6. Follow both accounts on X.
7. Post on X.
8. Post on LinkedIn.
9. Submit the form.

### Phase 1 — The gate (30–45 min · free)

Run this **before** building anything. All four checks use Fetch, not Agent, so they cost nothing.

| Check | Target | Pass criterion |
|---|---|---|
| G1 | A live MCX bhavcopy URL | 200, real HTML/CSV content, not the Akamai block page |
| G2 | A specific MCX circular PDF | 200, extractable PDF text |
| G3 | The MCX circular **archive listing** | ≥1 dated 2026 circular returned |
| G4 | A TinyFish Agent run on the same archive | Structured JSON matching `output_schema` |

### Phase 2 — Decision (5 min)

| Gate result | Decision |
|---|---|
| G1–G4 pass | Build the full plane (bhavcopy + circulars + Monitor) |
| G1–G2 pass, G3–G4 fail | Scope to **bhavcopy-only live ingestion** + a Search-based circular lookup |
| All fail | Keep the compliance package; run the project on a different public domain through the identical plane; **document the MCX negative result** (which is what `arb-bound` does anyway) |

### Phase 3 — Build (2–3 h, only if gated green)

1. `tinyfish_plane/fetch.py` — `fetch_bhavcopy(date) -> str`
2. `tinyfish_plane/adapter.py` — feed bytes to `arbbound.ingest` unchanged
3. `server.py` — `/scan?date=`
4. `docs/tinyfish.html` — progress + verdict
5. Test: same date must produce the same verdict as the committed CSV
6. Add the nightly CI step

### Phase 4 — Package the story (30 min)

Screenshot, a short X post, a LinkedIn post, and a README section that states the gate results
honestly — including which check failed, if any did.

### Documented failure modes

| Risk | Mitigation |
|---|---|
| MCX 403s TinyFish too | Phase 2 scopes down; compliance already banked in Phase 0 |
| The bhavcopy is a ZIP, and Fetch returns markdown | Fetch returns HTML/markdown, not the file; use Browser or a direct download URL |
| The archive stays walled | Use Search to find circular PDFs directly, bypassing the listing |
| $8 credits run out mid-project | Phase 0 and Phase 1 are free; only Phase 3 spends, and only on Agent |
| The dependency hurts the main project | Zero changes to `arbbound/`; the plane is additive and isolated |

---

## 6. Manual steps only Jay can do

Nothing in this list can be delegated to an agent — each step needs your own browser session,
your credentials, or your name on the post.

### Phase 0 — the graded package

1. **Sign up** via the official HIH referral link
   (`https://agent.tinyfish.ai/sign-up?ref=…`). Do not use the generic page, or the referral is lost.
2. **Create the API key** at `agent.tinyfish.ai/api-keys` → *Create API Key*. Shown **once**.
   Copy it into `arb-bound/.env` as `TINYFISH_API_KEY=...`. Confirm `.env` is gitignored.
3. **Connect TinyFish to your AI assistant** — pick one:
   - ChatGPT or Claude: install the **plugin** (one-tap, OAuth, no API key needed)
   - Claude Code / Codex / Cursor / OpenCode: add the MCP server
     `https://agent.tinyfish.ai/mcp`
   - Either is fine for the challenge; the plugin is fastest
4. **Run your first automation.** A good, honest one is a real page. Then confirm the run appears
   under *Runs* in `agent.tinyfish.ai/home` with a COMPLETED status.
5. **Screenshot the dashboard** showing the completed run. Redact the API key if it is visible.
6. **Follow** `@Tiny_Fish` and `@HackInHills` on X.
7. **Post on X** (see draft below), publish, copy the tweet URL.
8. **Post on LinkedIn** (see draft below), publish, copy the post URL.
9. **Submit the Google Form once**, with: registered email, TinyFish signup email, referral-confirmed,
   the screenshot, "what would you automate", both social URLs, and the disclosure confirmation.

### Phase 1 — the gate

10. Run the four gate checks above. **Read the results before deciding anything.**

### Optional, for the wider TinyFish community

11. Consider the free Student / Ambassador programs — they are separate, open to anyone, and pay per
    approved build. Shipping the project is the application.

---

## 7. Post drafts

Disclose the benefit — the form asks you to confirm you did, and it is the honest thing anyway.

**X (from their tweet-intent, personalised):**

> Just unlocked $8 in TinyFish signup credits 🐟
>
> Claim yours: https://tinyfish.hackinhills.com
>
> First run: pointed it at a site that blocks datacentre IPs and got real content back. Now wiring it
> into arb-bound, my MCX gold arbitrage engine — so the engine's verdict runs on data fetched live,
> not a committed CSV.
>
> Taking part in the @HackInHills TinyFish Builder Challenge. What would you automate first?
> @Tiny_Fish

**LinkedIn:**

> Just unlocked $8 in TinyFish signup credits 🐟
>
> TinyFish exposes Search, Fetch, Agent, Browser and Monitor as APIs for AI agents — the interesting
> part is that it runs a real browser with stealth, which is exactly what a regulated exchange's
> bot-protection normally stops.
>
> My hackathon project (arb-bound) tests whether cross-contract MCX gold spreads are arbitrageable.
> It could never ingest MCX data live — mcxindia.com returns 403 to datacentre IPs. So the experiment
> is: can TinyFish get the live bhavcopy that my own fetcher couldn't, and does the same 73-test
> engine print the same verdict on it?
>
> Claim yours: https://tinyfish.hackinhills.com
> @TinyFish @HackInHills

---

## 9. Gate results — run and recorded (2026-10-13)

The gate in §5 Phase 1 has been run. All four checks used the recorded API key; wallet at
the time was **$43.95**, now **$42.45** after the Agent runs.

| Check | Target | Result |
|---|---|---|
| **G1** | Live MCX bhavcopy | **PASS** — 4.9 MB of real dated JSON, **all 5 gold symbols present** (`GOLD`, `GOLDGUINEA`, `GOLDM`, `GOLDPETAL`, `GOLDTEN`), `Date 10/12/2026`, `DateDisplay 12 Oct 2026`. `curl` gets an Akamai Access Denied page on the same URL. |
| **G2** | A specific MCX circular PDF | **PARTIAL** — guessed PDF paths returned `target_unreachable`. Superseded by G4, which reaches circulars through the archive UI instead. |
| **G3** | MCX circular archive **listing** | **PASS** — real rows returned (14 most recent circulars with date/category/number). No Akamai block. |
| **G4** | **Agent** applying the archive date filter | **PASS — the decisive one.** Run `fa67aaf5-cda4-4b54-81a2-269988e3577f`, **COMPLETED in 115 steps**, returned **204 circulars** for 01/10/2024 → 31/12/2024 across all 14 result pages. |

### What this unlocks that was previously impossible

The MCX circular archive is JS-driven and its endpoint sits behind a MIME-blocked JS file. In the
main project we could **not** reach it at all and had to close a research question via an alternate
mirror (`docs/NOV2024.md`, H1). The Agent API navigated the real browser, set From/To dates, clicked
Show and paged through. The archived result is committed at
`data/mcx_circulars_oct_dec_2024.json`.

**Follow-up circular #766 read** (the one in-window "spec-change?" candidate that mentioned gold
delivery): MCX/PMT/766/2024, 19 November 2024, effective 29 November 2024. It adds empanelled-refiner
bars to **Gold Mini (100 g)** delivery provisions. It **does not mention or affect GOLDGUINEA or
GOLDPETAL**, and changes no tender period, delivery period, lot size or purity. H1 therefore remains
**rejected on primary evidence**, now from MCX's own archive rather than a mirror.

### A real bug the live path found in the main package

Running the live data through `arbbound.ingest` surfaced a genuine defect:

- The API payload carries `Date` (`10/12/2026`, MM/DD/YYYY) **and** `DateDisplay` (`12 Oct 2026`).
- `_parse_mcx_date` tried `%d/%m/%Y` before `%m/%d/%Y`, so the ambiguous slash date resolved the
  wrong way and **every live row was silently dated two months out** (10 Dec instead of 12 Oct).
- Fix: `ingest._dates_from()` prefers the unambiguous `DateDisplay` when the column is present, and
  the docstring now records that a bare slash date is a guess. Regression tests in
  `tests/test_ingest_dates.py`.

Verified live: the frame's date range is now `2026-10-12`, correct.

### Honest limits found while building

- `?date=` on the bhavcopy URL is **ignored** — only today's bhavcopy is reachable, so this is a
  **daily ingest**, not a historical backfill.
- Fetch is **not perfectly stable** on this endpoint: it sometimes returns an HTML shell instead of
  the embedded JSON. `fetch_bhavcopy` now retries and `_extract_json_array` recovers the payload
  from a wrapper.
- One day is one row per symbol. A single live run does not produce a *series*, so it cannot yet
  exercise the walk-forward engine; it proves ingest, not inference.

---

- [ ] Signed up via the official referral link
- [ ] API key created and stored in `.env` (not committed)
- [ ] TinyFish connected to a supported AI assistant
- [ ] First automation run completed and visible in the dashboard
- [ ] Dashboard screenshot taken
- [ ] Both X accounts followed
- [ ] X post published, URL copied
- [ ] LinkedIn post published, URL copied
- [ ] Form submitted once
- [ ] Gate checks G1–G4 run and their results written down
- [ ] (If green) `/scan?date=` returns the engine's verdict on live-fetched data
- [ ] (If green) A nightly CI step runs it and commits the result
- [ ] The gate result, including any failure, is published — not hidden

---

## 8. Definition of done

- [x] Signed up via the official referral link
- [x] API key created and stored in `.env` (not committed)
- [x] TinyFish connected to a supported AI assistant
- [x] First automation run completed and visible in the dashboard
- [x] Dashboard screenshot taken
- [x] Both X accounts followed
