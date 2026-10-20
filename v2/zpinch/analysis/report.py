"""
The run report as HTML (v3 phase 5): the curated write-up first, then the
figures, then the data appendix. One builder serves two readers:

    standalone=True   a self-contained .html file (export zip, --report):
                      figures embedded as base64 PNG, its own stylesheet,
                      light and dark themes, no network access needed
    standalone=False  the GUI report panel (Qt's QTextBrowser): Qt renders
                      a subset of HTML 4, so no stylesheet or <details>, and
                      figures are named resources the panel registers

    from zpinch.analysis import features as FE, report as RP
    from zpinch.analysis.explain import analyse
    h, meta = FE.load_npz("dataset/sweep-2026-10-19/runs/r00273.npz")
    r = analyse(h, meta)
    open("r00273.html", "w").write(RP.html(r, RP.figures(h, r, meta)))
"""

import base64
import csv
import html as _html
import io
import math

import numpy as np
from matplotlib.figure import Figure

from . import features as FE
from .explain import NAMES, STORES

# one colour per phase kind on the mode plot; the same tab10 colours as the
# rest of the diagnostics so the report and the live plots look like one tool
PHASE_COLOURS = {
    "kink_growth": "tab:orange", "saturated_kink": "tab:green", "kink_disruption": "tab:red",
    "sausage": "tab:purple", "gravity_sag": "tab:brown", "radiative_collapse": "tab:blue",
    "resistive_diffusion": "tab:olive", "compression": "tab:cyan", "kink_growing": "tab:orange",
    "quiescent": "tab:gray",
}

FIGURE_CAPTIONS = {
    "modes.png": "Instability amplitudes, both relative to the column's mean radius: m = 1 is how far "
                 "the centre line wanders (the kink), m = 0 how much the radius varies along the "
                 "column (the sausage). Shaded bands are the phases in the timeline below.",
    "energy.png": "Energy stores. The dotted red line is what the total should be from the circuit "
                  "input, radiation and floor corrections; the black total sitting on it means the "
                  "energy bookkeeping closes.",
    "column.png": "The pinch column: its radius, and the temperature and density on the axis, all "
                  "relative to their starting values.",
}


# =====================================================
# figures
# =====================================================

def figures(h, r, meta):
    """{name: PNG bytes} for the report: modes (with phases), energy, column."""
    from ..diagnostics import plot_energy, plot_modes, plot_pinch
    a0 = meta["setup"]["pinch_radius"]
    h = {k: np.asarray(v) for k, v in h.items()}

    def modes(ax):
        plot_modes(ax, h)
        for p in r["phases"]:
            ax.axvspan(p["t_start"], p["t_end"], color=PHASE_COLOURS.get(p["name"], "tab:gray"),
                       alpha=0.12, lw=0)
            ax.text(0.5 * (p["t_start"] + p["t_end"]), 0.97, NAMES.get(p["name"], p["name"]),
                    transform=ax.get_xaxis_transform(), ha="center", va="top", fontsize=6, color="0.3")

    out = {}
    for name, draw in (("modes.png", modes), ("energy.png", lambda ax: plot_energy(ax, h)),
                       ("column.png", lambda ax: plot_pinch(ax, h, a0))):
        fig = Figure(figsize=(6.4, 3.0), dpi=130)
        draw(fig.add_subplot(111))
        fig.tight_layout(pad=0.5)
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        out[name] = buf.getvalue()
    return out


# =====================================================
# small helpers
# =====================================================

def _e(x):
    return _html.escape(str(x))


def _num(x, fmt="{:.4g}"):
    if isinstance(x, (bool, np.bool_)):
        return "yes" if x else "no"
    if isinstance(x, (int, float, np.floating, np.integer)):
        x = float(x)
        if math.isnan(x):
            return "n/a"
        if math.isinf(x):
            return "infinite" if x > 0 else "-infinite"
        return fmt.format(x)
    return str(x)


def _table(head, rows, cls=""):
    c = f' class="{cls}"' if cls else ""
    out = [f"<table{c}><tr>" + "".join(f"<th>{_e(h)}</th>" for h in head) + "</tr>"]
    for row in rows:
        out.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>")
    return "\n".join(out) + "</table>"


def _section(title, body, standalone, open_=True):
    """A collapsible block in the browser, a plain heading in Qt."""
    if not standalone:
        return f"<h3>{_e(title)}</h3>\n{body}"
    o = " open" if open_ else ""
    return f"<details{o}><summary>{_e(title)}</summary>\n{body}\n</details>"


def run_line(f):
    return (f"t = 0 to {f['t_final']:.2f} · I = {f['current']:.3g} · B_z = {f['axial_field']:.3g} · "
            f"L = {f['length']:.3g} · η = {f['resistivity']:.2g} · ν = {f['viscosity']:.2g} · "
            f"C = {f['cooling']:.2g} · g = {f['gravity']:.2g}")


