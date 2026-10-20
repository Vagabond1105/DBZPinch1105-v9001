"""
Curated write-ups (plan section 7, Phase 4).

The report's student-facing prose comes from a fixed library of hand-written
entries in library/*.md, never from free text generation, so it cannot
invent physics. Each entry covers one outcome class, either in general or in
one parameter regime ("saturated kink just inside the Kruskal-Shafranov
limit"), and has three sections: What happened, Why, Try next. The text has
{placeholders} that are filled with this run's numbers.

Entry format (front matter, then markdown sections):

    ---
    id: saturated-kink-marginal
    class: saturated_kink
    title: Saturated kink just inside the Kruskal-Shafranov limit
    regime: nq_seed 0.5..1.0; gravity 0..0.3
    example: r00843                       # a sweep run this entry was checked on
    preset: Saturated kink (Bz = 0.6)     # GUI preset that reproduces it (optional)
    compare: nq_seed 0.5..1.0; gravity 0..0.3; cooling 0..0.3   # sweep runs the text quotes (default: regime)
    priority: 0                           # breaks ties between equally specific entries
    reviewed: data-checked                # no | data-checked | yes
    ---
    ## What happened
    The column bent into a corkscrew ... {m1_sat:.2f} radii ...

Regime keys are feature names (features.FEATURES), with closed intervals
lo..hi (inf allowed). An entry with no regime is the class's general entry;
every class has exactly one (tests/test_library.py).

Selection: among entries of the run's class whose box contains the run, the
most specific (most regime keys, then priority) wins. A regime entry is never
used outside its box, because its text states regime facts ("you had no
axial field"); the report names the nearest one and how far off the run was.

Numbers quoted from the sweep ("44 of 61 runs in this regime disrupted") are
not typed into the text: they are {regime_*} placeholders filled from
library/stats.json, which tools/library.py regenerates from the labelled
sweep, so they stay true when the dataset grows. They count the runs inside
the entry's compare box, which is usually the regime box narrowed to runs
where nothing else interferes (gravity and cooling would otherwise mix
sagging and collapsing runs into a Kruskal-Shafranov count). The text says
which runs it is quoting.

reviewed: "no" entries are never used. "data-checked" means every claim was
checked against the sweep statistics and the example run; "yes" means a
physicist has also read it. The report says which.
"""

import json
import math
import os
import string

from . import features as FE
from . import rules as RU

LIBRARY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "library")
STATS_PATH = os.path.join(LIBRARY_DIR, "stats.json")
EXAMPLES_PATH = os.path.join(LIBRARY_DIR, "examples.json")
SECTIONS = ("What happened", "Why", "Try next")
REVIEW_STATES = {
    "data-checked": "checked against the sweep data; not yet reviewed by a physicist",
    "yes": "reviewed by a physicist",
}

# Kruskal-Shafranov targets for the "Try next" suggestions, from the sweep's
# n q table (tools/analyse.py summary, runs without gravity or cooling):
# below 0.25 every run disrupted, 0.5-1 every run saturated, above 1.5 no run
# grew a kink.
NQ_DISRUPT = 0.2       # inside the all-disrupt band
NQ_SATURATE = 0.75     # middle of the all-saturate band
NQ_STABLE = 1.5        # the no-kink band starts here; at the default length (1.5)
                       # and radius this needs B_z = 1.49, just inside the slider
# "Try next" for a column that should diffuse: every resistive-diffusion run
# in the sweep had eta >= 3.5e-3 (the rule needs a^2 / eta <= 6 for a = 0.12,
# i.e. eta >= 2.4e-3, plus a core that halves), so 5e-3 is safely inside.
ETA_DIFFUSE = 5e-3


# =====================================================
# loading
# =====================================================

def _parse_regime(text):
    box = {}
    for part in filter(None, (p.strip() for p in text.split(";"))):
        key, rng = part.split()
        lo, hi = rng.split("..")
        box[key] = (float(lo), float(hi))
    return box


