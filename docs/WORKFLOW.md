# Workflow Plan — `arb-bound`

**Track:** 03 · Commodity Derivatives Intelligence
**Team:** 3 · laptop only · **Repo:** https://github.com/j4yop/arb-bound

This is the plan we build against. Phase 0–3 are **done and verified**; Phase 4–6 are the
remaining build.

---

## How we work

**One rule: no result is written down until the code produces it.** Every number in the
README, the deck and this plan came out of a command someone ran. When the output contradicted
the hypothesis, we fixed the code or reported the contradiction — we never edited the claim.

Two loops, run constantly:

```
hypothesis  ->  run it  ->  does the output match?  ->  no: WHY?  ->  fix model, rerun
                                          ->  yes: write it down
```

Every time the output disagreed with us, it found a real defect. See §Phase 3.

---

## Architecture

```
                    MCX bhavcopy  (JSON embedded in page, or CSV drop)
                                     |
                    +----------------+----------------+
                    |                                 |
             arbbound/fetch.py              (CSV fallback path)
              proxy-routed fetch
                    |                                 |
                    +----------------+----------------+
                                     |
                            +-----------------+
                            |  ingest.py       |  <- all parsing, all normalisation
                            |                 |     nothing downstream sees a raw row
                            +-----------------+
                                     |
                    symbol strip | MCX date formats | FUTCOM filter
                    per-gram-of-FINE-gold price | no_trade / is_thin flags
                                     |
                    +----------------+----------------+
                    |                                 |
          contracts.py                     ingest.matched_basis()
          the contract master              maturity-matched basis
          (every fact cited)               (offset expiry calendars handled)
                    |                                 |
                    +------------+--------------------+
                                 |
                    +------------+-------------+
                    |                          |
              bound.py                  analysis.py
              the structural bound       walk_forward()  train-fitted centre, frozen
              fabrication overhead       detect_breaks()  mean-shift + volume signature
              purity/duty wedge          check_executability()  hi/lo + volume audit
              statutory friction                                    |
                    |                          |                     |
                    +------------+-------------+
                                 |
                          cli.py  ->  build_report()
                                 |
                    +------------+------------+
                    |                         |
              report.json               report.py / build.py
              machine-readable          docs/index.html  (GitHub Pages)
```

### Module responsibilities

| Module | Owns | Never does |
|---|---|---|
| `contracts.py` | Purity, lot, quote base, expiry window, provenance | Any arithmetic |
| `bound.py` | The economic bound + every assumption constant | Touching market data |
| `ingest.py` | Parsing, normalisation, maturity matching | Any judgement about tradeability |
| `analysis.py` | Walk-forward, break detection, executability | Loading files or CLI concerns |
| `cli.py` | Wiring, human output | Analysing |
| `fetch.py` / `report.py` / `build.py` | I/O only | Domain logic |

The dependency arrow points one way: `cli → analysis → {bound, ingest} → contracts`.
No module imports the one below it in the cycle. This is what makes each piece testable
in isolation and what lets us replace an assumption without touching the pipeline.

---

## Tech stack

| Layer | Choice | Why this and not the alternative |
|---|---|---|
| Language | **Python 3.11+** | Only stack where the MCX data ecosystem lives |
| Data | **pandas + NumPy** | Already standard for bhavcopy; no new dependency risk |
| Stats | **stdlib `math`, `statistics`** | The mean-shift statistic is ~10 lines. `ruptures` was installed and rejected — 5 strikes is not a changepoint problem, and a dependency is a demo risk |
| Storage | **CSV + JSON, committed to git** | Judges can clone and rerun with zero setup. No DB, no cloud, no API key |
| Tests | **pytest, 39 tests** | Contract facts and bound logic encoded as assertions |
| UI | **Server-rendered HTML, inline SVG, zero JS deps** | Opens offline in Manali with no `npm install`. A build step is a demo risk |
| Deploy | **GitHub Pages** | Free, public, live URL for judges |
| CI | `pytest` on push | A red test blocks the claim |

**Explicitly rejected:** a database, a web framework, a charting library, an options-pricing
library, live broker APIs. Each adds a failure mode to a demo that must not fail in a room.

---

## The workflow, phase by phase

