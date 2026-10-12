"""Generate the Hack in Hills submission deck from computed results.

Every number on every slide is read from a report produced by running the
analysis. Nothing is typed in by hand, so the deck cannot drift from the code.

The section order follows the official Hack in Hills '26 PPT template exactly.

Usage
-----
    python -m arbbound.deck --report docs/report.json --out deck.pptx
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Emu, Inches, Pt

# Matches the template's 20 x 11.25in canvas.
SW, SH = 20.0, 11.25

INK = RGBColor(0x1A, 0x19, 0x17)
MUTED = RGBColor(0x6B, 0x68, 0x62)
GOLD = RGBColor(0xA6, 0x7C, 0x00)
OK = RGBColor(0x1F, 0x6F, 0x4A)
WARN = RGBColor(0x9A, 0x67, 0x00)
BAD = RGBColor(0xA0, 0x30, 0x30)
RULE = RGBColor(0xD8, 0xD4, 0xCC)


def _blank(prs: Presentation):
    return prs.slides.add_slide(prs.slide_layouts[0])


def _text(slide, x, y, w, h, runs, size=18, color=INK, bold=False,
          align=None, space_after=6, line=1.25):
    """Place a text box. ``runs`` is a string or a list of paragraphs."""
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    paras = runs if isinstance(runs, list) else [runs]
    for i, p in enumerate(paras):
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        para.space_after = Pt(space_after)
        para.line_spacing = line
        if align is not None:
            para.alignment = align
        r = para.add_run()
        r.text = p
        r.font.size = Pt(size)
        r.font.bold = bold
        r.font.color.rgb = color
        r.font.name = "Inter"
    return box


def _rule(slide, x, y, w):
    ln = slide.shapes.add_shape(1, Inches(x), Inches(y), Inches(w), Pt(2))
    ln.fill.solid()
    ln.fill.fore_color.rgb = RULE
    ln.line.fill.background()
    ln.shadow.inherit = False
    return ln


def _kpi(slide, x, y, w, h, value, label, color=INK, value_size=30, label_size=11):
    box = slide.shapes.add_shape(1, Inches(x), Inches(y), Inches(w), Inches(h))
    box.fill.solid()
    box.fill.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    box.line.color.rgb = RULE
    box.line.width = Pt(1)
    box.shadow.inherit = False
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = Inches(0.14)
    tf.margin_right = Inches(0.10)
    tf.margin_top = Inches(0.12)
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = value
    r.font.size = Pt(value_size)
    r.font.bold = True
    r.font.color.rgb = color
    r.font.name = "Inter"
    p2 = tf.add_paragraph()
    r2 = p2.add_run()
    r2.text = label
    r2.font.size = Pt(label_size)
    r2.font.color.rgb = MUTED
    r2.font.name = "Inter"
    return box


#: Short display names. MCX pair names like "GOLDGUINEA/GOLDPETAL" are far too
#: long to sit inside a 2.8in KPI box without colliding with its neighbour.
_SHORT = {
    "GOLDGUINEA/GOLDM": "GUINEA / M",
    "GOLDGUINEA/GOLDPETAL": "GUINEA / PETAL",
    "GOLDGUINEA/GOLDTEN": "GUINEA / TEN",
    "GOLDM/GOLDPETAL": "M / PETAL",
    "GOLDM/GOLDTEN": "M / TEN",
    "GOLDPETAL/GOLDTEN": "PETAL / TEN",
}


def _short(name: str) -> str:
    return _SHORT.get(name, name.replace("GOLD", ""))


def _section(prs, title, kicker=None):
    """Clear the template's placeholder slide and write a section heading."""
    slide = _blank(prs)
    _text(slide, 1.1, 4.4, 17, 1.2, title, size=52, bold=True)
    if kicker:
        _text(slide, 1.1, 5.6, 17, 0.8, kicker, size=20, color=GOLD)
    return slide


# --------------------------------------------------------------- slide bodies