# =====================================================
# the report
# =====================================================

def body(r, meta=None, img=lambda name: name, standalone=True):
    """The report's HTML body; img(name) gives each figure's src."""
    from .model import format_prediction
    from .writeup import match_text
    f, w = r["features"], r.get("writeup")
    L = []

    # ---- header ----
    L.append(f"<h1>{_e(w['title'] if w else r['label_name'])}</h1>")
    tag = f"<b>Outcome: {_e(r['label_name'])}</b>"
    if r["secondary"]:
        tag += " &nbsp;(also: " + _e(", ".join(NAMES.get(s, s) for s in r["secondary"])) + ")"
    tag += f" &nbsp;·&nbsp; confidence: {_e(r['confidence'])}"
    L.append(f'<p class="tag">{tag}</p>')
    L.append(f'<p class="meta">{_e(run_line(f))}</p>')
    if r["borderline"]:
        L.append(f'<p class="meta">Borderline: {_e("; ".join(r["borderline"]))}</p>')
    warnings = r["notes"] + r["health"] + ([w["note"]] if w and w["note"] else [])
    for note in warnings:
        L.append(f'<p class="warn">⚠ {_e(note)}</p>')

    # ---- the write-up ----
    if w:
        for head, text in w["sections"].items():
            L.append(f"<h2>{_e(head)}</h2>\n<p>{_e(text)}</p>")
        L.append(f'<p class="meta">Where this text comes from: {_e(match_text(w))}</p>')
    else:
        L.append("<p>No curated write-up exists for this outcome; the timeline and causes below "
                 "are the analysis in full.</p>")

    # ---- figures ----
    L.append("<h2>Figures</h2>")
    for name, cap in FIGURE_CAPTIONS.items():
        L.append(f'<p class="fig"><img src="{img(name)}" width="540" alt="{_e(name)}"><br>'
                 f'<span class="meta">{_e(cap)}</span></p>')

    # ---- data appendix ----
    L.append("<h2>Data appendix</h2>")
    rows = [(f"{p['t_start']:.2f}", f"{p['t_end']:.2f}", _e(NAMES.get(p["name"], p["name"])), _e(p["text"]))
            for p in r["phases"]]
    L.append(_section("Timeline", _table(("from t", "to t", "phase", "what the diagnostics show"), rows),
                      standalone))
    items = "".join(f"<li>{_e(c['text'])}</li>" for c in r["causes"])
    L.append(_section("Causes in detail (energy bookkeeping, phase by phase)", f"<ul>{items}</ul>", standalone))
    rows = [("✓" if c["agree"] else "✗", _e(c["name"]), _num(c["value"]), _e(c["expect"]), _e(c["note"]))
            for c in r["criteria"]]
    L.append(_section("Stability criteria (theory against this run)",
                      _table(("", "criterion", "value", "theory expects", "this run"), rows, "crit"),
                      standalone))

    ml = r.get("ml")
    if ml:
        rows = []
        a, b = ml.get("run_classifier"), ml.get("outcome_predictor")
        if a:
            verdict = ("agrees with the rules" if ml["agrees"] else
                       f"disagrees with the rules ({100 * ml['rule_label_prob']:.0f} % for "
                       f"{NAMES[r['label']]}): a borderline or unusual run")
            rows.append(("run classifier (a), from the history", _e(format_prediction(a, NAMES)), _e(verdict)))
        if b:
            rows.append(("outcome predictor (b), from the settings alone", _e(format_prediction(b, NAMES)),
                         "what the model expected before the run started"))
        L.append(_section("Machine-learning view (a cross-check: the causes come from physics)",
                          _table(("model", "prediction", "comment"), rows), standalone))

    e = r["energy_total"]
    rows = [(k, f"{e[k]:+.3f}") for k in STORES] + [
        ("circuit input", f"{e['injected']:+.3f}"), ("radiated", f"{e['radiated']:.3f}"),
        ("floor corrections", f"{e['floor']:.3f}")]
    L.append(_section("Energy budget, whole run (fractions of the starting energy E0)",
                      _table(("store", "change"), rows), standalone))

    if meta:
        rows = [(f"setup.{k}", _e(_num(v))) for k, v in meta["setup"].items()]
        rows += [(f"live.{k}", _e(_num(v))) for k, v in meta["live"].items()]
        L.append(_section("Parameters", _table(("parameter", "value"), rows), standalone, open_=False))
    units = {name: (unit, desc) for name, unit, desc in FE.FEATURES}
    rows = [(_e(k), _e(_num(v)), _e(units.get(k, ("", ""))[0]), _e(units.get(k, ("", ""))[1]))
            for k, v in f.items()]
    L.append(_section(f"All {len(f)} features (what the models see)",
                      _table(("feature", "value", "unit", "meaning"), rows), standalone, open_=False))

    grid = (meta or {}).get("derived", {}).get("grid")
    L.append(f'<p class="meta">Analysis {_e(r["version"])}'
             + (f" · grid {'×'.join(map(str, grid))}" if grid else "")
             + (f" · statistics from {_e(w['stats_source'])}" if w and w.get("stats_source") else "")
             + ". Z-pinch MHD v3.</p>")
    return "\n".join(L)


