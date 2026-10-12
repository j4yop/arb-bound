# Problem Statement, Questions, and Answers

Hack in Hills '26 · Track 03: Commodity Derivatives Intelligence

---

## 1. Problem statement

MCX lists the same metal — gold — as **four separate futures contracts**, differing only in
physical delivery size and fineness:

| Contract | Lot | Quote base | Purity | Expiry |
|---|---|---|---|---|
| `GOLDM` | 100 g | per 10 g | 995 | 3rd–5th |
| `GOLDTEN` | 10 g | per 10 g | 999 | 27th–31st |
| `GOLDGUINEA` | 8 g | per 8 g | 999 | 27th–31st |
| `GOLDPETAL` | 1 g | per 1 g | 999 | 27th–31st |

A retail trader opening a broker app sees four prices for the same metal and sees a
**spread**. The natural reading is that one is mispriced and the difference is available.

Three things make that reading wrong, and none of them are obvious from the contract list:

1. **Delivery is compulsory.** Closing a cross-contract position means taking delivery of
   physical bars, not just netting a P&L.
2. **Fabricating a bar costs money, and the cost is per-bar, not per-gram.** Converting
   between sizes has a floor, and it scales inversely with bar size.
3. **The contracts are not actually the same thing.** `GOLDM` is 995-purity and quotes
   duty-inclusive Ex-Ahmedabad; the others are 999-purity retail bars on a different basis.

So the observable gap is a mixture of at least three different things: a contractual wedge,
a physical conversion cost, and — possibly — a genuine mispricing. **Nobody can tell them
apart from the prices alone.**

Meanwhile the public data needed to settle the question is free, needs no API key, and is
published daily. It is simply not being used this way.

### The concrete failure this causes

A trader comparing `GOLDPETAL` against `GOLDM` sees a persistent gap of a couple of hundred
basis points and concludes there is an arbitrage. There is not. The gap is roughly what it
costs to mint the metal. Deploying capital on that reading means paying bid-ask spread,
slippage, brokerage, STT, stamp duty and exchange fees into a gap that was never a gap.

---

## 2. Questions this project asks, and answers

### Q1. How large must a cross-contract gap be before anyone can profit from it?

**A bound, derived from contract structure rather than fitted to data.**

The bound has three components:

| Component | Source | Type |
|---|---|---|
| Fabrication overhead difference | `mint_cost_per_bar / lot_grams` | Assumption, range 20–60 INR/bar |
| Purity / duty quote-basis wedge | MCX circular: 999 delivery into 995 settles at `Rate × 999/995` | Sourced mechanism, duty component is a range |
| Statutory friction + slippage | Brokerage + GST 18%, STT/CTT, stamp duty, exchange and SEBI fees | Sourced, range 4–35 bps per leg |

On the bundled sample the bound is **~13 bps** for the 999-only pairs and **~240–270 bps**
where the purity/duty wedge applies, plus friction.

**Answer: between ~35 and ~360 bps depending on the pair.**

---

### Q2. Does any pair ever exceed that bound, in data the test never saw?

**No persistent edge. Six pairs, walk-forward, no look-ahead.**

The centring level is fitted on the training window only and then frozen. The only quantity
fitted to training data is one scalar.

Three of six pairs print gaps above the bound on isolated days. But two of those three show a
large **level shift** between the training and test medians — the structural relationship
itself moved — so the flagged days are reported as regime drift, not as ~200 separate
opportunities. The remaining pair's flagged days were re-tested against the exchange's own
printed high/low bands.

**Answer: no persistent arbitrageable edge survives costs. This is the outcome the problem
statement explicitly permits: "A rigorous demonstration that no persistent edge survives
costs is also a valid analytical outcome."**

---

### Q3. If there is no edge, why does the basis jump around?

**Because structural cost cannot jump. The jumps are events.**

A fixed fabrication cost produces a smooth or slowly-varying basis. A discontinuity means
something else moved.

The clearest instance: the `GOLDGUINEA/GOLDPETAL` basis went from **+245.7 bps to −12.0 bps**
across roughly three weeks in **November 2024** — a monotone drift, not a single-day step. A
contract circular takes effect on a date and would produce a step, so this is **not** a rule
change of the usual kind.

