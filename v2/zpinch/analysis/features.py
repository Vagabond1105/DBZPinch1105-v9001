"""
Run history -> named physical numbers (plan section 4).

A "history" is the dict of HISTORY_KEYS arrays that ZPinch records every
step (zpinch/pinch.py). The sweep saved it down-sampled to DT_SAVE, and the
analysis always works on that same sampling, so a run analysed live in the
GUI and the same run loaded from the dataset give the same numbers.

Everything is dimensionless in the code's units (docs/04): lengths in
domain widths, time in L0 / v0, energies as fractions of the starting total
energy E0. Mode amplitudes (m0, m1, shift) are already relative to the
column radius. Radii are quoted in units of the starting radius a.
"""

import json
import math

import numpy as np

DT_SAVE = 0.005          # history sample spacing (~0.03 Alfven times), as in tools/sweep.py
MIXED_RADIUS = 3.5       # see rules.py: column spread most of the way to the wall
GAMMA_GAS = 5.0 / 3.0

# (name, unit, meaning): the researcher-facing list, written to the CSV header doc
FEATURES = [
    # ---- starting parameters (what the user set) ----
    ("current", "I_Bennett", "drive current set point"),
    ("rise_time", "t0", "drive circuit L/R time"),
    ("axial_field", "B_theta(a)", "uniform guide field B_z"),
    ("resistivity", "L0 v0", "magnetic diffusivity eta"),
    ("viscosity", "L0 v0", "kinematic viscosity nu"),
    ("cooling", "-", "bremsstrahlung coefficient C (P = C rho^2 sqrt T)"),
    ("gravity", "v0^2/L0", "gravitational acceleration along -y"),
    ("length", "L0", "column length / domain width (requested)"),
    ("pinch_radius", "L0", "starting Bennett radius a"),
    ("background_density", "rho0", "density outside the column"),
    # ---- stability numbers at t = 0 ----
    ("q_a", "-", "safety factor 2 pi a B_z / (L_z B_theta) with the starting current"),
    ("q_a_driven", "-", "q_a / I, as if all the driven current flowed in the column. It does not: above "
                        "I ~ 1.5 most of the extra current flows in the swept-up sheath, and q_a "
                        "predicts the outcome better (tools/analyse.py summary)"),
    ("kadomtsev_margin", "-", "B_z^2 / (B_theta^2 / 2) at r = a; > 1 means sausage-stable edge"),
    ("kadomtsev_driven", "-", "Kadomtsev margin at the driven current"),
    ("lundquist", "-", "a v_A / eta"),
    ("beta_a", "-", "plasma beta at r = a"),
    ("t_alfven", "t0", "Alfven crossing time a / v_A"),
    ("t_resistive", "t0", "resistive diffusion time a^2 / eta"),
    ("t_cooling", "t0", "core cooling time at rho = T = 1: 1 / ((gamma-1) C)"),
    # ---- kink (m = 1, axial n >= 1) ----
    ("m1_peak", "a", "largest kink amplitude"),
    ("m1_t_peak", "t0", "time of the largest kink amplitude"),
    ("m1_final", "a", "kink amplitude at the end"),
    ("m1_gamma", "1/t0", "fitted exponential growth rate of the kink"),
    ("m1_gamma_err", "1/t0", "standard error of m1_gamma"),
    ("m1_gamma_r2", "-", "R^2 of the exponential fit (1 = clean exponential)"),
    ("m1_gamma_tA", "-", "kink growth rate in units of 1 / t_alfven"),
    ("m1_t_onset", "t0", "start of the exponential growth window"),
    ("m1_dominant_n", "-", "axial wavenumber (wavelengths along L_z) carrying most of the kink at its peak"),
    ("m1_high_n_frac", "-", "fraction of kink power in n = 2, 3 at the peak (spectrum spread; nan if unresolved)"),
    ("m1_resolved_frac", "-", "share of the kink amplitude carried by n = 1..3 at the peak (the saved diagnostic "
                              "resolves only these; ~0 for columns seeded with n >= 4)"),
    ("seed_n", "-", "axial wavenumber of the seeded m = 0 / m = 1 perturbation (pinch.py: k a ~ 1.2)"),
    ("nq_seed", "-", "seed_n * q_a: Kruskal-Shafranov number of the seeded helix (< 1: unstable)"),
    # ---- sausage (m = 0) ----
    ("m0_peak", "a", "largest sausage (necking) amplitude"),
    ("m0_t_peak", "t0", "time of the largest sausage amplitude"),
    ("m0_gamma", "1/t0", "fitted exponential growth rate of the sausage"),
    ("m0_gamma_err", "1/t0", "standard error of m0_gamma"),
    ("m0_gamma_r2", "-", "R^2 of the sausage fit"),
    # ---- bulk offset (n = 0: the whole column moves) ----
    ("shift_peak", "a", "largest offset of the whole column from the axis"),
    ("shift_t_peak", "t0", "time of the largest offset"),
    ("shift_final", "a", "offset at the end"),
    # ---- geometry ----
    ("radius_max", "a", "largest column radius"),
    ("radius_min", "a", "smallest column radius"),
    ("radius_final", "a", "column radius at the end"),
    ("radius_rate_max", "a/t0", "fastest radius growth (0.1 t0 window)"),
    ("t_mixed", "t0", "first time the radius passed MIXED_RADIUS a (nan: never)"),
    # ---- core and extremes ----
    ("core_density_max", "start", "largest core density / its starting value"),
    ("core_density_t_max", "t0", "time of the largest core density"),
    ("core_density_final", "start", "core density at the end / its starting value"),
    ("core_temp_min", "T0", "lowest core temperature"),
    ("core_temp_t_min", "t0", "time of the lowest core temperature"),
    ("core_temp_final", "T0", "core temperature at the end"),
    ("peak_density_max", "rho0", "highest density anywhere"),
    ("peak_temperature_max", "T0", "highest temperature anywhere"),
    # ---- energy flows, fractions of E0 ----
    ("kinetic_max", "E0", "largest kinetic energy"),
    ("kinetic_t_max", "t0", "time of the largest kinetic energy"),
    ("d_magnetic", "E0", "change in magnetic energy, start to end"),
    ("d_thermal", "E0", "change in thermal energy, start to end"),
    ("d_potential", "E0", "change in gravitational energy, start to end"),
    ("injected", "E0", "net energy the circuit put in (negative: taken out)"),
    ("radiated", "E0", "energy lost to radiation"),
    ("magnetic_to_plasma", "E0", "injected - d_magnetic: energy the field handed to the plasma"),
    # ---- numerical health ----
    ("floor_energy", "E0", "energy added by vacuum floors (large = numerically suspect)"),
    ("energy_error_max", "-", "largest |energy budget error|"),
    ("divb_max", "-", "largest |div B| dx / |B|"),
    ("t_final", "t0", "simulated time reached"),
]
FEATURE_NAMES = [f[0] for f in FEATURES]
PARAM_NAMES = FEATURE_NAMES[:10]


