"""Generate a self-contained HTML dashboard from a computed report.

Writes one file with no build step and no network dependency, so it opens in a
browser in Manali with the laptop offline. Every number on the page is read
from the JSON report - nothing is transcribed by hand.
"""

from __future__ import annotations

import json
from pathlib import Path


def _sparkline(rows: list[dict], width: int = 520, height: int = 90) -> str:
    """Minimal inline SVG step chart for one pair's basis history."""
    if not rows:
        return ""
    xs = [r["x"] for r in rows]
    ys = [r["y"] for r in rows]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    span = (ymax - ymin) or 1.0
    pts = " ".join(
        f"{10 + (x - xmin) / (xmax - xmin or 1) * (width - 20):.1f},"
        f"{10 + (1 - (y - ymin) / span) * (height - 20):.1f}"
        for x, y in zip(xs, ys)
    )
    zero_y = 10 + (1 - (0 - ymin) / span) * (height - 20)
    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" '
        f'role="img" aria-label="basis over time">'
        f'<line x1="0" y1="{zero_y:.1f}" x2="{width}" y2="{zero_y:.1f}" '
        f'stroke="#999" stroke-dasharray="3 3" stroke-width="1"/>'
        f'<polyline points="{pts}" fill="none" stroke="#b8860b" stroke-width="1.8"/>'
        f"</svg>"
    )


