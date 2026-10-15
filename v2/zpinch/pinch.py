"""
Z-pinch simulation: a Bennett-equilibrium plasma column carrying an axial
current, driven by an external circuit through the side walls.

Geometry: x, y in [-1/2, 1/2] (side walls), z periodic (a section of a
long column). The drive current I(t) enters as the azimuthal field it
produces in the wall ghost cells - Ampere's law then makes the same total
current flow through the plasma, and any change in I(t) propagates inward
as a fast magnetosonic wave carrying Poynting flux (exactly how a real
pinch is driven by its capacitor bank).

Initial state (Bennett 1934), isothermal at T0 = 1, mu_0 = 1:
    rho(r) = rho_bg + rho0 / (1 + r^2/a^2)^2
    p(r)   = T0 * rho(r)
    B_t(r) = (I_B / 2 pi) r / (r^2 + a^2),    I_B^2 = 8 pi^2 a^2 p0
which satisfies dp/dr = -J_z B_theta exactly. It is in equilibrium but
unstable: sausage (m=0) and kink (m=1) modes grow from the seed
perturbation on the Alfven time a / v_A.
"""

import math
import time

import numpy as np

from . import kernels as K
from .constants import (
    NG, RHO, PR, BX, BY, BZ,
    BC_PINCH_WALL, BC_PERIODIC, SOLVER_HLL, SOLVER_HLLD,
)
from .params import SetupParams, LiveParams, RESOLUTIONS
from .solver import MHDSolver

FIELDS = {
    "Density": K.FIELD_DENSITY,
    "Temperature": K.FIELD_TEMPERATURE,
    "Pressure": K.FIELD_PRESSURE,
    "Current density |J|": K.FIELD_JMAG,
    "Axial current J_z": K.FIELD_JZ,
    "Magnetic field |B|": K.FIELD_BMAG,
    "Speed |v|": K.FIELD_VMAG,
    "Plasma beta": K.FIELD_BETA,
}

HISTORY_KEYS = (
    "t", "dt", "mass", "kinetic", "magnetic", "thermal", "potential", "total",
    "injected", "radiated", "floor", "energy_error", "mass_error",
    "current_drive", "current_measured", "bennett_ratio", "divb",
    "m0", "m1", "shift", "m0_n1", "m0_n2", "m0_n3", "m1_n1", "m1_n2", "m1_n3", "radius", "core_density", "core_temperature",
    "peak_density", "peak_temperature",
)