# =====================================================
# getting a run in
# =====================================================

def resample(history, dt=DT_SAVE):
    """Every-step history -> samples every dt (the last sample is always kept)."""
    t = np.asarray(history["t"], dtype=float)
    n = min(len(v) for v in history.values())
    t = t[:n]
    grid = np.arange(0.0, t[-1], dt)
    idx = np.unique(np.append(np.searchsorted(t, grid), n - 1))
    return {k: np.asarray(v[:n], dtype=float)[idx] for k, v in history.items()}


def derived_numbers(sim):
    """Stability numbers at t = 0 (plan section 4), all from the setup alone."""
    s, lv, sv = sim.setup, sim.live, sim.solver
    Lz = sv.nz * sv.dx
    Bt = sim.B_peak                         # B_theta at r = a
    Bz = s.axial_field * Bt
    p_a = sim.T0 * (sim.rho_bg + sim.RHO0 / 4.0)   # Bennett profile at r = a
    return {
        "Lz": Lz, "grid": [sv.nx, sv.ny, sv.nz], "dx": sv.dx,
        "I_bennett": sim.I_bennett, "B_peak": Bt, "v_alfven": sim.v_alfven, "t_alfven": sim.t_alfven,
        "q_a": 2.0 * math.pi * sim.a * Bz / (Lz * Bt),
        "kadomtsev_margin": Bz ** 2 / (Bt ** 2 / 2.0),     # > 1: sausage-stable at the edge
        "lundquist": sim.a * sim.v_alfven / lv.resistivity if lv.resistivity > 0 else float("inf"),
        "beta_a": p_a / ((Bt ** 2 + Bz ** 2) / 2.0),
    }


def derived_from_params(setup, live):
    """
    derived_numbers() without building a simulation: the same formulas as
    ZPinch.__init__ (grid size, Bennett current, peak field, Alfven speed)
    for setup/live dicts, so the GUI can predict while sliders move.
    """
    from ..params import RESOLUTIONS
    N = RESOLUTIONS[setup["resolution"]]
    nz = max(4, int(round(N * setup["length"] / 2.0)) * 2)
    dx = 1.0 / N
    a = float(setup["pinch_radius"])
    rho0 = T0 = 1.0
    k = a * math.sqrt(2.0 * rho0 * T0)
    Bt = k / (2.0 * a)
    v_a = Bt / math.sqrt(rho0)
    Lz = nz * dx
    Bz = setup["axial_field"] * Bt
    eta = live["resistivity"]
    p_a = T0 * (setup["background_density"] + rho0 / 4.0)
    return {
        "Lz": Lz, "grid": [N, N, nz], "dx": dx,
        "I_bennett": 2.0 * math.pi * k, "B_peak": Bt, "v_alfven": v_a, "t_alfven": a / v_a,
        "q_a": 2.0 * math.pi * a * Bz / (Lz * Bt),
        "kadomtsev_margin": Bz ** 2 / (Bt ** 2 / 2.0),
        "lundquist": a * v_a / eta if eta > 0 else float("inf"),
        "beta_a": p_a / ((Bt ** 2 + Bz ** 2) / 2.0),
    }