def parse(text, path="<string>"):
    """One entry from its file text."""
    if not text.startswith("---\n"):
        raise ValueError(f"{path}: no front matter")
    head, body = text[4:].split("\n---\n", 1)
    e = {"path": path, "regime": {}, "compare": None, "example": None, "preset": None, "priority": 0}
    for line in head.splitlines():
        line = line.split(" #", 1)[0].rstrip()
        if not line:
            continue
        key, value = (s.strip() for s in line.split(":", 1))
        if key in ("regime", "compare"):
            e[key] = _parse_regime(value)
        elif key == "priority":
            e["priority"] = int(value)
        else:
            e[key] = value or None
    if e["compare"] is None:
        e["compare"] = e["regime"]
    e["sections"] = {}
    for chunk in ("\n" + body).split("\n## ")[1:]:
        heading, _, txt = chunk.partition("\n")
        e["sections"][heading.strip()] = " ".join(txt.split())   # one paragraph per section
    for key in ("id", "class", "title", "reviewed"):
        if not e.get(key):
            raise ValueError(f"{path}: missing '{key}'")
    return e


def load(include_unreviewed=False):
    """Every entry in library/, in file-name order."""
    out = []
    for name in sorted(os.listdir(LIBRARY_DIR)):
        if name.endswith(".md") and not name.startswith("README"):
            path = os.path.join(LIBRARY_DIR, name)
            with open(path) as fh:
                e = parse(fh.read(), path)
            if include_unreviewed or e["reviewed"] in REVIEW_STATES:
                out.append(e)
    return out


def load_stats():
    try:
        with open(STATS_PATH) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def load_examples(entries=None):
    """
    The textbook runs: {entry id: example} for every in-use entry whose
    example is in examples.json (tools/library.py check), each with the
    entry's title and class added. Ordered by class, then title.
    """
    entries = load() if entries is None else entries
    try:
        with open(EXAMPLES_PATH) as fh:
            ex = json.load(fh)
    except (OSError, ValueError):
        return {}
    out = {e["id"]: {**ex[e["id"]], "title": e["title"], "class": e["class"]}
           for e in entries if e["id"] in ex}
    return dict(sorted(out.items(), key=lambda kv: (kv[1]["class"], kv[1]["title"])))


# =====================================================
# selection
# =====================================================

def box_distance(f, regime):
    """
    0 inside the box; otherwise the largest miss over the regime keys,
    relative to the interval width (or to the bound itself for a point or
    open interval), so 0.2 means "20 % outside".
    """
    worst = 0.0
    for key, (lo, hi) in regime.items():
        x = f.get(key, math.nan)
        if not isinstance(x, (int, float)) or math.isnan(x):
            return math.inf
        if lo <= x <= hi:
            continue
        miss = lo - x if x < lo else x - hi
        if math.isfinite(hi) and hi > lo:
            width = hi - lo
        else:                                   # a point (B_z 0..0) or open-ended box
            width = max(abs(lo), abs(hi) if math.isfinite(hi) else 0.0) or 1.0
        worst = max(worst, miss / width)
    return worst


def select(label, f, entries=None):
    """
    (entry, match) for a run with this label and these features. match =
    {kind: "regime" | "general", nearest: id or None, distance}. Returns
    (None, None) if the class has no entry.
    """
    entries = load() if entries is None else entries
    own = [e for e in entries if e["class"] == label]
    if not own:
        return None, None
    inside = [e for e in own if box_distance(f, e["regime"]) == 0.0]
    best = max(inside, key=lambda e: (len(e["regime"]), e["priority"])) if inside else None
    if best is None or not best["regime"]:
        regimes = [e for e in own if e["regime"]]
        near = min(regimes, key=lambda e: box_distance(f, e["regime"])) if regimes else None
        general = best or next((e for e in own if not e["regime"]), own[0])
        return general, {"kind": "general", "nearest": near["id"] if near else None,
                         "distance": box_distance(f, near["regime"]) if near else None}
    return best, {"kind": "regime", "nearest": best["id"], "distance": 0.0}


