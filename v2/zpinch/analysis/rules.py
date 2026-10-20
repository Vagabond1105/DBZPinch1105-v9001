"""
Physics labeller (plan section 3): turns a run's history into a timeline
of phases and one overall outcome class, using transparent thresholds.

It is the "teacher" for the Phase 3 classifier and the fallback when no
model is loaded. Every threshold below says why it has its value and which
runs it was checked against (sweep-2026-10-19, 1058 runs at 32^3; run ids
are files in dataset/sweep-2026-10-19/runs/).

Outcome classes, in the order they win when several happen in one run
(the most violent end state names the run; the others are listed as
secondary):

    radiative_collapse   core gets cold AND dense: radiation outruns heating
    kink_disruption      kink grows large, then the column is torn apart
    kink_growing         the kink is still growing exponentially when the run
                         ends (only when analysed early, e.g. from the GUI;
                         no t = 3 sweep run ends this way)
    sausage              necking (m = 0) is the largest distortion
    saturated_kink       kink grows, then stops growing; the column survives
    gravity_sag          the whole column falls along -y; little or no kink
    resistive_diffusion  nothing goes unstable; the column spreads and heats
                         by Ohmic dissipation
    quiescent            nothing much happens

Compression is not an outcome class: in this setup the circuit's magnetic
piston sweeps the background plasma into a sheath and the core is squeezed
only briefly (core density +30-90 %, then it relaxes), so it appears as an
early phase of the timeline.
"""

import math

import numpy as np

from .features import MIXED_RADIUS, first_time

CLASSES = ("quiescent", "saturated_kink", "kink_disruption", "sausage", "gravity_sag",
           "radiative_collapse", "resistive_diffusion", "kink_growing")
PRIORITY = ("radiative_collapse", "kink_disruption", "sausage", "kink_growing", "saturated_kink",
            "gravity_sag", "resistive_diffusion", "quiescent")

# ---- thresholds (amplitudes in units of the column radius) ----

# A mode counts as having grown once it is 5x the 0.02 seed. Runs that stay
# quiet (strong B_z, short column: r00194, r00739, r00027) settle at
# 0.03-0.09 after a start-up transient, so 0.10 sits just above them.
GROWN = 0.10
# A kink this large can tear the column. In runs without gravity or
# cooling, fast radius growth (>= 3 a per time unit) first appears in the
# 0.3-0.4 band of peak kink amplitude and is the norm above 0.4.
NONLINEAR = 0.30
# A saturated kink's level is read within this long after the exponential
# phase ends (growth at gamma ~ 4 stops within ~0.3 time units).
SAT_WINDOW = 0.5
# Still growing: the kink peaks in the last STILL_WINDOW and is growing
# there at >= half its fitted exponential rate. The sweep's late creep
# (rates 0.1-1 against ~4) stays well below that.
STILL_WINDOW = 0.1
STILL_FRAC = 0.5
# A disruption must tear the column within this long after the kink became
# nonlinear; a slow spread much later is diffusion, not break-up.
DISRUPT_DELAY = 1.0
# Necking counts once it is 0.15 a, larger than the kink at that moment,
# for at least 0.1 time units (a single overshoot is not a sausage, r00849).
# In 1058 runs m0 never exceeded 0.52 and passed 0.15 in ~90 runs, mostly
# during radiative collapse where cold blobs condense along the column; it
# is the largest distortion of the whole run in only a handful.
SAUSAGE = 0.15
SAUSAGE_MIN_TIME = 0.1
# The whole column has fallen by half its own radius. Gravity runs reach
# 0.5-1.5 within t ~ 0.5 (r00047, r00863); without gravity the offset
# stays below ~0.3 until the column breaks up.
SAG = 0.5
# Radiative collapse: core temperature below 0.4 T0 while the core is at
# least 1.5x denser than at the start. In the sweep the core temperature
# minimum is bimodal: 35 runs went below 0.4 (most to 0.05-0.15, e.g.
# r00171, r00899), the rest stayed above 0.6. The density condition
# separates a collapse from a column that only cools while it expands
# (r00044, r01009: T falls to 0.3-0.4 but density does not rise).
COLLAPSE_T = 0.4
COLLAPSE_RHO = 1.5
COLLAPSE_ONSET_T = 0.7     # the timeline starts the collapse when T_core falls below this
# Compression: core density 30 % above its start while the drive pushes
# (I > 1.1). Runs at I ~ 2.5 reach 1.6-2.0 (r00243, r00741); runs near
# I = 1 never pass ~1.15.
COMPRESS_RHO = 1.3
COMPRESS_I = 1.1
# Resistive diffusion: a quiet column whose core density has fallen to
# RESISTIVE_CORE of its start AND which gained RESISTIVE_HEAT of E0 as heat
# with almost no motion (Ohmic heating). Quiet runs at eta ~ 1e-4 still
# fall to ~0.7 by t = 3 (numerical diffusion of an 8-cell-wide column) and
# gain ~0.015 E0; at eta >= 3e-3 they fall below 0.45 and gain >= 0.05.
# The cause must also fit in the run: the resistive time a^2 / eta at most
# RESISTIVE_TIMES x the simulated time. Without it, high-current runs that
# heat by compression rather than by eta were caught (r00554, I = 2.2).
RESISTIVE_CORE = 0.5
RESISTIVE_HEAT = 0.04
RESISTIVE_TIMES = 2.0

