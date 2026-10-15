# arb-bound

**Physical delivery costs as a structural no-arbitrage bound for MCX cross-contract gold.**

Built for **Hack in Hills '26 · Track 03: Commodity Derivatives Intelligence**.

---

## Live Links

- **Live Analytics Dashboard:** <https://arb-bound.vercel.app/>
- **Interactive Browser Playground:** <https://arb-bound.vercel.app/playground.html>  
  *(Zero server, zero API key — runs the actual Python analysis client-side via Pyodide WebAssembly)*

---

## Problem Statement

MCX lists the same physical underlying — gold — across four futures contracts differing in lot size, delivery fineness, and quotation basis:

| Contract | Lot Size | Quote Base | Purity | Expiry Window |
|---|---|---|---|---|
| `GOLDM` | 100 g | per 10 g | **995** | 3rd–5th |
| `GOLDTEN` | 10 g | per 10 g | 999 | 27th–31st |
| `GOLDGUINEA` | 8 g | per 8 g | 999 | 27th–31st |
| `GOLDPETAL` | 1 g | per 1 g | 999 | 27th–31st |

When these contracts trade at apparent basis differentials, screen traders naively assume an arbitrageable mispricing exists.

In reality, three structural mechanics prevent riskless extraction:
1. **Compulsory physical delivery:** Closing a cross-contract basis requires taking delivery of physical bars, not merely cash-settling.
2. **Fixed fabrication costs:** Minting, assaying, serialising, and transporting gold bars is a fixed cost per bar, not per gram. Fabrication overhead per gram scales inversely with bar size (`fixed_cost_per_bar / bar_grams`), making a 1 g bar carry ~8× the per-gram fabrication overhead of an 8 g bar.
3. **Contractual purity/duty wedge:** `GOLDM` is 995-fineness quoted duty-inclusive *Ex-Ahmedabad*, whereas the others are 999 retail bars. MCX delivery rules adjust 999 material delivered into 995 contracts at `Rate × 999/995`.

**The Failure:** Traders who treat these structural wedges as mispricings burn capital paying bid-ask spread, slippage, STT/CTT, stamp duty, GST, and exchange fees into a spread that was never tradeable.

---

## Questions Asked & Solutions Delivered

### Q1. How large must a cross-contract basis be before anyone can extract profit?
- **Solution:** Derived an analytical, structural economic bound from contract specifications rather than curve-fitting:
  $$\text{Bound} = \Delta \text{Fabrication Overhead} + \text{Purity/Duty Wedge} + \text{Statutory Frictions \& Slippage}$$
  - Fabrication overhead difference: 20–60 INR/bar assumption (swept across full parameter sensitivity).
  - Purity/duty wedge: Sourced directly from MCX circulars.
  - Statutory frictions: SEBI/exchange turnover fees, STT/CTT, stamp duty, brokerage, and GST (4–35 bps per leg).
- **Answer:** The no-arbitrage bound is **13–362 bps** across all pairs (~13–40 bps for 999/999 pairs; ~240–362 bps when crossing into 995 `GOLDM`).

### Q2. Does any contract pair ever exceed that bound in unseen data?
- **Solution:** Walk-forward out-of-sample evaluation across **11,771 traded rows** (October 2023 – September 2026).
  - Train/test split with freeze: Only one scalar (centring level) is fitted on training data and frozen out-of-sample; zero hyperparameters tuned on test data.
  - Strictly one-way: Small bars are structurally dearer to fabricate. A trading signal exists only when the expensive-to-mint leg trades rich.
  - Executability audit: Isolated breach days are audited against exchange-printed High/Low bands and orderbook depth.
- **Answer:** **No persistent arbitrageable edge survives costs.** Apparent spreads collapse into structural costs. (A validated, rigorous null result explicitly permitted by Track 03 criteria).

### Q3. If there is no tradeable edge, why does the basis jump?
- **Solution:** Discontinuities cannot be produced by stationary minting costs; they signal regime shifts or liquidity shocks.
  - Applied two-sided mean-shift detection coupled with volume signature analysis.
  - Decomposed the notable **November 2024 basis drift** (+245.7 bps to −12.0 bps over ~3 weeks in `GOLDGUINEA/GOLDPETAL`):
    - Macro post-US election gold sell-off dropped the entire complex ~312 bps.
    - `GOLDGUINEA` tracked international spot immediately, while `GOLDPETAL` maintained a +167 bps retail convenience premium.
    - Verified against MCX Master Circulars that no contract specification change occurred during that window.
- **Answer:** Discontinuities reflect macroeconomic retail-premium compression and liquidity shocks, not exploitable arbitrage.

