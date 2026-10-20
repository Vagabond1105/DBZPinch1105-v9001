"""
Why did the run do what it did? (plan section 2, "causal explanation")

Causes come from physics bookkeeping, never from a model:
  * stability criteria from the starting parameters (Kruskal-Shafranov q,
    Kadomtsev margin, Lundquist number, resistive and cooling times), each
    compared with what actually happened;
  * the energy budget: which store (magnetic, gravitational, circuit,
    thermal) paid for the motion and the heat, measured over the phase
    where it happened.

The output is a plain dict (JSON-safe) plus format_report() for a text
version. The student-facing prose on top is a curated write-up from
writeup.py (Phase 4), filled with the numbers computed here; the causes and
criteria below it are the data appendix.
"""

import math
import textwrap

import numpy as np

from . import features as FE
from . import rules as RU

ANALYSIS_VERSION = "1.1 (phase 4, rules + curated write-ups)"

NAMES = {
    "quiescent": "Quiescent column",
    "saturated_kink": "Saturated helical kink",
    "kink_disruption": "Kink -> disruption",
    "sausage": "Sausage-dominated",
    "gravity_sag": "Gravity sag",
    "radiative_collapse": "Radiative collapse",
    "resistive_diffusion": "Resistive diffusion",
    "compression": "Compression",
    "kink_growth": "Kink growth",
    "kink_growing": "Kink still growing",
}

STORES = ("kinetic", "magnetic", "thermal", "potential")

# Typical kink timing in the sweep (32^3, runs where it grew): growth starts
# at t ~ 0.19 and runs at ~0.79 per Alfven time. Used only to tell a user who
# analyses early whether the kink has had time to show yet.
KINK_ONSET = 0.19
KINK_RATE_TA = 0.79


def kink_time_needed(f):
    """Rough time for a kink to reach rules.GROWN from the 0.02 seed."""
    return KINK_ONSET + math.log(RU.GROWN / 0.02) * f["t_alfven"] / KINK_RATE_TA


# =====================================================
# energy bookkeeping
# =====================================================

def energy_between(h, t0, t1):
    """Changes of each store and each source/sink between two times, in units of E0."""
    t = np.asarray(h["t"])
    E0 = float(h["total"][0])
    i0 = int(np.clip(np.searchsorted(t, t0), 0, len(t) - 1))
    i1 = int(np.clip(np.searchsorted(t, t1), 0, len(t) - 1))
    d = {k: float(h[k][i1] - h[k][i0]) / E0 for k in STORES}
    for k in ("injected", "radiated", "floor"):
        d[k] = float(h[k][i1] - h[k][i0]) / E0
    d["t0"], d["t1"] = float(t[i0]), float(t[i1])
    return d


def _pct(x):
    return f"{100 * x:.0f} %" if abs(x) >= 0.01 else f"{100 * x:.1f} %"


def who_paid(d):
    """
    Plain-language energy flow over a window. Sources are stores that fell
    plus the circuit if it put energy in; sinks are stores that rose plus
    radiation. Only flows above 0.5 % of E0 are named.
    """
    src, snk = [], []
    names = {"kinetic": "flow (kinetic)", "magnetic": "the magnetic field",
             "thermal": "heat (thermal)", "potential": "gravitational energy"}
    for k in STORES:
        if d[k] < -0.005:
            src.append((names[k], -d[k]))
        elif d[k] > 0.005:
            snk.append((names[k], d[k]))
    if d["injected"] > 0.005:
        src.append(("the drive circuit", d["injected"]))
    elif d["injected"] < -0.005:
        snk.append(("the drive circuit (energy taken back out)", -d["injected"]))
    if d["radiated"] > 0.005:
        snk.append(("radiation", d["radiated"]))
    src.sort(key=lambda x: -x[1])
    snk.sort(key=lambda x: -x[1])
    if not src:
        return "No energy store changed by more than 0.5 % of the starting energy."
    s = "Paid for by " + ", ".join(f"{n} ({_pct(v)} of E0)" for n, v in src)
    if snk:
        s += "; it went into " + ", ".join(f"{n} ({_pct(v)})" for n, v in snk)
    return s + "."


# =====================================================
# stability criteria
# =====================================================