### Phase 0 — Feasibility *(complete)*
**Question:** can we get the data at all, from a machine that MCX blocks?
- Found MCX returns **HTTP 403 (Akamai)** on every path from a data-centre IP; `archives.mcxindia.com` has no DNS.
- Solved by fetching the page through a read proxy with a different egress and extracting the embedded JSON array: **15,369 rows parsed.**
- **Exit criterion met.** Data is real, free, and no API key.

### Phase 1 — Contract master *(complete)*
- Wrote `contracts.py` with purity, lot size, quote base, expiry window, and a `Provenance` object per fact.
- Verified against MCX contract specs and the 05-Aug-2025 circular.
- **Why first:** every downstream number is wrong if this is wrong. Nothing else can be trusted until this is pinned.

### Phase 2 — Normalisation *(complete)*
- Built `ingest.py`: symbol padding, two MCX date formats, `OPTFUT` filtering.
- **The trap:** `OPTFUT` rows share the `Symbol` of their underlying future. Unfiltered, they silently corrupt every average downstream. Caught by writing the filter before the first analysis run.
- Per-gram-of-fine-gold: `px / quote_grams / purity`.

### Phase 3 — The bound, and three real bugs *(complete)*

This is where the work actually happened. The first run **contradicted the thesis** — 5 of 6 pairs showed breaches up to +989 bps. Each was a genuine defect:

| # | Bug | Symptom | Fix |
|---|---|---|---|
| 1 | Averaged across all listed expiries | Term structure leaked into cross-contract basis; +989 bps artefacts | `matched_basis()` pairs each contract with the expiry closest in time; drops legs >7 days apart or >120 DTE |
| 2 | Purity modelled as a divisor | GOLDM vs 999 pairs permanently "breached" | Purity is a **delivery-time cash adjustment** (`Rate × 999/995`). Added `purity_wedge_bps` |
| 3 | Took `abs(residual)` | Fabrication is **one-way**; both directions treated as tradeable | Only the dear-to-manufacture side is tradeable. Direction from the pair's overhead ordering, not the basis sign |
| 4 | Tradable sign flipped on negative median | A constant −20 bps basis inverted the test | Fixed to use overhead ordering, which is a property of the *pair* |

**Exit criterion met:** the output stopped contradicting the thesis, and where it still
disagrees it says so (two pairs breach and hold a stable level — reported, not explained away).

### Phase 4 — Make it demonstrable *(in progress)*
The hardest 6 minutes of the hackathon is not building this. It is a judge understanding it.

- [ ] **Deck:** lead with the number. *"₹2,164 of gold premium vanished in 15 trading days in Nov 2024 — we found the day, and it wasn't an arbitrage."*
- [ ] **Two-screen demo:** load a bhavcopy → watch the verdict print. One command, live.
- [ ] **Judge script:** 3 scripted questions, each one click deep.
- [ ] **Kill the 6-minute-methodology trap.** If we open with method, we lose the room.
- [ ] **Social round:** the Reel is the moment the line steps. 30 seconds, no narration needed.

### Phase 5 — Close the credibility gap
The demo is only half. The other half is surviving Q&A.

- [ ] **Attack the weakest input first.** Who challenges the ₹20–60/bar mint cost? Have the sensitivity table ready.
- [ ] **Publish the limitations panel in the UI**, not just the README. A rigour claim you volunteer is worth more than one you're caught without.
- [ ] **Pre-register the hypothesis with a timestamp + commit hash**, before the final analysis run. It's already committed — preserve that.
- [ ] **GitHub Actions** running pytest on every push.

### Phase 6 — The open question *(the real differentiator)*
We dated a regime break and could not attribute it. That is worth more than a tidy answer.

- [ ] **Hunt the Nov 2024 cause.** MCX circular archive is numbered and dated. Pull Oct–Dec 2024 bullion circulars and check for a contract-spec or delivery change.
- [ ] **If found:** that's the headline — we explain a dislocation the leading competitor flagged and couldn't solve.
- [ ] **If not found:** publish it as an open question with the date, the window, and the volume signature. Explicitly blessed by the brief.
- [ ] **Bonus if time allows:** extend the maturity-matched method to silver (`SILVER`/`SILVERM`/`SILVERMIC`/`SILVER100`) — identical contract structure, near-zero extra code.