---

## Project Workflow

```
[MCX Bhavcopy: JSON / CSV]
           │
           ▼
[1. Ingestion & Sanitisation] ──► Strip symbols, normalise date variants, filter OPTFUT
           │
           ▼
[2. Purity Normalisation]     ──► Convert to INR per gram of FINE gold (px / quote_grams / purity)
           │
           ▼
[3. Maturity Matching]        ──► Pair contracts by nearest expiry (offset <= 7d, DTE <= 120d)
           │
           ▼
[4. Structural Bound Engine]  ──► Compute analytical cost floor (minting + wedge + friction)
           │
           ▼
[5. Walk-Forward Analysis]    ──► Train-fitted centre frozen into test window (one-way cost rule)
           │
           ▼
[6. Regime & Executability]   ──► Mean-shift break detection & exchange High/Low band audit
           │
           ▼
[7. Multi-Target Delivery]    ──► CLI JSON / Static HTML Dashboard / Pyodide WebAssembly Playground
```

---

## Architecture & Codebase Layout

Unidirectional dependency flow: `cli / playground → analysis → {bound, ingest} → contracts`.

```
arbbound/
├── contracts.py    # Contract master: lot, purity, quote basis, provenance citations (no arithmetic)
├── bound.py        # Economic no-arbitrage bound & parameter sensitivity sweeps (no market data)
├── ingest.py       # Parsing, fine-gold normalisation, maturity-matched pairing (no trading assumptions)
├── analysis.py     # Walk-forward testing, two-sided break detection, executability audits
├── cli.py          # Unified CLI entrypoint and JSON report serialization
├── fetch.py        # Proxy-routed live MCX data fetcher (bypasses CDN IP blocks)
├── report.py       # Self-contained zero-dependency HTML dashboard generator
├── playground.py   # Pyodide WebAssembly build orchestrator for browser execution
└── deck.py         # Programmatic PPTX generation synced directly from report.json
tests/              # 95 tests: contract specifications, bound math, AST anti-hardcoding guards
docs/               # Deep documentation, problem breakdown, workflow plans, and pitch deck
```

---

## Tech Stack

- **Core Analytics:** Python 3.11+, NumPy, pandas (vectorised financial calculations).
- **Statistics:** Standard library `math` and `statistics` (lean, deterministic, zero dependency risk).
- **In-Browser Execution:** [Pyodide](https://pyodide.org/) WebAssembly — runs Python package client-side in the browser with zero backend infrastructure.
- **UI & Presentation:** Pure HTML5 + inline SVG (dependency-free, offline-operable, instant load).
- **Test Suite:** `pytest` (95 unit & integration tests) including AST-level parsing (`test_no_hardcoding.py`) ensuring no hardcoded outcomes or date branches.
- **Deployment:** Vercel edge delivery.

---

## Quick Start

### 1. Setup & Tests
```bash
git clone https://github.com/j4yop/arb-bound.git
cd arb-bound
pip install pandas numpy pytest

# Run the full test suite (95 tests)
PYTHONPATH=. pytest -q
```

### 2. Run the Analysis CLI
```bash
# Analyze historical dataset (Oct 2023 – Sep 2026, 11,771 rows)
python -m arbbound.cli --input data/fixture_gold_2023-2026.csv

# Output full machine-readable JSON report
python -m arbbound.cli --input data/fixture_gold_2023-2026.csv --json docs/report.json

# Run sensitivity sweep over all parameter corners
python -m arbbound.cli --sensitivity --input data/fixture_gold_2023-2026.csv
```

### 3. Build & Regenerate Artifacts
```bash
# Build static dashboard & playground
python -m arbbound.build --input data/fixture_gold_2023-2026.csv --outdir docs

# Regenerate presentation deck directly from report metrics
python -m arbbound.deck --report docs/report.json --out docs/arb-bound-deck.pptx
```

---

## Documentation & Deep Dives

- [`docs/PROBLEM.md`](docs/PROBLEM.md): Complete economic problem statement, question derivations, and mathematical proofs.
- [`docs/WORKFLOW.md`](docs/WORKFLOW.md): End-to-end architecture, module contracts, and phase-by-phase build logs.
- [`docs/NOV2024.md`](docs/NOV2024.md): Decomposed case study of the November 2024 basis break.
- [`docs/JUDGE-SCRIPT.md`](docs/JUDGE-SCRIPT.md): 6-minute presentation script and technical defense Q&A.
- [`docs/arb-bound-deck.pptx`](docs/arb-bound-deck.pptx): Official Hack in Hills submission deck.