def criteria(f, cls):
    """Each criterion: value, what theory says, and whether the run agreed."""
    label = cls["label"]
    kinked = f["m1_peak"] >= RU.GROWN
    disrupted = label == "kink_disruption"
    out = []

    # Kruskal-Shafranov. The helix with n wavelengths along the column is
    # kink-unstable when n q < 1 (its pitch matches the field lines inside
    # the column); q itself is the n = 1 case. The starting q is used: the
    # extra current of a strong drive flows mostly in the swept-up sheath,
    # outside the column, so q / I over-predicts the kink (sweep: q < 0.1
    # disrupts 99 % of the time, q / I < 0.1 only 91 %).
    q, nq, n = f["q_a"], f["nq_seed"], int(f["seed_n"])
    out.append({"name": "Kruskal-Shafranov q(a), longest helix", "value": q, "threshold": 1.0,
                "expect": ("the longest helix (n = 1) is kink-unstable" if q < 1 else
                           "every helix is kink-stable"),
                # q < 1 without a kink is fine: the n = 1 helix is slow (see note)
                "agree": True if q < 1 else not kinked,
                "note": ("a kink grew" if kinked else "no kink grew") +
                        (" (with a wall at ~4 radii and only 3 time units, the n = 1 helix grows slowly: "
                         "shorter helices decide the outcome)" if q < 1 and not kinked else ""),
                "detail": "q = 2 pi a B_z / (L_z B_theta) with the starting current"})
    if nq < 0.5:
        expect, agree = "far below 1: strongly unstable (sweep: 124 of 131 such runs disrupted)", disrupted
    elif nq < 1.0:
        expect, agree = "below 1: unstable but close to marginal (sweep: 43 of 43 saturated)", kinked
    elif nq < 1.5:
        expect, agree = "just above 1: marginal (sweep: 65 % saturated, 35 % no kink)", True
    else:
        expect, agree = "well above 1: stable (sweep: 41 of 41 grew no kink)", not kinked
    out.append({"name": f"Kruskal-Shafranov n q for the seeded helix (n = {n})", "value": nq, "threshold": 1.0,
                "expect": expect, "agree": agree,
                "note": f"kink peak {f['m1_peak']:.2g} radii" + (", disrupted" if disrupted else ""),
                "detail": "n q < 1: the seeded helix twists more slowly than the field lines and can grow; "
                          "sweep numbers are 32^3 runs without gravity or cooling"})

    k = f["kadomtsev_margin"]
    necked = f["m0_peak"] >= RU.SAUSAGE
    out.append({"name": "Kadomtsev sausage margin", "value": k, "threshold": 1.0,
                "expect": ("edge is sausage-stable (B_z^2 > B_theta^2 / 2)" if k > 1 else
                           "edge is open to sausage necking (B_z^2 < B_theta^2 / 2)"),
                "agree": (not necked) if k > 1 else True,
                "note": (f"largest necking {f['m0_peak']:.2g} a" +
                         ("" if k > 1 or necked else "; the kink grew first and dominated")),
                "detail": "B_z^2 / (B_theta^2 / 2) at r = a, with the starting current"})

    S, tr = f["lundquist"], f["t_resistive"]
    out.append({"name": "Lundquist number S", "value": S, "threshold": 100.0,
                "expect": ("nearly ideal: field lines move with the plasma" if S >= 100 else
                           "resistive: field lines slip through the plasma"),
                "agree": True,
                "note": f"resistive time a^2/eta = {tr:.3g} vs run length {f['t_final']:.3g}"
                        + (" (diffusion acts within the run)" if tr <= RU.RESISTIVE_TIMES * f["t_final"] else ""),
                "detail": "S = a v_A / eta"})

    if f["cooling"] > 0:
        tc = f["t_cooling"]
        collapsed = label == "radiative_collapse" or "radiative_collapse" in cls["secondary"]
        out.append({"name": "Radiative cooling time", "value": tc, "threshold": f["t_final"],
                    "expect": ("cooling acts within the run" if tc < f["t_final"] else
                               "cooling slower than the run"),
                    "agree": not collapsed or tc < f["t_final"],
                    "note": (f"core reached T = {f['core_temp_min']:.2g} T0 and "
                             f"{f['core_density_max']:.2g}x its density; radiated {_pct(f['radiated'])} of E0"),
                    "detail": "1 / ((gamma - 1) C) for the core at rho = T = 1 (shorter once it compresses)"})

    I = f["current"]
    out.append({"name": "Drive current vs Bennett", "value": I, "threshold": 1.0,
                "expect": ("magnetic pressure exceeds plasma pressure: the column is pushed inward"
                           if I > RU.COMPRESS_I else
                           "magnetic pressure below plasma pressure: the column relaxes outward" if I < 0.9 else
                           "close to Bennett equilibrium"),
                "agree": True,
                "note": (f"core density peaked at {f['core_density_max']:.2g}x its start"),
                "detail": "I / I_Bennett; the circuit approaches it with time constant "
                          f"{f['rise_time']:.3g}"})

    if f["gravity"] > 0:
        t_fall = math.sqrt(2.0 * f["pinch_radius"] / f["gravity"])
        out.append({"name": "Gravity fall time across one radius", "value": t_fall, "threshold": f["t_final"],
                    "expect": "the column can fall within the run" if t_fall < f["t_final"] else
                              "too slow to matter in this run",
                    "agree": True,
                    "note": f"whole-column offset reached {f['shift_peak']:.2g} a",
                    "detail": "sqrt(2 a / g), free fall with nothing holding the column"})
    return out