def start_features(setup, live, der=None):
    """
    Everything known before pressing Start: the parameters and the
    stability numbers (FEATURE_NAMES up to t_cooling, plus seed_n, nq_seed).
    This is what the outcome predictor (model.py) sees.
    """
    der = der or derived_from_params(setup, live)
    a = float(setup["pinch_radius"])
    f = {}
    for k in ("current", "rise_time", "resistivity", "viscosity", "cooling", "gravity"):
        f[k] = float(live[k])
    for k in ("axial_field", "length", "pinch_radius", "background_density"):
        f[k] = float(setup[k])
    I = max(f["current"], 1e-6)
    f["q_a"] = float(der["q_a"])
    f["q_a_driven"] = f["q_a"] / I
    f["kadomtsev_margin"] = float(der["kadomtsev_margin"])
    f["kadomtsev_driven"] = f["kadomtsev_margin"] / I ** 2
    f["lundquist"] = float(der["lundquist"])
    f["beta_a"] = float(der["beta_a"])
    f["t_alfven"] = float(der["t_alfven"])
    f["t_resistive"] = a * a / f["resistivity"] if f["resistivity"] > 0 else math.inf
    f["t_cooling"] = 1.0 / ((GAMMA_GAS - 1.0) * f["cooling"]) if f["cooling"] > 0 else math.inf
    f["seed_n"] = float(max(1, int(round(float(der["Lz"]) / (5.0 * a)))))   # as ZPinch._init_state
    f["nq_seed"] = f["seed_n"] * f["q_a"]
    return f


def run_from_sim(sim):
    """(history, meta) for a live ZPinch, in the same form as a dataset run."""
    from dataclasses import asdict
    meta = {"id": "live", "setup": asdict(sim.setup), "live": asdict(sim.live),
            "derived": derived_numbers(sim), "status": "ok", "reason": "user"}
    return resample(sim.history), meta


def load_npz(path):
    """(history, meta) from a tools/sweep.py run file."""
    with np.load(path) as z:
        meta = json.loads(str(z["meta"]))
        h = {k[2:]: z[k] for k in z.files if k.startswith("h_")}
    return h, meta


# =====================================================
# measurements
# =====================================================

def fit_growth(t, amp, min_ratio=4.0, min_points=8):
    """
    Exponential growth rate of a mode amplitude: a straight-line fit of
    ln(amp) against t over the window where the mode has clearly left its
    starting level (2x the minimum before the peak) and is not yet
    nonlinear (half the peak). Returns None when the amplitude never grew
    by min_ratio (4x leaves at least a 2x-wide window to fit).
    """
    amp = np.maximum(np.asarray(amp, dtype=float), 1e-12)
    ipk = int(np.argmax(amp))
    if ipk < 2:
        return None
    imin = int(np.argmin(amp[:ipk + 1]))
    a_min, a_pk = amp[imin], amp[ipk]
    if a_pk / a_min < min_ratio:
        return None
    seg = amp[imin:ipk + 1]
    i0 = imin + int(np.argmax(seg >= 2.0 * a_min))
    i1 = imin + int(np.argmax(seg >= 0.5 * a_pk))
    if i1 - i0 + 1 < min_points:
        i0, i1 = imin, ipk
    if i1 - i0 + 1 < 3:
        return None
    x, y = t[i0:i1 + 1], np.log(amp[i0:i1 + 1])
    xm = x - x.mean()
    sxx = float(np.sum(xm ** 2))
    if sxx <= 0.0:
        return None
    slope = float(np.sum(xm * (y - y.mean())) / sxx)
    resid = y - (y.mean() + slope * xm)
    ssr = float(np.sum(resid ** 2))
    sst = float(np.sum((y - y.mean()) ** 2))
    n = len(x)
    err = math.sqrt(ssr / (n - 2) / sxx) if n > 2 else float("nan")
    return {"gamma": slope, "gamma_err": err, "r2": 1.0 - ssr / sst if sst > 0 else 0.0,
            "t_start": float(t[i0]), "t_end": float(t[i1])}


def first_time(t, mask):
    """Time of the first True in mask, or nan."""
    idx = np.flatnonzero(mask)
    return float(t[idx[0]]) if idx.size else float("nan")