def _axial_amplitudes(f_hat, n_max=3):
    """Amplitude of axial modes n = 1..n_max from an FFT (both +n and -n,
    which for the complex centre are the two helix handednesses)."""
    nz = f_hat.size
    out = np.zeros(n_max)
    for n in range(1, min(n_max, nz // 2) + 1):
        out[n - 1] = abs(f_hat[n]) if 2 * n == nz else math.hypot(abs(f_hat[n]), abs(f_hat[-n]))
    return out


class ZPinch:

    RHO0 = 1.0
    T0 = 1.0

    def __init__(self, setup=None, live=None):
        self.setup = setup or SetupParams()
        self.live = live or LiveParams()
        s = self.setup

        N = RESOLUTIONS[s.resolution]
        nz = max(4, int(round(N * s.length / 2.0)) * 2)
        dx = 1.0 / N
        self.solver = MHDSolver(N, N, nz, dx, (-0.5, -0.5, -0.5 * nz * dx),
                                (BC_PINCH_WALL, BC_PINCH_WALL, BC_PERIODIC))
        sv = self.solver

        a = s.pinch_radius
        self.a = a
        self.rho_bg = s.background_density
        p0 = self.RHO0 * self.T0
        self.k_bennett = a * math.sqrt(2.0 * p0)           # I_B / (2 pi)
        self.I_bennett = 2.0 * math.pi * self.k_bennett
        self.B_peak = self.k_bennett / (2.0 * a)            # B_theta at r = a
        self.v_alfven = self.B_peak / math.sqrt(self.RHO0)
        self.t_alfven = a / self.v_alfven

        self._init_state()
        self._init_tracers()

        # drive circuit: I(t) relaxes toward live.current * I_B with time
        # constant live.rise_time; evaluated analytically within a step
        self._I_start = self.I_bennett
        self._t_start = 0.0
        self._I_target = self.I_bennett
        self._tau = self.live.rise_time
        sv.drive_current = self.drive_current
        sv.drive_a = a
        sv.T_ref = self.T0
        # vacuum floors: when the rising current lifts plasma off the walls the
        # region behind it empties; without a floor the Alfven speed there
        # diverges and dt -> 0. Everything the floors add is tallied.
        sv.rho_floor = 0.1 * self.rho_bg
        sv.t_floor = 0.02 * self.T0

        self.history = {key: [] for key in HISTORY_KEYS}
        self._apply_live()
        sv.update_primitives(0.0)
        self._t0 = sv.totals()
        self.wall_time = 0.0
        self.last_step_seconds = 0.0
        self._record(sv.W)

    # =====================================================
    # initial conditions
    # =====================================================

    def _init_state(self):
        sv = self.solver
        s = self.setup
        a = self.a
        g = np.s_[NG:-NG]
        X, Y, Z = np.meshgrid(sv.xc[g], sv.yc[g], sv.zc[g], indexing="ij")
        Lz = sv.nz * sv.dx
        rng = np.random.default_rng(s.seed)

        kind = s.perturbation
        eps = s.perturbation_amp
        n_mode = max(1, int(round(Lz / (5.0 * a))))         # k a ~ 1.2, near fastest growth
        kz = 2.0 * math.pi * n_mode / Lz
        use_m0 = kind in ("Sausage (m=0)", "Random + m=0 + m=1")
        use_m1 = kind in ("Kink (m=1)", "Random + m=0 + m=1")
        use_rand = kind in ("Random", "Random + m=0 + m=1")

        # displace (m=1) and radially rescale (m=0) the whole column; the
        # field is built from the same displaced coordinates, which keeps it
        # exactly divergence-free (B_z = const, B_perp depends on x', y')
        x_shift = eps * a * np.cos(kz * Z) if use_m1 else 0.0
        y_shift = eps * a * np.sin(kz * Z) if use_m1 else 0.0
        scale = 1.0 + eps * np.cos(kz * Z + 0.7) if use_m0 else 1.0
        Xp = (X - x_shift) / scale
        Yp = (Y - y_shift) / scale
        r2 = Xp ** 2 + Yp ** 2
        f = 1.0 / (1.0 + r2 / a ** 2) ** 2

        rho = self.rho_bg + self.RHO0 * f
        p = self.T0 * rho
        if use_rand:
            # isobaric density noise: pressure balance is kept, entropy is not
            rho = rho * (1.0 + 0.5 * eps * (2.0 * rng.random(rho.shape) - 1.0) * (f > 0.05))

        k = self.k_bennett
        bx = -k * Yp / (r2 + a ** 2)
        by = k * Xp / (r2 + a ** 2)
        bz = np.full_like(rho, s.axial_field * self.B_peak)
        zero = np.zeros_like(rho)
        sv.set_primitive(rho, zero, zero, zero, p, bx, by, bz)

    def _init_tracers(self):
        """Tracers sampled from the Bennett mass distribution (r < 2.5 a)."""
        sv = self.solver
        n = self.setup.n_tracers
        rng = np.random.default_rng(self.setup.seed + 1)
        u_max = 6.25 / 7.25
        u = rng.random(n) * u_max
        r = self.a * np.sqrt(u / (1.0 - u))
        th = rng.random(n) * 2.0 * math.pi
        z = sv.lo[2] + rng.random(n) * (sv.hi[2] - sv.lo[2])
        self.tracers = np.ascontiguousarray(np.stack([r * np.cos(th), r * np.sin(th), z], axis=1))
        self.tracer_tag = (r / (2.5 * self.a)).astype(np.float32)   # initial radius, for colouring
        self._periodic = np.array([False, False, True])

    # =====================================================
    # drive circuit
    # =====================================================

    def drive_current(self, t):
        return self._I_target + (self._I_start - self._I_target) * math.exp(-(t - self._t_start) / self._tau)

    def _apply_live(self):
        sv = self.solver
        lv = self.live
        sv.eta0 = float(lv.resistivity)
        sv.spitzer = bool(lv.spitzer)
        sv.nu = float(lv.viscosity)
        sv.cooling = float(lv.cooling)
        sv.gy = -float(lv.gravity)
        sv.solver = SOLVER_HLL if lv.solver == "HLL" else SOLVER_HLLD

        # re-anchor the exponential at the current time so changes to the
        # set point / rise time continue smoothly from the present current
        I_now = self.drive_current(sv.t) if hasattr(self, "_I_start") else self.I_bennett
        self._I_start = I_now
        self._t_start = sv.t
        self._I_target = float(lv.current) * self.I_bennett
        self._tau = max(float(lv.rise_time), 1e-6)

    # =====================================================
    # stepping
    # =====================================================

    @property
    def t(self):
        return self.solver.t

    def step(self):
        t_wall = time.perf_counter()
        self._apply_live()
        sv = self.solver
        recorded = []

        def on_prims(W, dt):
            # W is the ghost-filled state at time t: record diagnostics for
            # it, then move tracers through it
            if sv.n_steps > 0:
                recorded.append(self._record(W))
            if self.tracers.shape[0]:
                K.advect_tracers(self.tracers, W, dt, sv.lo, sv.hi, sv.dx, self._periodic, NG)

        sv.step(on_prims=on_prims)
        self.last_step_seconds = time.perf_counter() - t_wall
        self.wall_time += self.last_step_seconds

    # =====================================================
    # diagnostics
    # =====================================================

    def _record(self, W):
        sv = self.solver
        h = self.history
        tot = sv.totals()
        t0 = self._t0
        budget = sv.injected_energy - sv.radiated_energy + sv.floor_energy
        energy_error = (tot["total"] - t0["total"] - budget) / t0["total"]
        mass_error = (tot["mass"] - t0["mass"] - sv.injected_mass - sv.floor_mass) / t0["mass"]

        mom = K.slice_moments(W, sv.xc, sv.yc, self.rho_bg, NG)
        s0 = np.maximum(mom[:, 0], 1e-300)
        xc = mom[:, 1] / s0
        yc = mom[:, 2] / s0
        r2 = np.maximum(mom[:, 3] / s0 - xc ** 2 - yc ** 2, 0.0)
        R = np.sqrt(2.0 * r2)                 # equals a for a Bennett profile
        R_mean = max(float(R.mean()), 1e-12)
        # axial Fourier spectra (n = number of wavelengths along L_z): m=0 from
        # the slice radius R(z), m=1 from the complex slice centre x_c + i y_c.
        # The n=0 centre term is a bulk shift of the whole column (e.g. a
        # gravity sag), not a kink, so m1 only sums n >= 1 (Parseval: m1 is
        # the RMS of the centre about its mean, m0 the RMS of R about its mean)
        nz = R.size
        r_hat = np.fft.fft(R) / nz
        c_hat = np.fft.fft(xc + 1j * yc) / nz
        m0_n = _axial_amplitudes(r_hat) / R_mean
        m1_n = _axial_amplitudes(c_hat) / R_mean
        m0 = float(R.std() / R_mean)
        m1 = float(np.sqrt(np.sum(np.abs(c_hat[1:]) ** 2)) / R_mean)
        shift = float(np.abs(c_hat[0]) / R_mean)
        core_T = float(mom[:, 4].sum() / s0.sum())
        core_rho = float(mom[:, 5].sum() / s0.sum())

        # Ampere's law: circulation of B around the boundary ring of cells
        I_meas = self._measured_current(W)

        # generalised Bennett relation  I^2 / (8 pi) = integral (p + Bz^2/2 - edge) dA
        dA = sv.dx ** 2
        n_cells = sv.nx * sv.ny
        line_p = float(np.mean(mom[:, 6] - mom[:, 7] * n_cells)) * dA
        bennett = I_meas ** 2 / (8.0 * math.pi * line_p) if line_p > 0 else float("nan")

        inner = (slice(NG, -NG),) * 3
        rho_i = W[(RHO,) + inner]
        peak_rho = float(rho_i.max())
        peak_T = float((W[(PR,) + inner] / rho_i).max())

        vals = dict(
            t=sv.t, dt=sv.dt, mass=tot["mass"], kinetic=tot["kinetic"],
            magnetic=tot["magnetic"], thermal=tot["thermal"], potential=tot["potential"],
            total=tot["total"], injected=sv.injected_energy, radiated=sv.radiated_energy,
            floor=sv.floor_energy, energy_error=energy_error, mass_error=mass_error,
            current_drive=self.drive_current(sv.t) / self.I_bennett,
            current_measured=I_meas / self.I_bennett, bennett_ratio=bennett,
            divb=float(K.max_divb(W, sv.dx, NG)), m0=m0, m1=m1, shift=shift,
            m0_n1=m0_n[0], m0_n2=m0_n[1], m0_n3=m0_n[2],
            m1_n1=m1_n[0], m1_n2=m1_n[1], m1_n3=m1_n[2], radius=R_mean,
            core_density=core_rho, core_temperature=core_T,
            peak_density=peak_rho, peak_temperature=peak_T,
        )
        for key in HISTORY_KEYS:
            h[key].append(float(vals[key]))
        return vals

    def _measured_current(self, W):
        """I = (1/mu_0) closed-loop integral of B.dl through the outermost interior cells, z-averaged."""
        sv = self.solver
        lo, hi = NG, NG + sv.nx - 1
        jl, jh = NG, NG + sv.ny - 1
        k = slice(NG, NG + sv.nz)
        ii = slice(NG, NG + sv.nx)
        jj = slice(NG, NG + sv.ny)
        circ = (W[BX, ii, jl, k].sum(axis=0) + W[BY, hi, jj, k].sum(axis=0)
                - W[BX, ii, jh, k].sum(axis=0) - W[BY, lo, jj, k].sum(axis=0))
        return float(circ.mean()) * sv.dx

    def latest(self):
        return {key: vals[-1] for key, vals in self.history.items() if vals}

    # =====================================================
    # display data
    # =====================================================

    def field(self, name):
        """Display field on the interior as float32 (nx, ny, nz). Uses the
        primitives from the most recent step (ghosts valid)."""
        sv = self.solver
        out = np.empty((sv.nx, sv.ny, sv.nz), dtype=np.float32)
        K.derived_field(sv.W, FIELDS[name], sv.dx, NG, out)
        return out

    def snapshot_arrays(self):
        """Primitive fields (float32) for export."""
        sv = self.solver
        sv.flush()
        dm, de = sv.update_primitives()
        sv.floor_mass += dm
        sv.floor_energy += de
        names =("rho", "vx", "vy", "vz", "p", "bx", "by", "bz")
        return {n: sv.W[(q,) + sv.interior].astype(np.float32) for q, n in enumerate(names)}
