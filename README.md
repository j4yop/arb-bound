# arb-bound

**Is an MCX cross-contract gold spread an opportunity, or just the cost of closing it?**

MCX lists the same metal in four physical-delivery sizes:

| Contract | Lot | Quote base | Purity | Expiry window |
|---|---|---|---|---|
| `GOLDM` | 100 g | per 10 g | **995** | 3rd–5th |
| `GOLDTEN` | 10 g | per 10 g | 999 | 27th–31st |
| `GOLDGUINEA` | 8 g | per 8 g | 999 | 27th–31st |
| `GOLDPETAL` | 1 g | per 1 g | 999 | 27th–31st |

When two of these trade at a visible gap, the naive reading is "arbitrage". This project
tests whether that is ever true — against the **structural cost of physically delivering
the metal**, which nobody can arbitrage away.

Built for **Hack in Hills '26 · Track 03: Commodity Derivatives Intelligence**.

**Live demo:** <https://j4yop.github.io/arb-bound/> · mirrored on Vercel at
<https://arb-bound.vercel.app/> (same tree, same bytes — see `vercel.json`).

**Full write-ups:** [`docs/PROBLEM.md`](docs/PROBLEM.md) (problem statement + every question and
its answer) · [`docs/WORKFLOW.md`](docs/WORKFLOW.md) (architecture, tech stack, build phases) ·
[`docs/NOV2024.md`](docs/NOV2024.md) (the Nov-2024 break, decomposed) ·
[`docs/JUDGE-SCRIPT.md`](docs/JUDGE-SCRIPT.md) (6-minute demo runbook + Q&A defence)

## Run it yourself, live