---

## Definition of done

- [x] Real MCX data, no API key, no synthetic rows
- [x] Input → output CLI, deterministic
- [x] Structural bound with **sourced** facts and **ranged** assumptions
- [x] Walk-forward with no look-ahead
- [x] Regime-break detection with volume signature
- [x] Executability audit against printed hi/lo
- [x] 39 tests green
- [x] Live demo at `j4yop.github.io/arb-bound`
- [x] Problem statement + Q&A documented
- [ ] Deck
- [ ] Nov 2024 attribution

---

## Appendix A — Problem statement and Q&A (condensed)

**Problem.** MCX lists one metal as four physically-delivered futures. A trader sees four
prices and a spread, and concludes the spread is available. Three things make that wrong:
delivery is compulsory; fabrication cost is fixed *per bar*, so per-gram overhead scales
inversely with size; and the contracts are not the same thing (GOLDM is 995 purity quoting
duty-inclusive Ex-Ahmedabad; the rest are 999 retail bars). The observable gap is therefore a
mixture of a contractual wedge, a physical conversion cost, and possibly a real dislocation —
and the prices alone cannot separate them. The data needed to settle it is free and public.

| Question | Answer |
|---|---|
| **How large must the gap be to profit?** | A bound from structure, not fitted to data: fabrication overhead + purity/duty wedge + statutory friction. **~13 bps** for 999-only pairs, **~240–270 bps** where the wedge applies, plus friction. Band: **~35–360 bps**. |
| **Did any pair beat it out of sample?** | **No persistent edge.** 6 pairs, walk-forward, level fitted on train only. Flagged days re-tested against the exchange's own printed high/low bands. |
| **Why does the basis jump?** | Structural cost cannot jump, so discontinuities are events. Clearest case: **GOLDGUINEA/GOLDPETAL, +245.7 → −12.0 bps across ~3 weeks in Nov 2024.** A monotone drift, not a dated circular taking effect. The nearest circular (Aug 2025) **post-dates it by 8 months.** Open question, deliberately. |
| **Could it have been traded?** | The bhavcopy is settlement, not executable quotes. Every flagged day is re-tested for reachability within printed hi/lo and liquidity. Settlement alone proves nothing. |
| **Why not a rolling z-score?** | Three defects it causes: term structure leaks in via offset expiry calendars; purity is a delivery adjustment, not a divisor; and fabrication is one-way, so only one direction is tradeable. |

**Full version with derivations:** [`PROBLEM.md`](PROBLEM.md)

---

## Appendix B — Tech stack at a glance

| Layer | Choice | Rejected alternative & why |
|---|---|---|
| Python 3.11+ | The only stack where the MCX ecosystem lives | — |
| pandas + NumPy | Standard for bhavcopy | — |
| stdlib stats | Mean-shift is ~10 lines | `ruptures` — 5 strikes isn't a changepoint problem, and a dep is a demo risk |
| CSV + JSON in git | Clone and rerun with zero setup | A database — another failure mode |
| pytest | 39 tests encode the contract facts | — |
| Inline SVG, zero JS | Opens offline in Manali, no `npm install` | React/Vite — a build step that can fail on stage |
| GitHub Pages | Free live URL for judges | — |

---

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Judge reads it as "they proved nothing works" | Medium | High | Lead with the Nov 2024 detective story; null is the *conclusion*, not the hook |
| Mint cost challenged as unsourced | **High** | Medium | It's stated as an assumption; `--sensitivity` sweeps it; panel volunteers it first |
| Demo fails on stage | Low | High | Zero deps, committed data, no network. It cannot fetch anything at demo time |
| Nov 2024 proves unexplainable | Medium | Low | Explicitly a valid outcome; dated evidence either way |
| Another team ships options work | Medium | Low | We're not competing on breadth — the options projects need data we verified is thin |

---

## Immediate next actions

1. **Write the deck** (Phase 4). Everything it needs already exists and runs.
2. **Chase the Nov 2024 circular** (Phase 6). Highest research value left.
3. **Add GitHub Actions** so the green test suite is visible to judges.