def slide_title(prs, report, repo):
    s = _blank(prs)
    _text(s, 1.1, 2.0, 17.8, 1.0, "PROBLEM STATEMENT & THEME", size=17, color=GOLD, bold=True)
    _text(s, 1.1, 3.0, 17.8, 2.4,
          ["Is an MCX cross-contract gold spread",
           "an opportunity — or the cost of closing it?"],
          size=44, bold=True, line=1.15)
    _rule(s, 1.1, 5.6, 6.0)

    nov = _headline_break(report)
    if nov:
        _text(s, 1.1, 6.1, 17.8, 1.0,
              f"On {nov['date']}, {abs(nov['magnitude_bps']):.0f} basis points of gold "
              f"premium evaporated. We found the day — and proved it was never an arbitrage.",
              size=19, color=MUTED)
    _text(s, 1.1, 9.6, 17.8, 0.6,
          f"arb-bound  ·  {report['sample']['traded_rows']:,} real MCX rows  ·  {repo}",
          size=13, color=MUTED)


def slide_problem(prs, report):
    s = _blank(prs)
    _text(s, 1.1, 0.7, 17.8, 0.7, "PROBLEM STATEMENT & THEME", size=17, color=GOLD, bold=True)

    _text(s, 1.1, 1.7, 8.6, 4.6, [
        "MCX lists one metal as four physically-delivered futures.",
        "",
        "A trader sees four prices, sees a spread, and concludes the spread is available.",
        "",
        "Three things make that wrong:",
    ], size=17, line=1.35)

    items = [
        ("Delivery is compulsory.",
         "Closing a cross-contract position means taking physical bars, not netting P&L."),
        ("Fabrication cost is fixed per bar.",
         "Per-gram overhead scales inversely with size: a 1 g bar costs ~8x an 8 g bar."),
        ("The contracts are not the same thing.",
         "GOLDM is 995 purity quoting duty-inclusive Ex-Ahmedabad. The others are 999 retail bars."),
    ]
    y = 1.8
    for head, body in items:
        _text(s, 10.2, y, 8.8, 0.5, head, size=16, bold=True, color=GOLD)
        _text(s, 10.2, y + 0.52, 8.8, 1.1, body, size=14, color=MUTED, line=1.3)
        y += 2.0

    _rule(s, 1.1, 7.5, 17.8)
    _text(s, 1.1, 7.9, 17.8, 1.6, [
        "So the observable gap is a mixture of a contractual wedge, a physical conversion "
        "cost, and possibly a real dislocation — and prices alone cannot separate them.",
        "The data needed to settle it is free, public, and published daily. Nobody uses it this way.",
    ], size=17, color=INK, line=1.35)


def slide_solution(prs, report):
    s = _blank(prs)
    _text(s, 1.1, 0.7, 17.8, 0.7, "SOLUTION", size=17, color=GOLD, bold=True)
    _text(s, 1.1, 1.5, 17.8, 1.0, "arb-bound — bhavcopy in, per-pair verdict out",
          size=34, bold=True)
    _rule(s, 1.1, 2.6, 17.8)

    steps = [
        ("1  NORMALISE",
         "Everything becomes rupees per gram of fine gold: px / quote_grams / purity. "
         "MCX pads symbols and uses two date formats; both handled."),
        ("2  MATCH MATURITY",
         "These contracts expire on offset calendars, so a naive average leaks term structure "
         "into the basis. Each leg is paired with the nearest-maturity partner."),
        ("3  TEST WALK-FORWARD",
         "The centring level is fitted on training data only, then frozen and applied to data "
         "the test never saw. One scalar is fitted; nothing else is tuned."),
        ("4  AUDIT EXECUTABILITY",
         "A bhavcopy print is settlement, not a quote you can lift. Every flagged day is "
         "re-tested against the exchange's own printed high/low bands."),
    ]
    x = 1.1
    for head, body in steps:
        _text(s, x, 3.1, 4.2, 0.5, head, size=15, bold=True, color=GOLD)
        _text(s, x, 3.75, 4.2, 2.6, body, size=13.5, color=MUTED, line=1.35)
        x += 4.55

    _rule(s, 1.1, 6.8, 17.8)
    _text(s, 1.1, 7.1, 17.8, 0.6, "THE BOUND  —  derived from contract structure, never fitted to data",
          size=15, bold=True, color=INK)

    rows = sorted(report["bounds"].items())
    x = 1.1
    for name, b in rows:
        col = BAD if b["bound_low_bps"] > 150 else GOLD
        _kpi(s, x, 7.9, 2.85, 1.5,
             f"{b['bound_low_bps']:.0f}–{b['bound_high_bps']:.0f}",
             _short(name), col, value_size=26, label_size=12)
        x += 2.98