**[▶ Open the playground](https://j4yop.github.io/arb-bound/playground.html)** — paste your own
MCX bhavcopy (or load the bundled sample) and the *actual package* runs in your browser via
Pyodide. No server, no API key, nothing sent anywhere. Different input produces a different
verdict, because the result is computed, not stored.

The static report is at **[j4yop.github.io/arb-bound](https://j4yop.github.io/arb-bound/)**.

## Submission deck

[`docs/arb-bound-deck.pptx`](docs/arb-bound-deck.pptx) — 8 slides on the official Hack in Hills
template. Generated from `report.json` by `arbbound/deck.py`, so no number in it can drift
from the code:

```bash
python -m arbbound.deck --report docs/report.json --out docs/arb-bound-deck.pptx
```

---

## The claim

Refining and minting gold bars is dominated by a **fixed per-bar** cost — setup, assay,
serialisation, logistics — not a per-gram cost. So fabrication overhead per gram scales
inversely with bar size:

```
overhead_per_gram = fixed_cost_per_bar / bar_grams
```

A 1 g bar therefore carries roughly **8×** the per-gram overhead of an 8 g bar. That makes
the persistent `GOLDPETAL` premium a **structural constant, not a dislocation**. It can
only be captured by someone who already holds bar inventory and accepts assay, wastage and
warehouse risk. You cannot short into compulsory delivery with a laptop.

A second structural wedge sits on top: `GOLDM` is a **995**-purity contract quoting
*duty-inclusive Ex-Ahmedabad*, while the other three are 999 retail bars. MCX settles 999
material into a 995-denominated contract at `Rate × 999/995`. These contracts are
**contractually different things**, so part of their price difference is not tradeable at all.

---

## Quick start

```bash
pip install pandas numpy pytest

# Analyse a multi-month bhavcopy
python -m arbbound.cli --input data/fixture_gold_2023-2026.csv

# Machine-readable output
python -m arbbound.cli --input data/fixture_gold_2023-2026.csv --json report.json

# Build the HTML dashboard (this is what GitHub Pages serves)
python -m arbbound.build --input data/fixture_gold_2023-2026.csv --outdir docs

# Fetch live data (MCX blocks data-centre IPs; routed through a read proxy)
python -m arbbound.fetch --out data/bhavcopy_2026-09-10.json

# Assumptions are ranges, never point estimates; the sweep uses the input's own price
python -m arbbound.cli --sensitivity --input data/fixture_gold_2023-2026.csv

pytest -q
```

## Input / output

| | |
|---|---|
| **Input** | MCX bhavcopy, either the JSON the page embeds or a flattened CSV |
| **Output** | A verdict per contract pair: `NOT_ARBITRAGABLE` or `BOUND_EXCEEDED_IN_TEST`, plus regime breaks, an executability audit, and a full JSON report |

The tool is deterministic and offline. Same input → same verdict, every time.

---

## What the analysis actually does

**1. Normalise.** Everything becomes rupees per gram of **fine** gold:
`px / quote_grams / purity`. MCX pads symbols with trailing spaces and uses two different
date formats; both are handled. `OPTFUT` rows are filtered out — options share the
`Symbol` of their underlying future and would silently corrupt every average.

**2. Match maturities.** A naive "median of all listed expiries" per contract is wrong here
and dangerously so: the contracts expire on *offset* calendars and MCX lists six months out,
so a median across all expiries mixes **term structure** into the cross-contract basis. This
tool pairs each contract with the expiry of its partner closest in time and drops
observations where the two legs are more than 7 days apart or beyond 120 DTE.

**3. Test walk-forward.** The centring level is fitted on the training window **only**, then
frozen and applied unchanged to the unseen test window. One scalar is fitted; nothing else
is tuned.

**4. Respect one-way cost.** Fabrication is one-way — small bars are always dearer per gram.
An opportunity exists only when the *expensive-to-manufacture* contract trades rich. Taking
the absolute value of the residual (the naive approach) treats both directions as tradeable
and manufactures hundreds of false breaches. There is a test for exactly this.

**5. Detect regime breaks.** A structural cost cannot jump. So discontinuities in the basis
are evidence that something *else* drove them. A two-sided mean-shift statistic locates the
strongest breaks and attaches a volume signature, classifying each as a step change or a
liquidity event.

**6. Audit executability.** A bhavcopy print is a **settlement price, not a quote you can
lift**. Every flagged day is re-tested against the exchange's own printed high/low bands and
liquidity, because a gap you could never have crossed is not an opportunity.

---

## Findings on the bundled sample

11,771 traded rows, Oct 2023 → Sep 2026.

- **No pair shows a persistent arbitrageable edge.** Of six pairs, the large apparent gaps
  are explained by the purity/duty wedge and by fabrication overhead.
- **A genuine regime break in Nov 2024, now decomposed.** The `GOLDGUINEA/GOLDPETAL` basis moved
  **+245.7 → −12.0 bps** over roughly three weeks — not an instant step. Decomposing it by
  contract shows the whole gold complex fell ~−312 bps after the 5-Nov-2024 US election while
  `GOLDGUINEA` tracked it exactly and `GOLDPETAL` held a **+167 bps premium** — and PETAL is the
  *liquid* leg, so it is not a thin-contract artefact. Best-supported account: a retail-premium
  normalisation, matching the WGC's India domestic-premium timeline. Full write-up:
  [`docs/NOV2024.md`](docs/NOV2024.md). The one remaining channel — an MCX contract-spec change —
  was subsequently **closed**: MCX's own Master Circular – Products lists no GOLDGUINEA/GOLDPETAL
  *futures* spec change in Oct–Dec 2024 (only Gold *options* were touched), and the nearest such
  change post-dates by 9–10 months.
- **Level shifts are reported as level shifts.** Two pairs show a large *median* difference
  between train and test windows. That is a change in the structural relationship, not 200+
   separate trading opportunities, and the tool says so.
- **GOLDTEN has no history before Apr 2025**, so any "3-year" comparison using it as the
  benchmark silently covers about 18 months.

---

## Honesty and limits

Stated plainly, because a rigour claim you cannot defend is worthless. The same panel is
rendered on the **live dashboard itself**, not buried here:

- **`MINT_COST_PER_BAR_INR` is an assumption, not a measurement.** MCX does not publish it.
  It is carried as a range and swept via `--sensitivity --input <file>`; conclusions are only
  claimed where they survive the whole range. The sweep is displayed on the dashboard.
- **The duty wedge is policy-set and has moved repeatedly**, so it is a range, never a
  fitted constant. It is the least certain input in the model, and the sensitivity table
  shows how many basis points of the bound rest on it.
- **The Nov 2024 break is dated but not explained.** A rigorous demonstration that no edge
  survives is a valid result; so is an honest "we could not attribute this".
- **The bhavcopy is settlement data.** Anything requiring an executable fill is out of scope
  for this dataset — which is precisely why the executability audit exists.

## No part of this is hardcoded to a result

The one thing that would make all of the above worthless is a stored answer wearing the
clothes of an analysis. Three guards prevent it, and `tests/test_no_hardcoding.py` enforces
them:

- **No date or pair literal in executable code.** The AST is scanned; a date inside a
  provenance note is allowed, a date used to *branch* is not. The deck used to select its
  headline by searching for `"2024-11"` — it now picks the largest adverse break by rule,
  and lands on the same event.
- **A different input produces a different result.** A truncated sample flips three pair
  verdicts; the test asserts it. A hardcoded result would repeat.
- **No invented constants.** The reference price is the median of the supplied input
  (≈ ₹12,384/g on the bundled sample), and `--sensitivity` refuses to run without an input
  rather than falling back to a typed-in price. CI asserts the published price is not a
  round number.

Regenerate everything from a clean clone and the numbers come back identical:

## Data sources

- MCX daily bhavcopy — <https://www.mcxindia.com/market-data/bhavcopy>
- MCX gold contract specifications — <https://www.mcxindia.com/products/bullion/gold>
- MCX circular 05-Aug-2025 (staggered delivery tender period 5d → 3d; 999/995 delivery
  adjustment; Ex-Ahmedabad duty-inclusive quotation basis)

`data/fixture_gold_2023-2026.csv` is derived from published MCX bhavcopy rows and is
bundled so the tool runs offline. `data/bhavcopy_2026-09-10.json` is a live single-day
capture used to demonstrate the ingest path.

---

## Layout

```
arbbound/
  contracts.py   contract master - every economic claim cites a source here
  bound.py       structural arbitrage bound + sensitivity parameters
  ingest.py      MCX parsing, normalisation, maturity-matched basis
  analysis.py    walk-forward test, break detection, executability audit
  cli.py         bhavcopy in, verdict out
  fetch.py       live fetch through a read proxy
  report.py      self-contained HTML dashboard (bound, walk-forward, sensitivity, limits)
  deck.py        generates the submission deck from the report
  build.py       one-shot report + site build
tests/           60 tests: contract facts, bound logic, no-hardcoding, credibility
```