"""
Generic 3D MHD solver: owns the state arrays and advances them with
SSP-RK2 (Heun), calling the numba kernels for every heavy loop.

Everything the scheme does to the global mass/energy budget is tallied
(boundary fluxes, floors, radiation) so that

    E_box(t) - E_box(0) == injected - radiated + floors

holds to round-off. That identity is checked by the tests and shown live
in the GUI as the "energy budget error".
"""

import math

import numpy as np

from . import kernels as K
from .constants import (
    GAMMA, NVAR, NG, RHO_FLOOR, P_FLOOR, CFL, DIFF_SAFETY, GLM_ALPHA,
    BC_PERIODIC, SOLVER_HLLD, LIMITER_VANLEER, DIFF_MAX_LAG,
)


class MHDSolver:

    def __init__(self, nx, ny, nz, dx, lo, bc, gamma=GAMMA):
        self.nx, self.ny, self.nz = nx, ny, nz
        self.dx = float(dx)
        self.lo = np.array(lo, dtype=np.float64)
        self.hi = self.lo + self.dx * np.array([nx, ny, nz])
        self.bc = np.array(bc, dtype=np.int64)
        self.gamma = gamma

        shape = (NVAR, nx + 2 * NG, ny + 2 * NG, nz + 2 * NG)
        self.U = np.zeros(shape)
        self.U0 = np.zeros(shape)
        self.W = np.zeros(shape)
        self.dU = np.zeros(shape)
        self.F = np.zeros(shape)

        # cell-centre coordinates including ghosts
        self.xc = self.lo[0] + (np.arange(nx + 2 * NG) - NG + 0.5) * self.dx
        self.yc = self.lo[1] + (np.arange(ny + 2 * NG) - NG + 0.5) * self.dx
        self.zc = self.lo[2] + (np.arange(nz + 2 * NG) - NG + 0.5) * self.dx
        self.interior = (slice(NG, NG + nx), slice(NG, NG + ny), slice(NG, NG + nz))

        # physics / numerics settings (may be changed between steps)
        self.solver = SOLVER_HLLD
        self.limiter = LIMITER_VANLEER
        self.cfl = CFL
        self.eta0 = 0.0
        self.spitzer = False
        self.T_ref = 1.0
        self.eta_cap = 0.0
        self.nu = 0.0
        self.gy = 0.0              # gravity along y (negative = downward)
        self.cooling = 0.0
        self.rho_floor = RHO_FLOOR
        self.t_floor = 0.0
        self.drive_current = 0.0   # callable(t) or float, used by BC_PINCH_WALL
        self.drive_a = 1.0

        self.t = 0.0
        self.dt = 0.0
        self._diff_pending = 0.0
        self._dt_diffusion = math.inf
        self.ch = 0.0
        self.n_steps = 0

        # budget tallies (already multiplied by cell volume / face area)
        self.injected_energy = 0.0
        self.injected_mass = 0.0
        self.floor_energy = 0.0
        self.floor_mass = 0.0
        self.radiated_energy = 0.0

    # =====================================================
    # state helpers
    # =====================================================

    @property
    def dV(self):
        return self.dx ** 3

    def set_primitive(self, rho, vx, vy, vz, p, bx, by, bz):
        """Set interior state from primitive (nx, ny, nz) arrays."""
        W = self.W
        s = (slice(None),) + self.interior
        W[s] = 0.0
        for idx, arr in enumerate((rho, vx, vy, vz, p, bx, by, bz)):
            W[(idx,) + self.interior] = arr
        K.prim_to_cons(W, self.U, self.gamma)

    def _current_at(self, t):
        if callable(self.drive_current):
            return float(self.drive_current(t))
        return float(self.drive_current)

    def update_primitives(self, t=None):
        """cons -> prim on the interior, then ghost cells. Returns floor additions."""
        dm, de = K.cons_to_prim(self.U, self.W, self.gamma, self.rho_floor, P_FLOOR, self.t_floor, NG)
        K.fill_ghosts(self.W, self.bc, NG, self.xc, self.yc,
                      self._current_at(self.t if t is None else t), self.drive_a)
        return dm * self.dV, de * self.dV

    # =====================================================
    # timestep
    # =====================================================

    def stable_dt(self):
        """dt from the current W (call update_primitives first)."""
        smax = K.max_signal_speed(self.W, self.gamma, NG)
        smax = max(smax, 1e-12)
        dt = self.cfl * self.dx / smax
        d_max = 0.0
        if self.eta0 > 0.0:
            d_max = K.max_resistivity(self.W, self.eta0, self.spitzer, self.T_ref,
                                      self._eta_cap(), NG)
        if self.nu > 0.0:
            d_max = max(d_max, 4.0 / 3.0 * self.nu)
        self._dt_diffusion = DIFF_SAFETY * self.dx ** 2 / d_max if d_max > 0.0 else math.inf
        dt = min(dt, self._dt_diffusion)
        return dt, smax

    def _eta_cap(self):
        return self.eta_cap if self.eta_cap > 0.0 else 10.0 * self.eta0

    # =====================================================
    # right-hand side
    # =====================================================

    def _rhs_update(self, dt, a0, a1, diffusive=False):
        """
        One update U = a0*U0 + a1*(U + dt*L(U)), with L evaluated from the
        current W. diffusive=False: ideal-MHD (Riemann) fluxes + gravity;
        diffusive=True: resistive + viscous fluxes only. Returns (energy,
        mass) flowing IN through the non-periodic walls per unit time.
        """
        e_in = 0.0
        m_in = 0.0
        eta_cap = self._eta_cap()
        eta0, nu, gy = (self.eta0, self.nu, 0.0) if diffusive else (0.0, 0.0, self.gy)
        n = (self.nx, self.ny, self.nz)
        for d in range(3):
            K.compute_fluxes(self.W, self.F, d, self.dx, self.gamma, self.ch,
                             self.solver, self.limiter, eta0, self.spitzer,
                             self.T_ref, eta_cap, nu, NG, not diffusive)
            if self.bc[d] != BC_PERIODIC:
                lo_face = [slice(NG, NG + n[a]) for a in range(3)]
                hi_face = list(lo_face)
                lo_face[d] = NG
                hi_face[d] = NG + n[d]
                e_in += self.F[(4,) + tuple(lo_face)].sum() - self.F[(4,) + tuple(hi_face)].sum()
                m_net = self.F[(0,) + tuple(lo_face)] - self.F[(0,) + tuple(hi_face)]
                m_in += m_net.sum()
                if gy != 0.0:
                    # mass crossing a wall carries its gravitational potential
                    # Phi = -gy * y with it (needed to close the E + rho*Phi budget)
                    if d == 1:
                        e_in += -self.gy * (self.lo[1] * self.F[(0,) + tuple(lo_face)].sum()
                                            - self.hi[1] * self.F[(0,) + tuple(hi_face)].sum())
                    else:
                        # wall slice is (ny, nz) for d=0 and (nx, ny) for d=2: reduce to a y profile
                        m_y = m_net.sum(axis=1) if d == 0 else m_net.sum(axis=0)
                        e_in += float(np.dot(m_y, -self.gy * self.yc[NG:NG + self.ny]))
            K.accumulate(self.dU, self.F, d, self.dx, gy, self.W, NG,
                         d, self.U, self.U0, dt, a0, a1)
        dA = self.dx ** 2
        return e_in * dA, m_in * dA

    # =====================================================
    # time step
    # =====================================================

    def step(self, dt_max=None, on_prims=None):
        """
        Advance one step: SSP-RK2 for ideal MHD, then one diffusion pass.
        on_prims(W, dt), if given, is called with
        the fully ghost-filled primitives at the start of the step (used to
        advect tracers without an extra cons->prim pass).
        """
        dm, de = self.update_primitives(self.t)
        self.floor_mass += dm
        self.floor_energy += de

        dt, smax = self.stable_dt()
        if dt_max is not None:
            dt = min(dt, dt_max)
        self.dt = dt
        self.ch = smax

        if on_prims is not None:
            on_prims(self.W, dt)

        np.copyto(self.U0, self.U)

        # stage 1: U1 = U0 + dt L(U0)
        e1, m1 = self._rhs_update(dt, 0.0, 1.0)

        # stage 2: U = 1/2 U0 + 1/2 (U1 + dt L(U1)). Floors applied to U1 here
        # only reach the final state with weight 1/2.
        dm, de = self.update_primitives(self.t + dt)
        self.floor_mass += 0.5 * dm
        self.floor_energy += 0.5 * de
        e2, m2 = self._rhs_update(dt, 0.5, 0.5)

        self.injected_energy += 0.5 * dt * (e1 + e2)
        self.injected_mass += 0.5 * dt * (m1 + m2)

        # resistive + viscous terms: operator-split, conservative forward-Euler
        # passes. Diffusion is slow compared with the waves that set dt, so it
        # is applied with the time accumulated over up to DIFF_MAX_LAG steps,
        # never more than its own explicit stability limit allows. A step cut
        # short by dt_max (i.e. landing on a requested output time) flushes it.
        self._diff_pending += dt
        if self.eta0 > 0.0 or self.nu > 0.0:
            limit = min(DIFF_MAX_LAG * dt, self._dt_diffusion)
            if self._diff_pending + dt > limit or (dt_max is not None and dt >= dt_max):
                self._apply_diffusion(self.t + dt)
        else:
            self._diff_pending = 0.0

        K.damp_psi(self.U, math.exp(-GLM_ALPHA * self.ch * dt / self.dx))

        if self.cooling > 0.0:
            lost = K.radiative_cooling(self.U, self.gamma, self.cooling, dt, P_FLOOR, NG)
            self.radiated_energy += lost * self.dV

        self.t += dt
        self.n_steps += 1
        return dt

    def _apply_diffusion(self, t_end):
        """One conservative diffusion pass over the accumulated time, using the state at t_end."""
        dt = self._diff_pending
        self._diff_pending = 0.0
        if dt <= 0.0:
            return
        dm, de = self.update_primitives(t_end)
        self.floor_mass += dm
        self.floor_energy += de
        e_in, m_in = self._rhs_update(dt, 0.0, 1.0, diffusive=True)
        self.injected_energy += dt * e_in
        self.injected_mass += dt * m_in

    def flush(self):
        """Apply any diffusion still pending, so U is complete at the current time."""
        if self._diff_pending > 0.0 and (self.eta0 > 0.0 or self.nu > 0.0):
            self._apply_diffusion(self.t)
        self._diff_pending = 0.0

    # =====================================================
    # diagnostics
    # =====================================================

    def totals(self):
        """dict of volume-integrated mass and energies."""
        s = K.energy_totals(self.U, self.gamma, self.gy, self.yc, NG) * self.dV
        return {
            "mass": s[0],
            "kinetic": s[1],
            "magnetic": s[2],
            "thermal": s[3],
            "potential": s[4],
            "total": s[5] + s[4],
        }

    def interior_prim(self, var):
        return self.W[(var,) + self.interior]