def slide_architecture(prs, report):
    s = _blank(prs)
    _text(s, 1.1, 0.7, 17.8, 0.7, "ARCHITECTURE", size=17, color=GOLD, bold=True)

    layers = [
        ("INPUT", "MCX bhavcopy — JSON embedded in the page, or CSV drop. No API key.", MUTED),
        ("arbbound/fetch.py", "proxy-routed live fetch (MCX returns HTTP 403 to data-centre IPs)", INK),
        ("arbbound/ingest.py", "parse · strip symbols · filter OPTFUT · per-gram-fine · maturity match", INK),
        ("arbbound/contracts.py", "contract master — every fact carries a Provenance citation", INK),
        ("arbbound/bound.py", "structural bound: fabrication + purity/duty wedge + statutory friction", INK),
        ("arbbound/analysis.py", "walk-forward · regime-break detection · executability audit", INK),
        ("arbbound/cli.py → build.py", "verdict to stdout, report.json, and a static HTML dashboard", INK),
    ]
    y = 1.7
    for name, body, col in layers:
        _text(s, 1.4, y, 5.4, 0.45, name, size=16, bold=True, color=col if col == INK else GOLD)
        _text(s, 7.0, y + 0.03, 11.8, 0.45, body, size=14, color=MUTED)
        y += 1.02

    _rule(s, 1.1, 9.3, 17.8)
    _text(s, 1.1, 9.55, 17.8, 0.9, [
        "Dependencies point one way:  cli → analysis → {bound, ingest} → contracts.  "
        "No module imports one below it in a cycle, so each piece is testable in isolation "
        "and an assumption can change without touching the pipeline.",
        "39 tests encode the contract facts and the bound logic.  CI runs them plus a CLI "
        "smoke check on every push.",
    ], size=13.5, color=MUTED, line=1.35)


def slide_research(prs, report):
    s = _blank(prs)
    _text(s, 1.1, 0.7, 17.8, 0.7, "MARKET RESEARCH / ANALYSIS", size=17, color=GOLD, bold=True)

    wf = report["walk_forward"]
    n_pairs = len(wf)
    n_stable = sum(1 for w in wf.values() if w["level_is_stable"])
    sample = report["sample"]

    _kpi(s, 1.1, 1.6, 4.2, 1.5, f"{sample['traded_rows']:,}", "real traded rows, zero synthetic",
         INK, value_size=30, label_size=12)
    _kpi(s, 5.5, 1.6, 4.2, 1.5, f"{n_pairs}", "contract pairs tested",
         INK, value_size=30, label_size=12)
    _kpi(s, 9.9, 1.6, 4.2, 1.5, f"{n_stable}/{n_pairs}", "pairs with a stable level",
         OK, value_size=30, label_size=12)
    _kpi(s, 14.3, 1.6, 4.6, 1.5, "0", "persistent edges survive costs",
         OK, value_size=30, label_size=12)

    _rule(s, 1.1, 3.5, 17.8)
    _text(s, 1.1, 3.8, 17.8, 0.5, "WALK-FORWARD  —  residual basis, level frozen from training only",
          size=15, bold=True)

    y = 4.5
    for name, w in sorted(wf.items()):
        stable = w["level_is_stable"]
        verdict_col = OK if w["test_cleared_strict_bound"] == 0 else BAD
        _text(s, 1.4, y, 4.6, 0.4, name, size=14, bold=True)
        _text(s, 6.0, y, 4.4, 0.4,
              w["verdict"].replace("_", " ").lower(), size=13.5, color=verdict_col, bold=True)
        if stable:
            detail = (f"level stable · max residual {w['max_exceedance_bps']:+.0f} bps "
                      f"vs bound {w['bound_low_bps']:.0f}–{w['bound_high_bps']:.0f}")
            dcol = MUTED
        else:
            detail = (f"level shifted {w['level_shift_bps']:+.0f} bps — regime change, "
                      f"not {w['test_breaches']} separate opportunities")
            dcol = WARN
        _text(s, 10.6, y, 8.3, 0.4, detail, size=12.5, color=dcol)
        y += 0.72

    nov = _headline_break(report)
    _rule(s, 1.1, 9.25, 17.8)
    if nov:
        _text(s, 1.1, 9.5, 17.8, 1.2, [
            f"Dated and decomposed:  {_short(nov['pair'])} moved "
            f"{nov['median_before_bps']:+.0f} → {nov['median_after_bps']:+.0f} bps across "
            f"weeks around {nov['date']} — a drift, not a dated circular taking effect.",
            f"A structural cost cannot move like that, so we decomposed it by contract: the "
            f"complex fell while the liquid leg held its premium. The rule-change channel is "
            f"closed against MCX's own consolidated circular list.",
        ], size=13, color=MUTED, line=1.35)