**Answer: a dated, bounded, decomposed regime change, with the rule-change channel closed.**
We report it with a specific date rather than attributing it to a convenient cause. The nearest
Guinea/Petal *futures* spec changes (05-Aug-2025 stagger 5d → 3d; 11-Sep-2025 launch calendar)
**post-date the break by 9–10 months and cannot explain it.** MCX's own Master Circular – Products
confirms no GOLDGUINEA/GOLDPETAL futures-spec change exists anywhere in Oct–Dec 2024 — only Gold
*options* were modified — so the rule-change explanation is **rejected**, not merely unconfirmed.
The supported account is the price-action decomposition below.

**Q3a. The decomposition.** A basis is a difference and cannot say which side moved. So we
decompose the break by contract. Across the four-leg gold complex, the whole complex fell
**−312 bps** after the 5-Nov-2024 US election; `GOLDGUINEA` tracked that move exactly (0 bps
idiosyncratic), while `GOLDPETAL` fell only half as far, holding a **+167 bps relative premium**.
PETAL is the *liquid* leg (~37k lots/day vs ~3k), so this is not a thin-contract artefact, and the
move is a smooth multi-week decay rather than a step — consistent with a retail-premium
normalisation, matching the WGC's India domestic-premium timeline (US$2.8/oz → US$1/oz in the
first week of November). This is now a permanent feature: `analysis.attribute_break` runs on
**every** detected break and reports which leg departed and by how much.

---

### Q4. Can these gaps actually have been traded?

**The bhavcopy records settlement, not executable quotes.**

The problem statement warns directly: *"Settlement prices are official exchange settlement
values and should not automatically be treated as executable fill prices, particularly for
thin contracts."*

So every flagged day is re-tested: was the gap inside the day's own printed high/low band on
both legs, and did both legs carry enough volume to absorb a retail order? A gap that could
never have been crossed is not an opportunity regardless of how large it looks.

**Answer: settlement prints alone cannot establish a tradeable edge, and the tool refuses to
claim one.**

---

### Q5. Why not just use a rolling z-score?

Three reasons, each of which produced a wrong answer during development:

1. **Term structure contaminates the basis.** The contracts expire on *offset* calendars and
   MCX lists six months of expiries. Comparing a median across all expiries mixes carry into
   the cross-contract spread. Fix: pair each contract with the expiry of its partner closest
   in time; drop observations where the legs are more than 7 days apart.
2. **Purity is a delivery-time cash adjustment, not a divisor.** MCX settles `Rate × 999/995`
   at delivery. Dividing by purity is a normalisation convention, not a claim about fair
   value, and it understates the wedge.
3. **Fabrication is one-way.** Small bars are always dearer per gram, so only one direction
   is tradeable. Taking the absolute value of a residual treats both directions as
   exploitable and manufactures hundreds of false breaches.

**Answer: each of these was a real defect found by checking output against the data rather
than trusting it.**

---

## 3. Why this is not generic

- The field already has **28+ repos** on this exact problem statement, most created in the
  last ten days. Several ship **synthetic data** generated by `Math.random()`.
- The two serious existing projects cover **only 4 gold futures**, do **not** model the
  purity/duty wedge, and do **not** correct for maturity mismatch.
- One of them states its own unresolved question — *"the cause is not yet confirmed"* — and
  we have dated the break independently, decomposed it by contract, and closed the rule-change
  channel against MCX's own consolidated circular list.

The claim here is not "we found an edge." It is **"we proved there is not one, by a method
whose every assumption is stated and swept."**

## 4. Limitations

- `MINT_COST_PER_BAR_INR` (20–60) is an **assumption**. MCX does not publish it. Conclusions
  are claimed only where they survive the full range (`--sensitivity`).
- The **duty wedge** is set by Government policy and has changed repeatedly; it is carried as
  a range, never a fitted constant.
- The **Nov 2024 break is dated but not explained.** That is the honest current state.
- `GOLDTEN` has **no data before Apr 2025**, so a GOLDTEN-benchmarked "3-year" series is
  really ~18 months.
- This is **settlement data**. Live executable claims would need an order-book feed.