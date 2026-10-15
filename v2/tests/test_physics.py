"""
Physics validation suite. Run with:   .venv/bin/python -m pytest -q tests

Each test compares the solver against an exact solution or an exact
conservation law, along every axis so no direction-specific index bug can
hide.
"""

import os

os.environ.setdefault("NUMBA_THREADING_LAYER", "omp")

import math

import numpy as np
import pytest

from zpinch.constants import NG, BC_PERIODIC, BC_OUTFLOW, RHO, BX, VX, SOLVER_HLL, SOLVER_HLLD
from zpinch.params import SetupParams, LiveParams
from zpinch.pinch import ZPinch
from zpinch.solver import MHDSolver

from .reference import exact_sod


def _line(n, axis, bc_axis, gamma=5.0 / 3.0):
    dims = [2, 2, 2]
    dims[axis] = n
    bc = [BC_PERIODIC] * 3
    bc[axis] = bc_axis
    s = MHDSolver(*dims, 1.0 / n, (0.0, 0.0, 0.0), bc, gamma=gamma)
    c = (s.xc, s.yc, s.zc)[axis][NG:NG + n]
    shape = [1, 1, 1]
    shape[axis] = n
    return s, c.reshape(shape) * np.ones(dims), dims


def _run_to(s, t_end):
    while s.t < t_end - 1e-14:
        s.step(dt_max=t_end - s.t)
    s.update_primitives()


@pytest.mark.parametrize("axis", [0, 1, 2])
def test_sod_shock_tube(axis):
    """Euler limit (B = 0) against the exact Riemann solution."""
    n = 200
    s, x, dims = _line(n, axis, BC_OUTFLOW, gamma=1.4)
    rho = np.where(x < 0.5, 1.0, 0.125)
    p = np.where(x < 0.5, 1.0, 0.1)
    z = np.zeros(dims)
    s.set_primitive(rho, z, z, z, p, z, z, z)
    _run_to(s, 0.2)
    idx = [0, 0, 0]
    idx[axis] = slice(None)
    xs = x[tuple(idx)]
    r_exact, _, _ = exact_sod(xs, 0.2, gamma=1.4)
    err = np.mean(np.abs(s.interior_prim(RHO)[tuple(idx)] - r_exact))
    assert err < 4e-3


@pytest.mark.parametrize("axis", [0, 1, 2])
@pytest.mark.parametrize("solver", [SOLVER_HLLD, SOLVER_HLL])
def test_circularly_polarised_alfven_wave(axis, solver):
    """
    Exact nonlinear MHD solution (Toth 2000): after one period the wave
    must return to its initial state; the error must fall at ~2nd order.
    """
    errs = []
    for n in (32, 64):
        s, x, dims = _line(n, axis, BC_PERIODIC)
        s.solver = solver
        t1, t2 = (axis + 1) % 3, (axis + 2) % 3
        v = [np.zeros(dims) for _ in range(3)]
        b = [np.zeros(dims) for _ in range(3)]
        b[axis][:] = 1.0
        b[t1] = 0.1 * np.sin(2 * np.pi * x)
        b[t2] = 0.1 * np.cos(2 * np.pi * x)
        v[t1] = b[t1].copy()
        v[t2] = b[t2].copy()
        s.set_primitive(np.ones(dims), *v, 0.1 * np.ones(dims), *b)
        b0 = b[t1].copy()
        _run_to(s, 1.0)
        errs.append(np.mean(np.abs(s.interior_prim(BX + t1) - b0)))
    assert errs[1] < 0.15 * 0.1          # < 15 % of the amplitude at 64 cells
    assert math.log2(errs[0] / errs[1]) > 1.5


@pytest.mark.parametrize("axis", [0, 1, 2])
@pytest.mark.parametrize("comp", [1, 2])
@pytest.mark.parametrize("kind", ["resistive", "viscous"])
def test_diffusion_decay_rate(axis, comp, kind):
    """A small sinusoidal B (or shear v) must decay as exp(-D k^2 t); energy stays exactly conserved."""
    n, D, t_end, amp = 64, 0.01, 0.5, 1e-3
    s, x, dims = _line(n, axis, BC_PERIODIC)
    c = (axis + comp) % 3
    v = [np.zeros(dims) for _ in range(3)]
    b = [np.zeros(dims) for _ in range(3)]
    (b if kind == "resistive" else v)[c][:] = amp * np.sin(2 * np.pi * x)
    s.set_primitive(np.ones(dims), *v, 100.0 * np.ones(dims), *b)
    if kind == "resistive":
        s.eta0 = D
    else:
        s.nu = D
    e0 = s.totals()["total"]
    _run_to(s, t_end)
    q = s.interior_prim((BX if kind == "resistive" else VX) + c)
    measured = np.sum(q * np.sin(2 * np.pi * x)) / np.sum(np.sin(2 * np.pi * x) ** 2)
    expected = amp * math.exp(-D * (2 * np.pi) ** 2 * t_end)
    assert abs(measured / expected - 1.0) < 2e-3
    assert abs(s.totals()["total"] / e0 - 1.0) < 1e-13


