# Judge Script — 6 minutes

**Rule: nobody in the room should have to understand quant before we get to the point.**

Everything here already runs. Nothing is pre-baked, nothing is mocked, nothing is
hand-typed into a slide. The deck is generated from the same `report.json` the CLI prints.

---

## Pre-flight (2 minutes before you go up)

```bash
cd arb-bound
python -m pytest -q                        # expect: 39 passed
python -m arbbound.cli --input data/fixture_gold_2023-2026.csv
```

Both are offline. **There is no network call at demo time** — the data is committed and the
dashboard is a static file. If the venue wifi dies, nothing changes.

Have open, in this order:
1. Terminal, already at the repo root
2. `docs/arb-bound-deck.pptx`
3. Browser at `j4yop.github.io/arb-bound`

---

## 0:00 — 0:45 · The hook

**Say this, do not read the slide:**

> "MCX lists the same gold four times, in four physical delivery sizes. When one trades at a
> gap to another, that looks like free money. We spent three months of data proving it isn't
> — and in doing so found a 216-rupee-per-gram premium that evaporated in 15 trading days
> in November 2024. We know exactly which day, and we can prove it was never an arbitrage."

**Do not** explain Black-76, purity adjustment, or walk-forward yet. The number is the hook.

---

## 0:45 – 1:30 · The problem, in one breath

Point at the contract table on slide 2.

> "Four contracts. `GOLDM` is 100 grams at 995 purity quoting duty-inclusive Ex-Ahmedabad.
> The other three are 999 retail bars. Delivery is compulsory on all of them."

> "So a trader sees a spread and thinks: I buy the cheap one, sell the rich one, pocket the
> difference. Three things break that. You have to take delivery of actual gold. Minting a bar
> costs a fixed amount per bar, so a one-gram bar costs about eight times more per gram than
> an eight-gram bar. And the contracts aren't even the same product."

> "The data to settle this is free and public. Nobody had used it this way."

---

## 1:30 – 3:00 · The live demo

**This is the part that has to not break, and it now runs in the browser.** Open
`j4yop.github.io/arb-bound/playground.html` before you start talking, so Python has finished
booting. Then:

1. Click **Load bundled sample** → **Run the analysis**. The real package executes in the tab:
   11,954 rows, 6 pairs, ~10 seconds. Say: *"This is the actual code, running here, on this
   machine. No server."*
2. Then **paste something different** — delete the last ~1000 lines of the textarea, or paste a
   handful of your own rows, and run it again. **The verdict changes.** Say: *"If this were
   hardcoded, that number wouldn't move. It moves because it's computed."*
3. Optionally paste deliberate nonsense. It is **rejected with a readable message**, not a
   traceback — because a tool that silently answers garbage is worse than one that refuses.

If the venue wifi is dead, the offline fallback is the CLI (identical pipeline, identical
numbers):

```bash
python -m arbbound.cli --input data/fixture_gold_2023-2026.csv
```

Talk over the output, pointing at these five lines:

| Output | What you say |
|---|---|
| `STRUCTURAL BOUND` — wedge column | "240 basis points on the GOLDM pairs, zero on the 999-only pairs. That's the purity and duty difference. It's a contractual wedge — you can't trade it." |
| `WALK-FORWARD` — level frozen | "We fit one number on the training window. Then we froze it and applied it to data the test never saw." |
| `** LEVEL SHIFTED +150 bps **` | "Two pairs flagged 213 days. But the structural level itself moved. That's a regime change, not 213 separate trades — and we report it that way instead of counting them as opportunities." |
| `REGIME BREAKS — 2024-11-07 +246 → -12` | "This is the find. And we decomposed it: the whole gold complex fell 312 bps after the US election. GOLDPETAL held a 167 bps premium — and it's the *liquid* leg, so it isn't a thin-contract artefact." |
| `VERDICT` | "No persistent edge survives costs." |

**Then switch to the browser.** Scroll to `Basis history`. Point at the
`GOLDGUINEA/GOLDPETAL` chart — **the step is visible.** Say:

> "That's the November 2024 move. You can see the day."

That sentence, with the chart on screen, is the whole pitch.

---

## 3:00 – 4:00 · The honest part

Raise this yourself. Never let a judge find it.

> "Three things we did **not** prove."

> "One — minting cost is an assumption, not a measurement. MCX doesn't publish it. We carry it
> as ₹20 to ₹60 per bar and we only claim conclusions that survive the whole range."

> "Two — the November 2024 break is dated, not explained. We tested the obvious explanation,
> the May 2026 import-duty hike, and it failed the timing test. The spike peaks in February;
> the duty move is in May. So we're reporting it as an open question rather than inventing a
> cause."

> "Three — two pairs still breach the bound on a stable level. `GOLDGUINEA/GOLDM` and
> `GOLDM/GOLDPETAL`. We left them in."

**Why this works:** volunteering your weakest points is the single highest-leverage move in a
judging room. It converts scepticism into evidence of rigour.

---

## 4:00 – 5:00 · Why you, why this

> "There are twenty-eight repositories on this exact problem statement. Most were created in
> the last ten days. Several ship randomly generated data."

> "Two are serious. Both cover only four contracts, neither models the purity wedge, and
> neither corrects for maturity mismatch — these contracts expire on offset calendars, so a
> naive average silently mixes term structure into your spread."

> "One of them flags the November 2024 break in their own README and says the cause is 'not
> yet confirmed'. We dated it independently, and we showed the circular they had in mind
> post-dates it by eight months."

---

## 5:00 – 6:00 · Close and hand over

> "The spread was never the opportunity. We proved it with a bound derived from contract
> specifications, swept across every assumption it rests on."

> "Repo's public, tests run in CI, the demo is a static page that works offline. Go break it —
> the sensitivity table is in there, and we said our own numbers are assumptions."

---

## Anticipated questions

**"Is the minting cost real, or did you pick it to get the answer you wanted?"**
> "That's the right question, and it's why it's a range and why `--sensitivity` exists.
> Here — [run it live] — the structural component moves, but the conclusion doesn't. You can
> see exactly which parts of our claim are load-bearing."

**"Two pairs breached. Isn't that an edge you missed?"**
> "Possibly. We report them rather than tune a constant until they disappear. What we've
> shown is that no *persistent* edge survives costs, and that where a pair breaches on a
> stable level, we've quantified how far and in which direction."

**"Settlement prices aren't fills. Your whole backtest is unexecutable."**
> "Agreed, and that's why the last stage of the tool is an executability audit — every flagged
> day gets re-tested against the exchange's own printed high/low bands and liquidity. A gap
> you could never have crossed isn't an opportunity. We'd need an order-book feed to go
> further, and we say so on the limitations slide."

**"Why should I trust your data?"**
> "Every number in the deck is generated from the same report the CLI prints. Nothing is
> typed in. The tests are in CI, and you can rerun the whole thing from a clone with one
> command."

**"What's next?"**
> "Pull the MCX circulars for October to December 2024 and either explain the break or bound
> the search. Then the method ports to silver unchanged — same four-contract structure."

---

## If you are running short on time

Cut **Future Scope** entirely and go straight from the honest-parts slide to the close.
Never cut the live demo — it is the only part that cannot be faked.