# =====================================================
# filling in the numbers
# =====================================================

class _Absent:
    """Stands in for nan / inf so a template prints a word, not 'nan'."""

    def __init__(self, word):
        self.word = word

    def __format__(self, spec):
        return self.word


def _clean(x):
    if isinstance(x, float):
        if math.isnan(x):
            return _Absent("n/a")
        if math.isinf(x):
            return _Absent("infinite" if x > 0 else "-infinite")
    return x


def _bz_for_nq(f, meta, target):
    """
    Axial field that puts the seeded helix at n q = target, other settings
    unchanged. q is proportional to B_z, so it is target / (n * q per unit
    B_z); q per unit B_z comes from the same formula as the GUI (grid-rounded
    column length).
    """
    if meta and "setup" in meta and "live" in meta:
        q1 = FE.derived_from_params({**meta["setup"], "axial_field": 1.0}, meta["live"])["q_a"]
    else:
        q1 = 2.0 * math.pi * f["pinch_radius"] / f["length"]
    return target / (f["seed_n"] * q1)


def values(r, meta=None, stats=None, entry=None):
    """Every placeholder a template may use, for one analysed run."""
    f = r["features"]
    from .explain import NAMES, helix_sentence, kink_time_needed
    v = {k: _clean(x) for k, x in f.items()}
    for cls in sorted(r["evidence"], key=lambda c: c == r["label"]):   # the label's own evidence last
        v.update({k: _clean(x) for k, x in r["evidence"][cls].items()})
    for p in r["phases"]:
        v[p["name"] + "_start"], v[p["name"] + "_end"] = p["t_start"], p["t_end"]
    for k, x in r["energy_total"].items():
        if k not in ("t0", "t1"):
            v["e_" + k] = 100.0 * x                       # whole run, % of E0
    v.update({
        "wall_a": 0.5 / f["pinch_radius"],                # wall distance in column radii
        "seed_n": int(f["seed_n"]),
        "helix": helix_sentence(f),                       # explain.py: which helix carried the kink
        "q_axis": f["q_a"] / 2.0,                         # Bennett profile: q(0) = q(a) / 2
        "nq_axis": f["nq_seed"] / 2.0,
        "kinetic_max_pct": 100.0 * f["kinetic_max"],
        "radiated_pct": 100.0 * f["radiated"],
        "d_thermal_pct": 100.0 * f["d_thermal"],
        "bz_disrupt": _bz_for_nq(f, meta, NQ_DISRUPT),
        "bz_saturate": _bz_for_nq(f, meta, NQ_SATURATE),
        "bz_stable": _bz_for_nq(f, meta, NQ_STABLE),
        "nq_disrupt": NQ_DISRUPT,
        "nq_saturate": NQ_SATURATE,
        "nq_stable": NQ_STABLE,
        "eta_diffuse": ETA_DIFFUSE,
        "cooling_half": f["cooling"] / 2.0,
        # the rules' thresholds, so the text never retypes them
        "grown": RU.GROWN, "nonlinear": RU.NONLINEAR, "mixed_radius": FE.MIXED_RADIUS,
        "collapse_t": RU.COLLAPSE_T, "collapse_rho": RU.COLLAPSE_RHO, "sag": RU.SAG, "disrupt_delay": RU.DISRUPT_DELAY,
    })
    v["t_kink_needed"] = kink_time_needed(f)

    st = (stats or {}).get("entries", {}).get(entry["id"]) if entry else None
    if st:
        n, same = st["runs"], st["labels"].get(r["label"], 0)
        v.update(regime_runs=n, regime_same=same,
                 regime_same_pct=100.0 * same / n if n else _Absent("n/a"),
                 regime_mix=", ".join(f"{NAMES[k].lower()} {c}"
                                      for k, c in sorted(st["labels"].items(), key=lambda x: -x[1])))
    if stats:
        v["sweep_runs"] = stats["runs"]
        v["class_runs"] = stats["classes"].get(r["label"], 0)
    return v