# =====================================================
# causes: one short chain per detected class
# =====================================================

def _phase(cls, name):
    for p in cls["phases"]:
        if p["name"] == name:
            return p
    return None


def helix_sentence(f):
    """Which helix carried the kink, as far as the n = 1..3 diagnostic can tell."""
    seed = int(f["seed_n"])
    if not math.isfinite(f["m1_dominant_n"]):
        lam = f["length"] / seed
        return (f"The saved mode diagnostic resolves n = 1 to 3 only, and they carry "
                f"{100 * f['m1_resolved_frac']:.0f} % of this kink, so it sits in the seeded n = {seed} helix "
                f"(wavelength {lam:.2f}, {lam / f['pinch_radius']:.1f} radii) or its harmonics.")
    n = int(f["m1_dominant_n"])
    lam = f["length"] / n
    s = f"Most of the kink sits in the n = {n} helix (wavelength {lam:.2f}, {lam / f['pinch_radius']:.1f} radii)"
    if n == seed:
        return s + ", the helix the starting perturbation seeded."
    return s + (f", not the seeded n = {seed}: a {'longer' if n < seed else 'shorter'} helix outgrew it.")


def causes(h, f, cls):
    """Ordered list of {topic, text, energy?} explaining the timeline."""
    out = []
    found = cls["evidence"]

    p = _phase(cls, "compression")
    if p:
        d = energy_between(h, 0.0, p["t_end"])
        out.append({"topic": "compression", "energy": d, "text": (
            f"The circuit raised the current to {f['current']:.2g}x the Bennett value (rise time "
            f"{f['rise_time']:.2g}). The extra magnetic pressure squeezed the core to "
            f"{p['numbers']['core_density_max']:.2g}x its starting density by t = {p['t_end']:.2f}. "
            + who_paid(d))})

    p = _phase(cls, "kink_growth")
    if p:
        rate = (f"at rate {f['m1_gamma']:.2f} +- {f['m1_gamma_err']:.2f} per time unit "
                f"({f['m1_gamma_tA']:.2f} per Alfven time; fit R^2 = {f['m1_gamma_r2']:.2f})")
        if f["axial_field"] == 0:
            why = "With no axial field (q = 0) nothing resists bending, so the column is kink-unstable."
        elif f["nq_seed"] < 1:
            why = (f"With q = {f['q_a']:.2g} the seeded n = {int(f['seed_n'])} helix has n q = {f['nq_seed']:.2g} < 1, "
                   f"so it is kink-unstable (Kruskal-Shafranov).")
        else:
            why = (f"A kink grew although the seeded helix has n q = {f['nq_seed']:.2g} >= 1: q is lower inside "
                   f"the column (on the axis, half its edge value for the Bennett profile), so the inner column "
                   f"can still kink.")
        out.append({"topic": "kink_growth", "text": (
            f"{why} A helical kink grew from t = {p['t_start']:.2f} {rate}. " + helix_sentence(f))})

    if "kink_disruption" in found:
        e = found["kink_disruption"]
        d = energy_between(h, e["t_nonlinear"], e["t_mixed"] + 0.3)
        out.append({"topic": "kink_disruption", "energy": d, "text": (
            f"Once the kink passed {RU.NONLINEAR:g} radii (t = {e['t_nonlinear']:.2f}) it kept going: by "
            f"t = {e['t_mixed']:.2f} the column had been torn apart and its plasma spread to "
            f"{RU.MIXED_RADIUS:g} radii (the wall is at {0.5 / f['pinch_radius']:.1f}). "
            f"Flow peaked at {_pct(f['kinetic_max'])} of E0 (t = {f['kinetic_t_max']:.2f}). " + who_paid(d)
            + (" Nothing stopped it: there is no axial field to resist bending." if f["axial_field"] == 0 else
               f" Nothing stopped it: B_z is too weak to hold the helix (n q = {f['nq_seed']:.2g}, far below 1).")
            if f["nq_seed"] < 0.5 else
            f"Once the kink passed {RU.NONLINEAR:g} radii (t = {e['t_nonlinear']:.2f}) it tore the "
            f"column apart by t = {e['t_mixed']:.2f}. " + who_paid(d))})

    if "kink_growing" in found:
        nq = f["nq_seed"]
        likely = ("most runs this far below n q = 1 went on to disrupt (124 of 131 below 0.5)" if nq < 0.5 else
                  "runs with 0.5 < n q < 1 all saturated as a bent helix (43 of 43)" if nq < 1 else
                  "runs with n q this close to 1 mostly saturated at a small amplitude")
        out.append({"topic": "kink_growing", "text": (
            f"The kink is still growing exponentially at t = {f['t_final']:.2f} ({f['m1_final']:.2g} radii, "
            f"growing at {found['kink_growing']['late_rate']:.2f} per time unit), so the outcome is not decided "
            f"yet. Run longer and analyse again. In the overnight sweep, {likely}.")})

    if "saturated_kink" in found:
        p = _phase(cls, "saturated_kink")
        e = found["saturated_kink"]
        d = energy_between(h, p["t_start"], p["t_end"])
        text = (f"The kink stopped growing at ~{e['m1_sat']:.2g} radii (t = {e['t_sat']:.2f}) and the column "
                f"survived as a bent helix. Saturation happens when the helix has released the magnetic energy "
                f"it can reach: bending further would stretch the axial field (B_z = {f['axial_field']:.2g}) "
                f"more than it gains. ")
        if e["m1_final"] > 1.3 * e["m1_sat"]:
            text += (f"Late in the run it crept up again, to {e['m1_final']:.2g} radii at t = {f['t_final']:.2f}, "
                     f"far slower than its exponential phase"
                     + (" (partly because the amplitude is measured against a column that is shrinking)"
                        if f["radius_final"] < 1.0 else "") + ". ")
        out.append({"topic": "saturated_kink", "energy": d, "text": text + who_paid(d)})

    if "sausage" in found or _phase(cls, "sausage"):
        p = _phase(cls, "sausage")
        k = f["kadomtsev_margin"]
        out.append({"topic": "sausage", "text": (
            f"Necking (m = 0) reached {p['numbers']['m0_peak']:.2g} radii between t = {p['t_start']:.2f} and "
            f"{p['t_end']:.2f}. " + ("The Kadomtsev margin is below 1, so B_z is too weak to stiffen the "
                                     "column against pinching off." if k < 1 else
                                     "The Kadomtsev margin is above 1, so this is not the ideal sausage: "
                                     "it is the column breaking into dense blobs as it cools or decays."))})

    if "gravity_sag" in found:
        p = _phase(cls, "gravity_sag")
        d = energy_between(h, 0.0, p["t_end"])
        out.append({"topic": "gravity_sag", "energy": d, "text": (
            f"Gravity (g = {f['gravity']:.2g}) pulled the whole column {f['shift_peak']:.2g} radii off axis "
            f"by t = {f['shift_t_peak']:.2f}. This is a bulk shift (axial wavenumber n = 0), not a kink: "
            f"the column moves as a whole and stays straight. " + who_paid(d))})

    if "radiative_collapse" in found:
        p = _phase(cls, "radiative_collapse")
        e = found["radiative_collapse"]
        d = energy_between(h, p["t_start"], e["t_hit"])
        out.append({"topic": "radiative_collapse", "energy": d, "text": (
            f"Radiation (C = {f['cooling']:.2g}, cooling time ~{f['t_cooling']:.2g}) drained the core's heat "
            f"faster than compression and Ohmic heating replaced it. From t = {p['t_start']:.2f} the core cooled; "
            f"with less pressure the magnetic field squeezed it, and denser plasma radiates faster "
            f"(P ~ rho^2 sqrt T), a runaway. By t = {e['t_hit']:.2f} the core was below "
            f"{RU.COLLAPSE_T:g} T0 and {RU.COLLAPSE_RHO:g}x denser; it reached T = {f['core_temp_min']:.2g} "
            f"and {f['core_density_max']:.2g}x. " + who_paid(d))})

    if "resistive_diffusion" in found:
        d = energy_between(h, 0.0, f["t_final"])
        out.append({"topic": "resistive_diffusion", "energy": d, "text": (
            f"No instability grew (kink peak {f['m1_peak']:.2g}). With resistivity eta = {f['resistivity']:.2g} "
            f"the current diffuses out of the column in ~{f['t_resistive']:.2g} time units, shorter than the run, "
            f"so the column spread and its core density fell to {f['core_density_final']:.2g}x the start. "
            + who_paid(d) + " The heat is Ohmic: the current's resistance turns field energy into heat.")})

    if "quiescent" in found:
        d = energy_between(h, 0.0, f["t_final"])
        nq = f["nq_seed"]
        if nq >= 1:
            why = (f"The seeded helix has n q = {nq:.2g} >= 1, so the axial field (B_z = {f['axial_field']:.2g}) "
                   f"makes it kink-stable (Kruskal-Shafranov). ")
        elif f["t_final"] < 1.5 * kink_time_needed(f):
            why = (f"A kink is expected (n q = {nq:.2g} < 1) but has not had time to show: at the typical rate "
                   f"it needs until about t = {kink_time_needed(f):.1f} to reach {RU.GROWN:g} radii, and this "
                   f"run is at t = {f['t_final']:.2f}. Run longer and analyse again. ")
        else:
            why = (f"The seeded helix has n q = {nq:.2g} < 1, so a kink was possible, but "
                   + ("the axial field and " if f["axial_field"] > 0 else "")
                   + f"dissipation kept it below {RU.GROWN:g} radii within the run. ")
        out.append({"topic": "quiescent", "energy": d, "text": (
            f"Nothing grew beyond {max(f['m1_peak'], f['m0_peak']):.2g} radii. " + why
            + "The slow spreading that remains is diffusion (physical plus the grid's own). " + who_paid(d))})
    return out