def _rate_max(t, y, window=0.1):
    w = max(1, int(round(window / max(float(np.median(np.diff(t))), 1e-9)))) if len(t) > 1 else 1
    if len(t) <= w:
        return 0.0
    return float(np.max((y[w:] - y[:-w]) / (t[w:] - t[:-w])))


def compute(h, meta):
    """Feature dict (FEATURE_NAMES, all plain floats) for one run."""
    t = np.asarray(h["t"], dtype=float)
    E0 = float(h["total"][0])
    f = start_features(meta["setup"], meta["live"], meta["derived"])

    m1 = h["m1"]
    ipk = int(np.argmax(m1))
    f["m1_peak"], f["m1_t_peak"], f["m1_final"] = float(m1[ipk]), float(t[ipk]), float(m1[-1])
    fit = fit_growth(t, m1)
    f["m1_gamma"] = fit["gamma"] if fit else 0.0
    f["m1_gamma_err"] = fit["gamma_err"] if fit else float("nan")
    f["m1_gamma_r2"] = fit["r2"] if fit else float("nan")
    f["m1_gamma_tA"] = f["m1_gamma"] * f["t_alfven"]
    f["m1_t_onset"] = fit["t_start"] if fit else float("nan")
    # The history resolves the kink into n = 1, 2, 3 only. A column seeded
    # with n >= 4 (L_z > ~2.1 at a = 0.12) keeps its kink in the seeded helix
    # and its harmonics, and n = 1..3 stay at zero: in the sweep the share of
    # the m1 amplitude in n = 1..3 at the peak has median 1.00 for seed n = 2
    # and 3, and 0.00 for seed n = 4 and 5. Below half, the dominant n is
    # unknown (nan), not the argmax of zeros.
    pw = np.array([h[f"m1_n{n}"][ipk] ** 2 for n in (1, 2, 3)])
    f["m1_resolved_frac"] = float(math.sqrt(pw.sum()) / m1[ipk]) if m1[ipk] > 0 else 0.0
    resolved = f["m1_resolved_frac"] >= 0.5
    f["m1_dominant_n"] = float(np.argmax(pw) + 1) if resolved else float("nan")
    f["m1_high_n_frac"] = float(pw[1:].sum() / pw.sum()) if resolved else float("nan")

    m0 = h["m0"]
    jpk = int(np.argmax(m0))
    f["m0_peak"], f["m0_t_peak"] = float(m0[jpk]), float(t[jpk])
    fit0 = fit_growth(t, m0)
    f["m0_gamma"] = fit0["gamma"] if fit0 else 0.0
    f["m0_gamma_err"] = fit0["gamma_err"] if fit0 else float("nan")
    f["m0_gamma_r2"] = fit0["r2"] if fit0 else float("nan")

    sh = h["shift"]
    kpk = int(np.argmax(sh))
    f["shift_peak"], f["shift_t_peak"], f["shift_final"] = float(sh[kpk]), float(t[kpk]), float(sh[-1])

    R = np.asarray(h["radius"]) / f["pinch_radius"]
    f["radius_max"], f["radius_min"], f["radius_final"] = float(R.max()), float(R.min()), float(R[-1])
    f["radius_rate_max"] = _rate_max(t, R)
    f["t_mixed"] = first_time(t, R >= MIXED_RADIUS)

    rc = np.asarray(h["core_density"]) / h["core_density"][0]
    Tc = np.asarray(h["core_temperature"])
    f["core_density_max"], f["core_density_t_max"] = float(rc.max()), float(t[int(np.argmax(rc))])
    f["core_density_final"] = float(rc[-1])
    f["core_temp_min"], f["core_temp_t_min"] = float(Tc.min()), float(t[int(np.argmin(Tc))])
    f["core_temp_final"] = float(Tc[-1])
    f["peak_density_max"] = float(np.max(h["peak_density"]))
    f["peak_temperature_max"] = float(np.max(h["peak_temperature"]))

    K = np.asarray(h["kinetic"]) / E0
    f["kinetic_max"], f["kinetic_t_max"] = float(K.max()), float(t[int(np.argmax(K))])
    for key, name in (("magnetic", "d_magnetic"), ("thermal", "d_thermal"), ("potential", "d_potential")):
        f[name] = float(h[key][-1] - h[key][0]) / E0
    f["injected"] = float(h["injected"][-1]) / E0
    f["radiated"] = float(h["radiated"][-1]) / E0
    f["magnetic_to_plasma"] = f["injected"] - f["d_magnetic"]

    f["floor_energy"] = float(h["floor"][-1]) / E0
    f["energy_error_max"] = float(np.max(np.abs(h["energy_error"])))
    f["divb_max"] = float(np.max(h["divb"]))
    f["t_final"] = float(t[-1])
    return {k: f[k] for k in FEATURE_NAMES}