def placeholders(entry):
    """Field names used by an entry's text."""
    names = set()
    for txt in entry["sections"].values():
        names.update(name.split(".")[0].split("[")[0]
                     for _, name, _, _ in string.Formatter().parse(txt) if name)
    return names


def fill(entry, vals):
    return {h: entry["sections"][h].format_map(vals) for h in SECTIONS if h in entry["sections"]}


def _range_note(entry, vals):
    """
    A suggested B_z beyond the GUI slider. The seed's helix has n ~ L_z / 5a,
    so n q ~ 2 pi B_z / 5 whatever the length or radius; only the rounding of
    n moves it. At the sweep's radius the worst rounding needs B_z = 1.49 for
    n q = 1.5, but a wide column (a ~ 0.14 at L_z = 1) rounds n down to 1 and
    would need ~1.8, which the slider cannot reach.
    """
    from ..params import SetupParams
    from dataclasses import fields
    hi = next(f.metadata["hi"] for f in fields(SetupParams) if f.name == "axial_field")
    over = sorted(k for k in placeholders(entry) if k.startswith("bz_") and vals[k] > hi)
    if over:
        return (f"a suggested B_z ({', '.join(f'{vals[k]:.2f}' for k in over)}) is above the slider maximum "
                f"{hi:g}: with this column's length and radius the axial field alone cannot reach that n q")
    return None


def writeup(r, meta=None, entries=None, stats=None):
    """
    The curated write-up for an analysed run (explain.analyse output), or
    None if the library has nothing for its class. Falls back to the general
    entry if a regime entry cannot be filled (a placeholder it needs is
    missing for this run).
    """
    entries = load() if entries is None else entries
    stats = load_stats() if stats is None else stats
    entry, match = select(r["label"], r["features"], entries)
    if entry is None:
        return None
    note = None
    try:
        sections = fill(entry, values(r, meta, stats, entry))
    except (KeyError, ValueError, TypeError) as err:
        general = next((e for e in entries if e["class"] == r["label"] and not e["regime"]), None)
        if general is None or general is entry:
            return None
        note = f"entry {entry['id']} could not be filled ({err!r}); using the general entry"
        entry, match = general, {"kind": "general", "nearest": entry["id"], "distance": 0.0}
        sections = fill(entry, values(r, meta, stats, entry))
    note = note or _range_note(entry, values(r, meta, stats, entry))
    st = (stats or {}).get("entries", {}).get(entry["id"])
    return {
        "id": entry["id"], "title": entry["title"], "class": entry["class"],
        "sections": sections, "match": match, "note": note,
        "reviewed": entry["reviewed"], "review_text": REVIEW_STATES[entry["reviewed"]],
        "regime": {k: list(b) for k, b in entry["regime"].items()},
        "compare": {k: list(b) for k, b in entry["compare"].items()},
        "example": entry["example"], "preset": entry["preset"],
        "regime_stats": st, "stats_source": (stats or {}).get("source"),
    }


def match_text(w):
    """One line on how the entry was chosen (report appendix)."""
    m = w["match"]
    if m["kind"] == "regime":
        s = f"library entry '{w['id']}': this run lies inside its parameter box"
    elif m["nearest"]:
        s = (f"general entry '{w['id']}': no regime entry covers this run (nearest '{m['nearest']}', "
             f"{100 * m['distance']:.0f} % outside its box)" if math.isfinite(m["distance"]) else
             f"general entry '{w['id']}': no regime entry covers this run")
    else:
        s = f"general entry '{w['id']}' (the only entry for this class)"
    if w["regime_stats"]:
        s += f"; sweep runs in this box: {w['regime_stats']['runs']}"
    return s + f"; {w['review_text']}."