# =====================================================
# entry points
# =====================================================

def ml_view(f, cls, meta):
    """
    The trained models' opinion, if they exist (tools/train.py). Secondary
    by design: the causes above come from physics, this is a cross-check.
    """
    try:
        from . import model as MD
        a = MD.classify_run(f)
        b = MD.predict_outcome(meta["setup"], meta["live"])
    except ImportError:          # scikit-learn not installed
        return None
    if a is None and b is None:
        return None
    out = {"run_classifier": a, "outcome_predictor": b}
    if a is not None:
        top = a["probs"][0][0]
        out["agrees"] = top == cls["label"]
        out["rule_label_prob"] = dict(a["probs"]).get(cls["label"], 0.0)
    return out


def analyse(h, meta, with_ml=True):
    """
    Full analysis of one run (history at DT_SAVE spacing + meta). with_ml=False
    skips the models' opinion: training data must come from the rules alone.
    """
    f = FE.compute(h, meta)
    cls = RU.classify(h, f, meta)
    r = {
        "id": meta.get("id"),
        "version": ANALYSIS_VERSION,
        "label": cls["label"],
        "label_name": NAMES[cls["label"]],
        "secondary": cls["secondary"],
        "confidence": cls["confidence"],
        "borderline": cls["borderline"],
        "health": cls["health"],
        "notes": ([f"analysed early (t = {f['t_final']:.2f}): the label describes the run so far"]
                  if f["t_final"] < 1.0 else []),
        "phases": cls["phases"],
        "causes": causes(h, f, cls),
        "criteria": criteria(f, cls),
        "energy_total": energy_between(h, 0.0, f["t_final"]),
        "features": f,
        "evidence": cls["evidence"],
        "ml": ml_view(f, cls, meta) if with_ml else None,
    }
    from . import writeup as WU
    try:
        r["writeup"] = WU.writeup(r, meta)
    except (OSError, KeyError, ValueError) as err:   # a broken library file must not break the analysis
        r["writeup"] = None
        r["notes"].append(f"no curated write-up: the library could not be read ({err!r})")
    return r