# a decisive number within this factor of its threshold makes the label
# borderline (+-15 %: a threshold nudged that far would flip the label)
BORDER = 1.15

# numerical-health flags
FLOOR_WARN = 0.05          # vacuum floors added > 5 % of E0
ENERGY_WARN = 1e-3         # energy budget error above 0.1 %


def _phase(name, t0, t1, text, **numbers):
    return {"name": name, "t_start": float(t0), "t_end": float(t1), "text": text,
            "numbers": {k: float(v) for k, v in numbers.items()}}


def _runs(mask):
    """[(i_start, i_end)] of contiguous True stretches."""
    out, start = [], None
    for i, m in enumerate(mask):
        if m and start is None:
            start = i
        elif not m and start is not None:
            out.append((start, i - 1))
            start = None
    if start is not None:
        out.append((start, len(mask) - 1))
    return out


def detect(h, f):
    """
    Run every detector. Returns (found, phases): found maps class name ->
    dict of the evidence that decided it; phases is the time-ordered list.
    """
    t = np.asarray(h["t"], dtype=float)
    t_end = float(t[-1])
    m1, m0, sh = (np.asarray(h[k]) for k in ("m1", "m0", "shift"))
    rc = np.asarray(h["core_density"]) / h["core_density"][0]
    Tc = np.asarray(h["core_temperature"])
    found, phases = {}, []

    # ---- drive: compression ----
    if f["current"] > COMPRESS_I:
        ramp_end = min(t_end, 3.0 * f["rise_time"] + 1.0)
        early = (t <= ramp_end) & (rc >= COMPRESS_RHO) & (Tc >= COLLAPSE_ONSET_T)
        if early.any():
            i0, i1 = _runs(early)[0]
            found["compression"] = {"core_density_max": float(rc[i0:i1 + 1].max())}
            phases.append(_phase(
                "compression", t[i0], t[i1],
                "the rising current squeezes the core",
                core_density_max=rc[i0:i1 + 1].max(), current=f["current"]))

    # ---- kink: growth, then disruption or saturation ----
    if f["m1_peak"] >= GROWN:
        t_half = first_time(t, m1 >= 0.5 * f["m1_peak"])
        t_on = f["m1_t_onset"] if math.isfinite(f["m1_t_onset"]) else 0.0
        phases.append(_phase(
            "kink_growth", t_on, t_half,
            "a helical kink grows exponentially",
            gamma=f["m1_gamma"], gamma_err=f["m1_gamma_err"], r2=f["m1_gamma_r2"],
            dominant_n=f["m1_dominant_n"]))
        t_nl = first_time(t, m1 >= NONLINEAR)
        torn = (math.isfinite(t_nl) and math.isfinite(f["t_mixed"])
                and t_nl <= f["t_mixed"] <= t_nl + DISRUPT_DELAY)
        k_late = int(np.searchsorted(t, t_end - STILL_WINDOW))
        late_rate = (math.log(max(m1[-1], 1e-12) / max(m1[k_late], 1e-12)) / max(t_end - t[k_late], 1e-9)
                     if k_late < len(t) - 1 else 0.0)
        growing = (f["m1_t_peak"] >= t_end - STILL_WINDOW and f["m1_gamma"] > 0
                   and late_rate >= STILL_FRAC * f["m1_gamma"])
        if torn:
            found["kink_disruption"] = {"m1_peak": f["m1_peak"], "t_nonlinear": t_nl,
                                        "t_mixed": f["t_mixed"]}
            phases.append(_phase(
                "kink_disruption", t_nl, f["t_mixed"],
                "the kink tears the column apart and its plasma spreads toward the wall",
                m1_peak=f["m1_peak"], radius_max=f["radius_max"], kinetic_max=f["kinetic_max"]))
        elif growing:
            found["kink_growing"] = {"m1_final": f["m1_final"], "late_rate": late_rate}
            phases[-1]["t_end"] = t_end
        else:
            # saturation level: the largest amplitude within SAT_WINDOW of the end of
            # the exponential phase. Some kinks creep up again much later, at a few
            # % of the linear rate (32 runs, mostly radiative collapse, where the
            # shrinking radius they are measured against also raises them)
            t_sat0 = t_half if math.isfinite(t_half) else f["m1_t_peak"]
            win = (t >= t_sat0) & (t <= t_sat0 + SAT_WINDOW)
            i_sat = int(np.flatnonzero(win)[np.argmax(m1[win])])
            found["saturated_kink"] = {"m1_peak": f["m1_peak"], "m1_sat": float(m1[i_sat]),
                                       "t_sat": float(t[i_sat]), "m1_final": f["m1_final"]}
            phases.append(_phase(
                "saturated_kink", t_sat0, t_end,
                "the kink stops growing and the column survives as a bent helix",
                m1_sat=m1[i_sat], m1_final=f["m1_final"]))

    # ---- sausage ----
    # the class needs necking to be the largest distortion of the whole run;
    # a shorter stretch where m0 overtakes a kink that has already faded is
    # kept only as a phase (late necking, e.g. r00201, r00062)
    necking = [r for r in _runs((m0 >= SAUSAGE) & (m0 > m1)) if t[r[1]] - t[r[0]] >= SAUSAGE_MIN_TIME]
    if necking:
        i0, i1 = max(necking, key=lambda r: m0[r[0]:r[1] + 1].max())
        if f["m0_peak"] > f["m1_peak"] and f["m0_peak"] > f["shift_peak"]:
            found["sausage"] = {"m0_peak": f["m0_peak"], "m1_peak": f["m1_peak"]}
        phases.append(_phase(
            "sausage", t[i0], t[i1],
            "the column necks like a string of sausages",
            m0_peak=m0[i0:i1 + 1].max()))

    # ---- gravity sag ----
    if f["gravity"] > 0.0 and f["shift_peak"] >= SAG:
        found["gravity_sag"] = {"shift_peak": f["shift_peak"], "d_potential": f["d_potential"]}
        phases.append(_phase(
            "gravity_sag", first_time(t, sh >= 0.1), f["shift_t_peak"],
            "the whole column falls along -y",
            shift_peak=f["shift_peak"], d_potential=f["d_potential"]))

    # ---- radiative collapse ----
    hit = (Tc <= COLLAPSE_T) & (rc >= COLLAPSE_RHO)
    if hit.any():
        t_hit = first_time(t, hit)
        t_on = first_time(t, Tc <= COLLAPSE_ONSET_T)
        found["radiative_collapse"] = {"core_temp_min": f["core_temp_min"],
                                       "core_density_max": f["core_density_max"], "t_hit": t_hit}
        phases.append(_phase(
            "radiative_collapse", t_on, t_end,
            "radiation cools the core faster than it is heated; it shrinks and gets denser",
            core_temp_min=f["core_temp_min"], core_density_max=f["core_density_max"],
            radiated=f["radiated"], t_hit=t_hit))

    # ---- quiet runs: resistive diffusion or nothing ----
    if not any(k in found for k in ("saturated_kink", "kink_growing", "kink_disruption", "sausage",
                                    "gravity_sag", "radiative_collapse")):
        if (f["core_density_final"] <= RESISTIVE_CORE and f["d_thermal"] >= RESISTIVE_HEAT
                and f["t_resistive"] <= RESISTIVE_TIMES * t_end):
            found["resistive_diffusion"] = {"core_density_final": f["core_density_final"],
                                            "d_thermal": f["d_thermal"]}
            phases.append(_phase(
                "resistive_diffusion", 0.0, t_end,
                "the current diffuses outward; the column spreads and heats without moving",
                core_density_final=f["core_density_final"], d_thermal=f["d_thermal"]))
        else:
            found["quiescent"] = {"m1_peak": f["m1_peak"], "m0_peak": f["m0_peak"]}
            phases.append(_phase("quiescent", 0.0, t_end, "the column stays close to its starting state",
                                 m1_peak=f["m1_peak"], m0_peak=f["m0_peak"]))

    phases.sort(key=lambda p: (p["t_start"], p["t_end"]))
    return found, phases