def _small_pinch(**live):
    setup = SetupParams(n_tracers=500)
    return ZPinch(setup, LiveParams(**live))


def test_pinch_energy_and_mass_budget():
    """
    With a changing drive current, resistivity, viscosity, cooling and
    gravity all on, E_box - E_0 must equal (circuit energy in - radiated)
    to round-off, and mass must be exactly conserved.
    """
    sim = _small_pinch(current=1.6, rise_time=0.05, resistivity=2e-3, viscosity=1e-3,
                       cooling=0.2, gravity=0.3)
    for _ in range(80):
        sim.step()
    L = sim.latest()
    assert abs(L["energy_error"]) < 1e-12
    assert abs(L["mass_error"]) < 1e-12
    assert L["injected"] > 0.0          # the circuit did work on the plasma
    assert L["radiated"] > 0.0


def test_bennett_equilibrium_holds():
    """
    Unperturbed Bennett pinch at I = I_B should stay put: spurious flows are
    pure truncation error (largest next to the axis, where B_theta reverses
    within a cell or two), so they must be small and shrink with resolution.
    """
    peak = []
    for res in ("Fast (48 x 48 x 72)", "Medium (64 x 64 x 96)"):
        sim = ZPinch(SetupParams(perturbation="None", n_tracers=0, resolution=res),
                     LiveParams(resistivity=0.0, viscosity=0.0))
        while sim.t < 0.2:
            sim.step()
        sv = sim.solver
        sv.update_primitives()
        v = np.sqrt(sum(sv.interior_prim(VX + a) ** 2 for a in range(3)))
        peak.append(v.max() / sim.v_alfven)
        assert abs(sim.latest()["bennett_ratio"] - 1.0) < 0.05
    assert peak[0] < 0.05
    assert peak[1] < 0.8 * peak[0]


def test_divergence_stays_small():
    sim = _small_pinch(current=1.5, rise_time=0.05)
    for _ in range(60):
        sim.step()
    assert sim.latest()["divb"] < 0.1


def test_kink_grows():
    """The m=1 kink must grow (exponentially) from the seed - a Z-pinch is kink-unstable."""
    sim = _small_pinch()
    m1_start = sim.latest()["m1"]
    while sim.t < 0.6:
        sim.step()
    assert sim.latest()["m1"] > 3.0 * m1_start


def test_mode_diagnostics_separate_kink_from_shift():
    """A helical n=2 seed shows up in m1_n2 (and m1), a pure sideways shift only in 'shift'."""
    sim = ZPinch(SetupParams(n_tracers=0, perturbation="Kink (m=1)", perturbation_amp=0.05))
    L = sim.latest()
    assert L["m1_n2"] > 10 * max(L["m1_n1"], L["m1_n3"])
    assert abs(L["m1"] - L["m1_n2"]) < 0.1 * L["m1"]
    assert L["shift"] < 0.1 * L["m1"]

    sim = ZPinch(SetupParams(n_tracers=0, perturbation="None"))
    sv = sim.solver
    sv.W[:] = np.roll(sv.W, 2, axis=2)          # move the whole column by 2 cells in y
    L = sim._record(sv.W)
    assert L["shift"] > 0.3 and L["m1"] < 1e-6


def test_presets_apply_on_top_of_defaults():
    from zpinch.params import PRESETS, apply_preset
    setup, live = SetupParams(), LiveParams()
    setup.pinch_radius = 0.15                   # must be reset by the preset
    apply_preset("Saturated kink (Bz = 0.6)", setup, live)
    assert setup.axial_field == 0.6 and setup.pinch_radius == SetupParams().pinch_radius
    for name in PRESETS:
        apply_preset(name, SetupParams(), LiveParams())