def analyse_sim(sim):
    h, meta = FE.run_from_sim(sim)
    return analyse(h, meta)


def analyse_npz(path, with_ml=True):
    h, meta = FE.load_npz(path)
    return analyse(h, meta, with_ml)


def _num(x):
    if isinstance(x, float) and not math.isfinite(x):
        return "inf" if x > 0 else "nan"
    return f"{x:.4g}"


def format_report(r):
    """Plain-text report (terminal, --analyse, the GUI dialog)."""
    f = r["features"]
    L = []
    head = f"Outcome: {r['label_name']}"
    if r["secondary"]:
        head += "   (also: " + ", ".join(NAMES.get(s, s) for s in r["secondary"]) + ")"
    L += [head, f"Confidence: {r['confidence']}" + (" - " + "; ".join(r["borderline"]) if r["borderline"] else ""),
          f"Run: t = 0 .. {f['t_final']:.2f}   I = {f['current']:.3g}   B_z = {f['axial_field']:.3g}   "
          f"L = {f['length']:.3g}   eta = {f['resistivity']:.2g}   nu = {f['viscosity']:.2g}   "
          f"C = {f['cooling']:.2g}   g = {f['gravity']:.2g}", ""]
    for note in r["notes"] + r["health"]:
        L.append(f"! {note}")
    if r["notes"] or r["health"]:
        L.append("")
    w = r.get("writeup")
    if w:
        from .writeup import match_text
        L.append(w["title"])
        for head, text in w["sections"].items():
            L.append(head)
            L += textwrap.wrap(text, 100, initial_indent="  ", subsequent_indent="  ")
        if w["note"]:
            L.append(f"! {w['note']}")
        L += ["", "-" * 100, "Data appendix", ""]
    L.append("Timeline")
    for p in r["phases"]:
        L.append(f"  t = {p['t_start']:5.2f} - {p['t_end']:5.2f}  {NAMES.get(p['name'], p['name']):<24s} {p['text']}")
    L += ["", "Causes in detail (energy bookkeeping, phase by phase)"]
    for c in r["causes"]:
        L.append(f"  * {c['text']}")
    L += ["", "Stability criteria (theory vs this run)"]
    for c in r["criteria"]:
        mark = "ok" if c["agree"] else "!!"
        L.append(f"  {mark} {c['name']} = {_num(c['value'])}")
        L.append(f"       {c['expect']}; {c['note']}")
    ml = r.get("ml")
    if ml:
        from .model import format_prediction
        L += ["", "Machine-learning view (a cross-check; the causes above come from physics)"]
        a = ml.get("run_classifier")
        if a:
            verdict = ("agrees with the rules" if ml["agrees"] else
                       f"DISAGREES with the rules, which gave {NAMES[r['label']]} "
                       f"({100 * ml['rule_label_prob']:.0f} %): a borderline or unusual run")
            L.append(f"  run classifier (a):    {format_prediction(a, NAMES)}  - {verdict}")
        b = ml.get("outcome_predictor")
        if b:
            L.append(f"  before the run, (b):   {format_prediction(b, NAMES)}")
    e = r["energy_total"]
    L += ["", "Energy budget, whole run (fractions of the starting energy E0)",
          "  " + "  ".join(f"{k} {e[k]:+.3f}" for k in STORES) +
          f"  | circuit in {e['injected']:+.3f}  radiated {e['radiated']:.3f}  floors {e['floor']:.3f}",
          ""]
    if w:
        L.append("Write-up: " + match_text(w))
    L.append(f"Analysis {r['version']}; {len(f)} features in r['features'].")
    return "\n".join(L)