def _near(value, threshold):
    if not (math.isfinite(value) and threshold > 0 and value > 0):
        return False
    r = value / threshold
    return 1.0 / BORDER <= r <= BORDER


def borderline(label, f, found):
    """Notes for every decisive number that sits close to its threshold."""
    checks = {
        "quiescent": [("m1_peak", GROWN), ("m0_peak", SAUSAGE), ("core_density_final", RESISTIVE_CORE)],
        "saturated_kink": [("m1_peak", GROWN), ("radius_max", MIXED_RADIUS)],
        "kink_disruption": [("m1_peak", NONLINEAR), ("radius_max", MIXED_RADIUS)],
        "sausage": [("m0_peak", SAUSAGE), ("m0_peak", f["m1_peak"])],
        "gravity_sag": [("shift_peak", SAG)],
        "radiative_collapse": [("core_temp_min", COLLAPSE_T), ("core_density_max", COLLAPSE_RHO)],
        "kink_growing": [("m1_peak", GROWN)],
        "resistive_diffusion": [("core_density_final", RESISTIVE_CORE), ("d_thermal", RESISTIVE_HEAT),
                                ("t_resistive", RESISTIVE_TIMES * f["t_final"])],
    }[label]
    if label == "saturated_kink" and f["m1_peak"] >= NONLINEAR:
        checks = checks + [("m1_peak", NONLINEAR)]
    if label == "gravity_sag" and "saturated_kink" in found:
        checks = checks + [("m1_peak", NONLINEAR)]
    return [f"{name} = {f[name]:.3g} is within {BORDER:.2f}x of its threshold {thr:g}"
            for name, thr in checks if _near(f[name], thr)]