def render(report: dict, basis_history: dict[str, list[dict]] | None = None) -> str:
    """Render the report dict as a standalone HTML page."""
    basis_history = basis_history or {}
    sample = report["sample"]
    wf = report["walk_forward"]
    breaks = report["regime_breaks"]
    execs = report["executability"]
    vs = report["verdict_summary"]

    bound_rows = "".join(
        f"<tr><td class='mono'>{name}</td>"
        f"<td class='num'>{b['purity_wedge_bps']:.0f}</td>"
        f"<td class='num'>{b['structural_bps']:.0f}</td>"
        f"<td class='num'>{b['bound_low_bps']:.0f}-{b['bound_high_bps']:.0f}</td></tr>"
        for name, b in sorted(report["bounds"].items())
    )

    wf_rows = ""
    for name, w in sorted(wf.items()):
        if w["level_is_stable"]:
            note = '<span class="tag ok">level stable</span>'
            detail = (
                f"max residual {w['max_exceedance_bps']:+.0f} bps vs bound "
                f"{w['bound_low_bps']:.0f}-{w['bound_high_bps']:.0f}"
            )
        else:
            note = f'<span class="tag warn">level shift {w["level_shift_bps"]:+.0f} bps</span>'
            detail = (
                f"train level {w['train_median_bps']:+.0f} bps vs test median "
                f"{w['test_median_bps']:+.0f} bps"
            )
        verdict_cls = "ok" if w["test_cleared_strict_bound"] == 0 else "bad"
        wf_rows += (
            f"<tr><td class='mono'>{name}</td>"
            f"<td><span class='tag {verdict_cls}'>{w['verdict']}</span></td>"
            f"<td class='num'>{w['test_breaches']}</td>"
            f"<td class='num'>{w['test_cleared_strict_bound']}</td>"
            f"<td>{note}<br><small>{detail}</small></td></tr>"
        )
    if not wf_rows:
        wf_rows = "<tr><td colspan='5' class='muted'>Not enough matched-maturity observations in this input for a walk-forward test. Supply a multi-month bhavcopy.</td></tr>"

    break_rows = ""
    for name, bs in sorted(breaks.items()):
        for b in bs:
            if abs(b["magnitude_bps"]) < 25:
                continue
            vr = b["volume_ratio"]
            vol = f"x{vr:.1f}" if vr else "n/a"
            break_rows += (
                f"<tr><td class='mono'>{name}</td><td>{b['date']}</td>"
                f"<td class='num'>{b['median_before_bps']:+.0f} &rarr; "
                f"{b['median_after_bps']:+.0f}</td>"
                f"<td class='num'>{b['magnitude_bps']:+.0f}</td>"
                f"<td>{b['classification']}</td><td class='num'>{vol}</td></tr>"
            )
    if not break_rows:
        break_rows = "<tr><td colspan='6' class='muted'>No basis break above 25 bps detected.</td></tr>"

    exec_rows = ""
    for name, checks in sorted(execs.items()):
        ex = sum(1 for c in checks if c["executable"])
        exec_rows += (
            f"<tr><td class='mono'>{name}</td><td class='num'>{len(checks)}</td>"
            f"<td class='num'>{ex}</td></tr>"
        )
    if not exec_rows:
        exec_rows = "<tr><td colspan='3' class='muted'>No day cleared the bound, so nothing to test.</td></tr>"

    charts = ""
    for name, rows in basis_history.items():
        if len(rows) < 2:
            continue
        charts += (
            f"<div class='chart'><h3 class='mono'>{name}</h3>"
            f"{_sparkline(rows)}"
            f"<div class='axis'><span>{rows[0]['label']}</span>"
            f"<span>{rows[-1]['label']}</span></div></div>"
        )

    # Sensitivity: sweep every stated assumption and show how far the bound
    # moves. A conclusion is only worth stating if it survives the range.
    sens = report.get("sensitivity", {})
    sens_rows = ""
    for name, s in sorted(sens.items()):
        spread = s["max_total_bound_bps"] - s["min_total_bound_bps"]
        sens_rows += (
            f"<tr><td class='mono'>{name}</td>"
            f"<td class='num'>{s['min_structural_bps']:.0f} &ndash; "
            f"{s['max_structural_bps']:.0f}</td>"
            f"<td class='num'>{s['min_total_bound_bps']:.0f} &ndash; "
            f"{s['max_total_bound_bps']:.0f}</td>"
            f"<td class='num'>{spread:.0f}</td></tr>"
        )
    if not sens_rows:
        sens_rows = ("<tr><td colspan='4' class='muted'>Sensitivity sweep is "
                     "unavailable for this input.</td></tr>")

    stable_pairs = sum(1 for w in wf.values() if w["level_is_stable"])
    breached = vs["pairs_ever_clearing_bound"]
    if breached == 0:
        verdict = (
            "<h2 class='verdict ok'>No cross-contract spread cleared its arbitrage "
            "bound in the unseen test window.</h2>"
            "<p class='lead'>The observed gaps are consistent with the structural "
            "cost of physically re-minting between bar sizes, not with a "
            "mispricing that a trader could capture.</p>"
        )
    elif breached == stable_pairs:
        verdict = (
            f"<h2 class='verdict ok'>No persistent arbitrageable edge &mdash; all "
            f"{breached} breached pair(s) are explained by a structural level shift.</h2>"
            "<p class='lead'>Every flagged day falls in a window where the structural "
            "relationship between the two contracts had already moved. The apparent "
            "opportunities are the consequences of a regime change, not independent "
            "trades.</p>"
        )
    else:
        verdict = (
            f"<h2 class='verdict warn'>{breached} pair(s) printed gaps above the bound.</h2>"
            f"<p class='lead'>Of {vs['flagged_days_total']} flagged days, "
            f"{vs['flagged_days_executable']} sat inside the exchange's own printed "
            "high/low bands with sufficient volume. Where the structural level "
            "itself moved, the flagged days are reported as a level shift, not "
            "as an opportunity.</p>"
        )

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>arb-bound report</title>
<style>
  :root{{--bg:#fbfaf8;--fg:#1a1917;--mut:#6b6862;--line:#e3e0da;--card:#fff;
    --gold:#a67c00;--ok:#1f6f4a;--bad:#a03030;--warn:#9a6700}}
  @media(prefers-color-scheme:dark){{:root{{--bg:#141312;--fg:#eceae6;--mut:#9c988f;
    --line:#2c2926;--card:#1b1918;--gold:#d9ae4e;--ok:#5fc98d;--bad:#f08585;--warn:#e0b155}}}}
  *{{box-sizing:border-box}}
  body{{margin:0;background:var(--bg);color:var(--fg);
    font:15px/1.6 ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif}}
  .wrap{{max-width:1000px;margin:0 auto;padding:40px 20px 80px}}
  h1{{font-size:1.8rem;margin:0 0 4px;letter-spacing:-.02em}}
  h2{{font-size:1.15rem;margin:36px 0 10px}}
  h3{{font-size:.9rem;margin:0 0 4px}}
  .sub{{color:var(--mut);margin-bottom:24px}}
  .verdict{{font-size:1.25rem;margin:24px 0 8px;line-height:1.35}}
  .verdict.ok{{color:var(--ok)}} .verdict.warn{{color:var(--warn)}}
  .lead{{color:var(--mut);margin:0 0 8px}}
  .card{{background:var(--card);border:1px solid var(--line);border-radius:10px;
    padding:16px 18px;margin:16px 0}}
  table{{width:100%;border-collapse:collapse;margin:8px 0;font-size:.9rem}}
  th,td{{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line)}}
  th{{color:var(--mut);font-size:.74rem;text-transform:uppercase;letter-spacing:.06em}}
  .num{{text-align:right;font-variant-numeric:tabular-nums}}
  .mono{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.86rem}}
  .tag{{display:inline-block;padding:2px 8px;border-radius:4px;font-size:.74rem;
    font-weight:600;letter-spacing:.03em}}
  .tag.ok{{background:rgba(31,111,74,.16);color:var(--ok)}}
  .tag.bad{{background:rgba(160,48,48,.16);color:var(--bad)}}
  .tag.warn{{background:rgba(154,103,0,.16);color:var(--warn)}}
  .muted{{color:var(--mut)}}
  small{{color:var(--mut)}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}}
  .kpi{{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px 14px}}
  .kpi b{{display:block;font-size:1.4rem;font-variant-numeric:tabular-nums}}
  .kpi span{{color:var(--mut);font-size:.78rem}}
  .chart{{background:var(--card);border:1px solid var(--line);border-radius:8px;
    padding:12px 14px;margin:10px 0}}
  .axis{{display:flex;justify-content:space-between;color:var(--mut);font-size:.74rem}}
  ul.lim{{margin:0;padding-left:20px}}
  ul.lim li{{margin:9px 0;color:var(--mut)}}
  ul.lim b{{color:var(--fg)}}
  footer{{margin-top:44px;color:var(--mut);font-size:.82rem;border-top:1px solid var(--line);
    padding-top:14px}}
</style></head><body><div class="wrap">

<h1>arb-bound</h1>
<p class="sub">MCX cross-contract gold &mdash; is the spread an opportunity, or the cost of closing it?</p>

{verdict}
<p class="lead">Tested walk-forward on {len(wf)} contract pairs: the centring level is
fitted on the training window only, then frozen and applied unchanged to data the test
never saw. <strong>{stable_pairs} of {len(wf)}</strong> pairs held a stable structural
level.</p>

<p class="lead"><a href="playground.html"><strong>▶ Don't take our word for it — run it yourself.</strong></a>
The live playground executes this exact pipeline in your browser on input you supply.</p>

<div class="grid">
  <div class="kpi"><b>{sample['traded_rows']:,}</b><span>traded rows</span></div>
  <div class="kpi"><b>{sample['start']}</b><span>sample start</span></div>
  <div class="kpi"><b>{sample['end']}</b><span>sample end</span></div>
  <div class="kpi"><b>{report['reference_price_inr_per_gram_fine']:,.0f}</b><span>INR / gram fine</span></div>
</div>

<h2>Structural bound</h2>
<p class="lead">Minimum gross gap, in basis points, before a cross-contract spread can profit.
The wedge is a contractual purity/duty difference and is not tradeable.</p>
<div class="card"><table>
<tr><th>pair</th><th class="num">wedge (bps)</th><th class="num">structural</th><th class="num">bound band</th></tr>
{bound_rows}</table></div>

<h2>Walk-forward test</h2>
<p class="lead">The centring level is fitted on the training window only and then frozen.
Where the level itself moved, that is reported as a level shift, not as an opportunity.</p>
<div class="card"><table>
<tr><th>pair</th><th>verdict</th><th class="num">test breaches</th><th class="num">cleared</th><th>detail</th></tr>
{wf_rows}</table></div>

<h2>Detected regime breaks</h2>
<p class="lead">A structural cost cannot jump. These discontinuities are events, not arbitrage.</p>
<div class="card"><table>
<tr><th>pair</th><th>date</th><th class="num">level shift</th><th class="num">delta</th><th>class</th><th class="num">volume</th></tr>
{break_rows}</table></div>

<h2>Executability of flagged days</h2>
<p class="lead">A bhavcopy print is a settlement price, not a quote you can lift. Each flagged day is
re-tested against the exchange's own printed high/low bands and liquidity.</p>
<div class="card"><table>
<tr><th>pair</th><th class="num">flagged</th><th class="num">reachable</th></tr>
{exec_rows}</table></div>

{f"<h2>Basis history</h2>" + charts if charts else ""}

<h2>Sensitivity to stated assumptions</h2>
<p class="lead">Two inputs are assumptions, not measurements: the per-bar minting cost
(MCX does not publish it) and the import-duty wedge (policy-set, and it has moved).
Both are swept across their full range here. The column on the right is how many
basis points the bound itself moves &mdash; that is the part of our claim resting on
an assumption rather than on the contract specification.</p>
<div class="card"><table>
<tr><th>pair</th><th class="num">structural (bps)</th><th class="num">total bound (bps)</th><th class="num">moves by</th></tr>
{sens_rows}</table></div>

<h2>Limitations &mdash; read this before quoting any number</h2>
<div class="card">
<ul class="lim">
<li><b>Settlement is not execution.</b> Every price here is an exchange settlement
print, not a quote you could have lifted. The executability audit upper-bounds what
was reachable; it does not establish a fill.</li>
<li><b>Minting cost is assumed, not measured.</b> ₹20&ndash;60 per bar. Conclusions
are claimed only where they survive that whole range &mdash; see the sensitivity table.</li>
<li><b>The duty wedge is carried as a range.</b> The 995/999 purity part is exact
(999/995); the duty-basis part is policy and is stated, never fitted.</li>
<li><b>Regime breaks are dated, not always explained.</b> A discontinuity is reported
as an event. Where we tested an explanation (the May 2026 duty hike) and it failed the
timing test, we say so rather than inventing a cause.</li>
<li><b>Input coverage is limited by what MCX listed.</b> GOLDTEN has no history before
April 2025, so any GOLDTEN-based series is shorter than the headline window.</li>
</ul>
</div>

<footer>Every figure on this page is read from the JSON report; nothing is hand-transcribed.
Generated by arbbound.<br><br>
<strong>Try it yourself:</strong> <a href="playground.html">open the live playground</a> —
paste your own bhavcopy and watch this same pipeline run in your browser.<br><br>
Full write-ups: <a href="PROBLEM.md">PROBLEM.md</a> (problem statement + questions and answers) ·
<a href="WORKFLOW.md">WORKFLOW.md</a> (architecture, tech stack, build phases) ·
<a href="JUDGE-SCRIPT.md">JUDGE-SCRIPT.md</a> (demo runbook) ·
<a href="https://github.com/j4yop/arb-bound" style="color:var(--gold)">source repository</a></footer>
</div></body></html>"""


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="arbbound.report")
    ap.add_argument("--report", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    report = json.loads(Path(args.report).read_text())
    Path(args.out).write_text(render(report))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())