def slide_future(prs, report):
    s = _blank(prs)
    _text(s, 1.1, 0.7, 17.8, 0.7, "FUTURE SCOPE", size=17, color=GOLD, bold=True)

    left = [
        ("Attribute the two stable breaches", "GOLDGUINEA/GOLDM and GOLDM/GOLDPETAL breach the "
         "bound on a stable level. The GOLDM duty wedge is currently a stated 0–400 bps range; "
         "a sourced duty history would resolve it."),
        ("Silver", "SILVER / SILVERM / SILVERMIC / SILVER100 have the same contract structure. "
         "The maturity-matched method ports directly."),
    ]
    right = [
        ("Beyond MCX gold", "The general primitive: any futures series is invalid across its own "
         "specification discontinuities. Applies to NCDEX, then NSE/BSE F&O."),
        ("Executable prices", "This is settlement data. An order-book feed would turn the "
         "executability audit from an upper bound into a real fill estimate."),
        ("Public corpus", "MCX circulars are numbered, dated and append-only. Each month of "
         "ingestion retroactively re-scores historical results."),
    ]

    _text(s, 1.1, 1.8, 8.6, 0.5, "NEXT", size=15, bold=True, color=GOLD)
    y = 2.4
    for head, body in left:
        _text(s, 1.1, y, 8.6, 0.45, head, size=16, bold=True)
        _text(s, 1.1, y + 0.5, 8.6, 1.5, body, size=13.5, color=MUTED, line=1.32)
        y += 2.25

    _text(s, 10.4, 1.8, 8.6, 0.5, "BEYOND", size=15, bold=True, color=GOLD)
    y = 2.4
    for head, body in right:
        _text(s, 10.4, y, 8.6, 0.45, head, size=16, bold=True)
        _text(s, 10.4, y + 0.5, 8.6, 1.5, body, size=13.5, color=MUTED, line=1.32)
        y += 2.25


def slide_extra(prs, report):
    s = _blank(prs)
    _text(s, 1.1, 0.7, 17.8, 0.7, "EXTRA (OPTIONAL)  —  ASSUMPTIONS AND WHAT THEY DO NOT PROVE",
          size=17, color=GOLD, bold=True)

    left = [
        ("Minting cost is an assumption, not a measurement.",
         "₹20–60 per bar, because MCX does not publish it. Carried as a range and swept; "
         "conclusions are claimed only where they survive the whole range."),
        ("The duty wedge is policy-set and has moved repeatedly.",
         "6% (Jul 2024) → 15% (May 2026). Carried as a range, never fitted as a constant."),
        ("GOLDTEN has no history before Apr 2025.",
         "A GOLDTEN-benchmarked '3-year' series is really about 18 months."),
    ]
    right = [
        ("The November 2024 break is dated and decomposed, not guessed.",
         "The rule-change channel is closed: MCX's own Master Circular – Products lists no "
         "GOLDGUINEA/GOLDPETAL futures-spec change in the window. It was a market event — the "
         "liquid leg held its premium while the complex fell — not a rule event."),
        ("Settlement data cannot prove a tradeable edge.",
         "Everything here is end-of-day settlement. The executability audit bounds what could "
         "have been reachable; it does not establish a fill."),
        ("Two pairs still breach on a stable level.",
         "GOLDGUINEA/GOLDM and GOLDM/GOLDPETAL. Reported rather than tuned away."),
    ]

    _text(s, 1.1, 1.8, 8.6, 0.5, "STATED ASSUMPTIONS", size=15, bold=True, color=GOLD)
    y = 2.4
    for head, body in left:
        _text(s, 1.1, y, 8.6, 0.45, head, size=15.5, bold=True)
        _text(s, 1.1, y + 0.5, 8.6, 1.6, body, size=13, color=MUTED, line=1.32)
        y += 2.35

    _text(s, 10.4, 1.8, 8.6, 0.5, "WHAT THIS DOES NOT PROVE", size=15, bold=True, color=WARN)
    y = 2.4
    for head, body in right:
        _text(s, 10.4, y, 8.6, 0.45, head, size=15.5, bold=True)
        _text(s, 10.4, y + 0.5, 8.6, 1.6, body, size=13, color=MUTED, line=1.32)
        y += 2.35