def health(f, meta):
    notes = []
    if f["floor_energy"] > FLOOR_WARN:
        notes.append(f"vacuum floors added {100 * f['floor_energy']:.0f} % of the starting energy: "
                     "the near-vacuum outside the column was under-resolved, treat details with care")
    if f["energy_error_max"] > ENERGY_WARN:
        notes.append(f"energy budget error reached {f['energy_error_max']:.1e} (usually < 1e-12)")
    if meta.get("status") == "partial":
        notes.append(f"the run was stopped early at t = {f['t_final']:.2f} ({meta.get('reason')})")
    return notes


def classify(h, f, meta=None):
    """
    Label one run. Returns
        label       overall class (CLASSES)
        secondary   other classes that also happened
        confidence  "high", or "low" when a decisive number is near its threshold
        borderline  which numbers made it low
        phases      timeline, each {name, t_start, t_end, text, numbers}
        evidence    the numbers each detected class was decided on
        health      numerical warnings
    """
    found, phases = detect(h, f)
    present = [c for c in PRIORITY if c in found]
    label = present[0]
    # a large sag with only a small (saturated or slowly growing) kink is a sag that bends a little
    if (label in ("saturated_kink", "kink_growing") and "gravity_sag" in found
            and f["m1_peak"] < NONLINEAR and f["shift_peak"] > f["m1_peak"]):
        label = "gravity_sag"
    notes = borderline(label, f, found)
    return {
        "label": label,
        "secondary": [c for c in present if c != label] + (["compression"] if "compression" in found else []),
        "confidence": "low" if notes else "high",
        "borderline": notes,
        "phases": phases,
        "evidence": found,
        "health": health(f, meta or {}),
    }