STYLE = """
:root { --bg: #fbfbf9; --fg: #1d1f21; --muted: #5f6368; --rule: #d9d9d4; --card: #ffffff;
        --warn-bg: #fff4e0; --warn-fg: #7a4a00; --ok: #1e7b34; --bad: #b3261e; --accent: #2b5fab; }
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) { --bg: #16181a; --fg: #e6e6e3; --muted: #a0a4a8; --rule: #33373b;
        --card: #1e2124; --warn-bg: #3a2c12; --warn-fg: #f3c777; --ok: #6fcf88; --bad: #f28b82; --accent: #8ab4f8; }
}
:root[data-theme="dark"] { --bg: #16181a; --fg: #e6e6e3; --muted: #a0a4a8; --rule: #33373b;
        --card: #1e2124; --warn-bg: #3a2c12; --warn-fg: #f3c777; --ok: #6fcf88; --bad: #f28b82; --accent: #8ab4f8; }
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--fg);
       font: 16px/1.6 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
main { max-width: 820px; margin: 0 auto; padding: 32px 16px 64px; }
h1 { font-size: 1.7rem; line-height: 1.25; margin: 0 0 8px; }
h2 { font-size: 1.2rem; margin: 32px 0 6px; padding-top: 8px; border-top: 1px solid var(--rule); }
p { margin: 6px 0 12px; }
.tag { font-size: 1rem; }
.meta { color: var(--muted); font-size: 0.88rem; }
.warn { background: var(--warn-bg); color: var(--warn-fg); padding: 8px 12px; border-radius: 6px; }
.fig img { max-width: 100%; height: auto; border-radius: 6px; background: #fff; }
details { margin: 10px 0; background: var(--card); border: 1px solid var(--rule); border-radius: 8px;
          padding: 4px 12px; }
summary { cursor: pointer; font-weight: 600; padding: 6px 0; }
.scroll { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 0.86rem; margin: 6px 0 10px; }
th, td { text-align: left; vertical-align: top; padding: 4px 8px; border-bottom: 1px solid var(--rule); }
th { color: var(--muted); font-weight: 600; }
td:first-child { white-space: nowrap; }
.crit td:first-child { font-weight: 700; }
a { color: var(--accent); }
"""


def html(r, images, meta=None, title=None):
    """A standalone .html report with the figures embedded."""
    def img(name):
        return "data:image/png;base64," + base64.b64encode(images[name]).decode() if name in images else ""
    text = body(r, meta, img, standalone=True)
    # tables can be wider than a phone: let each scroll inside its own box
    text = text.replace("<table", '<div class="scroll"><table').replace("</table>", "</table></div>")
    title = title or f"Run report: {r['label_name']}"
    return (f'<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f"<title>{_e(title)}</title>\n<style>{STYLE}</style>\n</head>\n"
            f"<body>\n<main>\n{text}\n</main>\n</body>\n</html>\n")


# Qt's rich-text engine understands this much CSS; the palette (light or
# dark desktop theme) supplies the colours, so none are set here except the
# warning and the muted captions
QT_STYLE = """
h1 { font-size: 17pt; margin-bottom: 4px; }
h2 { font-size: 13pt; margin-top: 16px; margin-bottom: 2px; }
h3 { font-size: 11pt; margin-top: 12px; margin-bottom: 2px; }
p { margin-top: 2px; margin-bottom: 8px; }
.meta { color: #808080; font-size: 9pt; }
.warn { color: #c77700; }
th { text-align: left; color: #808080; padding: 2px 8px 2px 0px; }
td { padding: 2px 8px 2px 0px; }
"""


def features_csv(r):
    """name, value, unit, meaning: one row per feature (researcher export)."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(("feature", "value", "unit", "meaning"))
    units = {name: (unit, desc) for name, unit, desc in FE.FEATURES}
    for k, v in r["features"].items():
        w.writerow((k, f"{v:.10g}" if isinstance(v, float) else v, *units.get(k, ("", ""))))
    return buf.getvalue()


def bundle(h, meta):
    """
    Everything the GUI and the export need from one analysis: the result,
    its meta, the plain-text report, the standalone HTML, the feature CSV
    and the figure PNGs (the panel builds its own HTML with body(), naming
    the figures). Built in the physics worker so the window never waits.
    """
    from .explain import analyse, format_report
    r = analyse(h, meta)
    images = figures(h, r, meta)
    return {"report": r, "meta": meta, "text": format_report(r), "html": html(r, images, meta),
            "images": images, "csv": features_csv(r)}