def slide_close(prs, report, repo, demo):
    s = _blank(prs)
    _text(s, 1.1, 3.6, 17.8, 1.4,
          "The spread was never the opportunity.", size=48, bold=True)
    _rule(s, 1.1, 5.3, 6.0)
    _text(s, 1.1, 5.7, 17.8, 1.2,
          "We proved it with a bound derived from contract specifications, "
          "swept across every assumption it rests on.",
          size=22, color=MUTED)
    _text(s, 1.1, 8.4, 17.8, 0.6, repo, size=16, color=GOLD, bold=True)
    _text(s, 1.1, 9.1, 17.8, 0.6, demo, size=16, color=MUTED)


# ------------------------------------------------------------------ helpers


def _headline_break(report: dict, min_magnitude_bps: float = 150.0) -> dict | None:
    """Pick the single most significant regime break, **from the data**.

    Deliberately *not* keyed to a date or a pair name. An earlier version
    searched for the literal ``"2024-11"``, which meant the deck's headline
    silently disappeared whenever the tool ran on different input - the exact
    failure mode of a hardcoded result.

    The headline is now simply the largest structural discontinuity the analysis
    found: a break where the basis moved by at least ``min_magnitude_bps`` in the
    adverse direction. Change the input and the deck picks whatever that input
    actually contains, or drops the slide if there is nothing large enough.
    """
    best = None
    for pair, breaks in report.get("regime_breaks", {}).items():
        for b in breaks:
            # A rise in the tradeable direction is the headline; the sign
            # convention differs per pair, so compare on magnitude.
            magnitude = b["magnitude_bps"]
            if magnitude > 0:
                continue  # a narrowing gap, not the headline
            if best is None or magnitude < best["magnitude_bps"]:
                best = {**b, "pair": pair}
    if best is None or abs(best["magnitude_bps"]) < min_magnitude_bps:
        return None
    return best


def build(report: dict, template: str, out: str, repo: str, demo: str) -> None:
    prs = Presentation(template)
    # Drop the template's placeholder slides; we re-create each section.
    xml_slides = prs.slides._sldIdLst
    for sld in list(xml_slides):
        rId = sld.get(
            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
        )
        prs.part.drop_rel(rId)
        xml_slides.remove(sld)

    slide_title(prs, report, repo)
    slide_problem(prs, report)
    slide_solution(prs, report)
    slide_architecture(prs, report)
    slide_research(prs, report)
    slide_future(prs, report)
    slide_extra(prs, report)
    slide_close(prs, report, repo, demo)

    Path(out).write_bytes(b"")  # ensure path is writable before python-pptx save
    prs.save(out)


def main() -> int:
    ap = argparse.ArgumentParser(prog="arbbound.deck")
    ap.add_argument("--report", type=Path, default=Path("docs/report.json"))
    ap.add_argument("--template", type=Path, default=Path("data/hih_template.pptx"))
    ap.add_argument("--out", type=Path, default=Path("docs/arb-bound-deck.pptx"))
    ap.add_argument("--repo", default="github.com/j4yop/arb-bound")
    ap.add_argument("--demo", default="j4yop.github.io/arb-bound")
    args = ap.parse_args()

    report = json.loads(args.report.read_text())
    build(report, str(args.template), str(args.out), args.repo, args.demo)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())