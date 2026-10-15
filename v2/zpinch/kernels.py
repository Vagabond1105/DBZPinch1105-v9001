"""
Numba kernels for 3D resistive, viscous MHD on a uniform Cartesian grid.

Equations (mu_0 = 1), all in conservation form so mass, momentum and
total energy are conserved to round-off by construction:

    d rho / dt + div(rho v)                                        = 0
    d(rho v)/dt + div(rho v v + (p + B^2/2) I - B B - tau)         = rho g
    d E / dt    + div((E + p + B^2/2) v - B (v.B) + eta J x B - tau.v) = rho v.g
    d B / dt    + div(v B - B v) + curl(eta J)                     = 0
    d psi / dt  + ch^2 div B                                       = -damping

    E = p/(gamma-1) + rho v^2/2 + B^2/2,  J = curl B,
    tau = rho nu (grad v + grad v^T - 2/3 (div v) I)

Ohmic heating (eta J^2) and viscous heating are not added by hand: they
fall out of the conservative total-energy equation automatically, because
the resistive/viscous fluxes remove magnetic/kinetic energy and E is
unchanged, so the difference shows up as pressure.

Discretisation: finite-volume Godunov scheme, PLM reconstruction of
primitive variables, HLLD (Miyoshi & Kusano 2005) or HLL Riemann solver,
GLM divergence cleaning (Dedner et al. 2002, Mignone & Tzeferacos 2010),
SSP-RK2 time integration (driven from solver.py).

Array layout: U[var, i, j, k] with NG ghost layers on each side.
F[var, i, j, k] holds the flux through the LOWER face of cell (i, j, k)
in the current sweep direction.
"""

import math

import numpy as np
from numba import njit, prange

from .constants import (
    NVAR, BC_PERIODIC, BC_OUTFLOW, BC_PINCH_WALL, BC_CONDUCTING,
    SOLVER_HLLD, LIMITER_MINMOD, LIMITER_VANLEER,
)

FM = {"nsz", "arcp", "contract", "afn", "reassoc"}
JIT = dict(nogil=True, cache=True, fastmath=FM)
PJIT = dict(parallel=True, nogil=True, cache=True, fastmath=FM)


# =====================================================
# conserved <-> primitive
# =====================================================

@njit(**PJIT)
def cons_to_prim(U, W, gamma, rho_floor, p_floor, t_floor, ng):
    """
    Fills interior W from U. Applies floors (density, and pressure
    p >= max(p_floor, rho * t_floor)) in place on U and returns the
    (mass, energy) the floors added, summed per cell (multiply by dV).
    """
    _, nxg, nyg, nzg = U.shape
    gm1 = gamma - 1.0
    dmass = np.zeros(nxg)
    denergy = np.zeros(nxg)
    for i in prange(ng, nxg - ng):
        for j in range(ng, nyg - ng):
            for k in range(ng, nzg - ng):
                rho = U[0, i, j, k]
                if rho < rho_floor:
                    dmass[i] += rho_floor - rho
                    U[0, i, j, k] = rho_floor
                    rho = rho_floor
                inv = 1.0 / rho
                vx = U[1, i, j, k] * inv
                vy = U[2, i, j, k] * inv
                vz = U[3, i, j, k] * inv
                bx = U[5, i, j, k]
                by = U[6, i, j, k]
                bz = U[7, i, j, k]
                ke = 0.5 * rho * (vx * vx + vy * vy + vz * vz)
                me = 0.5 * (bx * bx + by * by + bz * bz)
                p = gm1 * (U[4, i, j, k] - ke - me)
                p_min = max(p_floor, rho * t_floor)
                if p < p_min:
                    e_new = ke + me + p_min / gm1
                    denergy[i] += e_new - U[4, i, j, k]
                    U[4, i, j, k] = e_new
                    p = p_min
                W[0, i, j, k] = rho
                W[1, i, j, k] = vx
                W[2, i, j, k] = vy
                W[3, i, j, k] = vz
                W[4, i, j, k] = p
                W[5, i, j, k] = bx
                W[6, i, j, k] = by
                W[7, i, j, k] = bz
                W[8, i, j, k] = U[8, i, j, k]
    return dmass.sum(), denergy.sum()


@njit(**PJIT)
def prim_to_cons(W, U, gamma):
    _, nxg, nyg, nzg = W.shape
    gm1 = gamma - 1.0
    for i in prange(nxg):
        for j in range(nyg):
            for k in range(nzg):
                rho = W[0, i, j, k]
                vx = W[1, i, j, k]
                vy = W[2, i, j, k]
                vz = W[3, i, j, k]
                bx = W[5, i, j, k]
                by = W[6, i, j, k]
                bz = W[7, i, j, k]
                U[0, i, j, k] = rho
                U[1, i, j, k] = rho * vx
                U[2, i, j, k] = rho * vy
                U[3, i, j, k] = rho * vz
                U[4, i, j, k] = (W[4, i, j, k] / gm1
                                 + 0.5 * rho * (vx * vx + vy * vy + vz * vz)
                                 + 0.5 * (bx * bx + by * by + bz * bz))
                U[5, i, j, k] = bx
                U[6, i, j, k] = by
                U[7, i, j, k] = bz
                U[8, i, j, k] = W[8, i, j, k]


# =====================================================
# ghost cells (filled on primitives)
# =====================================================

@njit(**JIT)
def _drive_field(x, y, current, a):
    """
    B of the drive current: Bennett-shaped, B_theta = I r / (2 pi (r^2 + a^2)).
    Outside the pinch this is the vacuum field I/(2 pi r) of a line current;
    using the Bennett form keeps the initial equilibrium exact in ghosts.
    """
    r2 = x * x + y * y
    f = current / (2.0 * math.pi * (r2 + a * a))
    return -f * y, f * x


@njit(**PJIT)
def fill_ghosts(W, bc, ng, xc, yc, drive_current, drive_a):
    """
    bc = (bc_x, bc_y, bc_z). Order z -> x -> y so edges/corners are filled
    from already-valid data.
    """
    nv, nxg, nyg, nzg = W.shape
    nx = nxg - 2 * ng
    ny = nyg - 2 * ng
    nz = nzg - 2 * ng

    # ---- z ----
    for i in prange(ng, nxg - ng):
        for j in range(ng, nyg - ng):
            for s in range(ng):
                lo = ng - 1 - s
                hi = nz + ng + s
                if bc[2] == BC_PERIODIC:
                    slo, shi = lo + nz, hi - nz
                elif bc[2] == BC_OUTFLOW:
                    slo, shi = ng, nz + ng - 1
                else:
                    slo, shi = ng + s, nz + ng - 1 - s
                for v in range(nv):
                    W[v, i, j, lo] = W[v, i, j, slo]
                    W[v, i, j, hi] = W[v, i, j, shi]
                if bc[2] == BC_PINCH_WALL or bc[2] == BC_CONDUCTING:
                    W[3, i, j, lo] = -W[3, i, j, lo]
                    W[3, i, j, hi] = -W[3, i, j, hi]
                    W[7, i, j, lo] = -W[7, i, j, lo]
                    W[7, i, j, hi] = -W[7, i, j, hi]

    # ---- x ----
    for k in prange(nzg):
        for j in range(ng, nyg - ng):
            for s in range(ng):
                lo = ng - 1 - s
                hi = nx + ng + s
                if bc[0] == BC_PERIODIC:
                    slo, shi = lo + nx, hi - nx
                elif bc[0] == BC_OUTFLOW:
                    slo, shi = ng, nx + ng - 1
                else:
                    slo, shi = ng + s, nx + ng - 1 - s
                for v in range(nv):
                    W[v, lo, j, k] = W[v, slo, j, k]
                    W[v, hi, j, k] = W[v, shi, j, k]
                if bc[0] == BC_PINCH_WALL or bc[0] == BC_CONDUCTING:
                    W[1, lo, j, k] = -W[1, lo, j, k]
                    W[1, hi, j, k] = -W[1, hi, j, k]
                if bc[0] == BC_CONDUCTING:
                    W[5, lo, j, k] = -W[5, lo, j, k]
                    W[5, hi, j, k] = -W[5, hi, j, k]
                elif bc[0] == BC_PINCH_WALL:
                    bxl, byl = _drive_field(xc[lo], yc[j], drive_current, drive_a)
                    bxh, byh = _drive_field(xc[hi], yc[j], drive_current, drive_a)
                    W[5, lo, j, k] = bxl
                    W[6, lo, j, k] = byl
                    W[5, hi, j, k] = bxh
                    W[6, hi, j, k] = byh

    # ---- y ----
    for k in prange(nzg):
        for i in range(nxg):
            for s in range(ng):
                lo = ng - 1 - s
                hi = ny + ng + s
                if bc[1] == BC_PERIODIC:
                    slo, shi = lo + ny, hi - ny
                elif bc[1] == BC_OUTFLOW:
                    slo, shi = ng, ny + ng - 1
                else:
                    slo, shi = ng + s, ny + ng - 1 - s
                for v in range(nv):
                    W[v, i, lo, k] = W[v, i, slo, k]
                    W[v, i, hi, k] = W[v, i, shi, k]
                if bc[1] == BC_PINCH_WALL or bc[1] == BC_CONDUCTING:
                    W[2, i, lo, k] = -W[2, i, lo, k]
                    W[2, i, hi, k] = -W[2, i, hi, k]
                if bc[1] == BC_CONDUCTING:
                    W[6, i, lo, k] = -W[6, i, lo, k]
                    W[6, i, hi, k] = -W[6, i, hi, k]
                elif bc[1] == BC_PINCH_WALL:
                    bxl, byl = _drive_field(xc[i], yc[lo], drive_current, drive_a)
                    bxh, byh = _drive_field(xc[i], yc[hi], drive_current, drive_a)
                    W[5, i, lo, k] = bxl
                    W[6, i, lo, k] = byl
                    W[5, i, hi, k] = bxh
                    W[6, i, hi, k] = byh


# =====================================================
# timestep
# =====================================================

@njit(**JIT)
def _fast_speed(rho, p, bn, b2, gamma):
    gp = gamma * p
    s = gp + b2
    disc = s * s - 4.0 * gp * bn * bn
    if disc < 0.0:
        disc = 0.0
    return math.sqrt(0.5 * (s + math.sqrt(disc)) / rho)


@njit(**PJIT)
def max_signal_speed(W, gamma, ng):
    _, nxg, nyg, nzg = W.shape
    smax = np.zeros(nxg)
    for i in prange(ng, nxg - ng):
        m = 0.0
        for j in range(ng, nyg - ng):
            for k in range(ng, nzg - ng):
                rho = W[0, i, j, k]
                p = W[4, i, j, k]
                bx = W[5, i, j, k]
                by = W[6, i, j, k]
                bz = W[7, i, j, k]
                b2 = bx * bx + by * by + bz * bz
                sx = abs(W[1, i, j, k]) + _fast_speed(rho, p, bx, b2, gamma)
                sy = abs(W[2, i, j, k]) + _fast_speed(rho, p, by, b2, gamma)
                sz = abs(W[3, i, j, k]) + _fast_speed(rho, p, bz, b2, gamma)
                s = max(sx, max(sy, sz))
                if s > m:
                    m = s
        smax[i] = m
    return smax.max()


@njit(**JIT)
def _eta_of_T(T, eta0, spitzer, T_ref, eta_cap):
    if not spitzer:
        return eta0
    Tn = max(T / T_ref, 1e-6)
    eta = eta0 * Tn ** -1.5
    return min(eta, eta_cap)


@njit(**PJIT)
def max_resistivity(W, eta0, spitzer, T_ref, eta_cap, ng):
    _, nxg, nyg, nzg = W.shape
    out = np.zeros(nxg)
    if not spitzer:
        return eta0
    for i in prange(ng, nxg - ng):
        m = 0.0
        for j in range(ng, nyg - ng):
            for k in range(ng, nzg - ng):
                e = _eta_of_T(W[4, i, j, k] / W[0, i, j, k], eta0, spitzer, T_ref, eta_cap)
                if e > m:
                    m = e
        out[i] = m
    return out.max()


# =====================================================
# reconstruction
# =====================================================

@njit(**JIT)
def _slope(qm, q0, qp, limiter):
    dl = q0 - qm
    dr = qp - q0
    if dl * dr <= 0.0:
        return 0.0
    if limiter == LIMITER_MINMOD:
        return dl if abs(dl) < abs(dr) else dr
    if limiter == LIMITER_VANLEER:
        return 2.0 * dl * dr / (dl + dr)
    # monotonised central
    dc = 0.5 * (dl + dr)
    m = min(2.0 * abs(dl), min(2.0 * abs(dr), abs(dc)))
    return m if dc > 0.0 else -m


# =====================================================
# riemann solvers (local frame: n = normal, t1/t2 = tangential)
# =====================================================

@njit(**JIT)
def _riemann(rL, uL, vL, wL, pL, byL, bzL,
             rR, uR, vR, wR, pR, byR, bzR,
             bx, gamma, solver, out):
    """
    MHD flux in the face-normal frame. bx is the (GLM-corrected) normal
    field, shared by both states. Writes 7 fluxes to out:
    rho, m_n, m_t1, m_t2, E, B_t1, B_t2.
    """
    gm1 = gamma - 1.0
    bx2 = bx * bx

    b2L = bx2 + byL * byL + bzL * bzL
    b2R = bx2 + byR * byR + bzR * bzR
    ptL = pL + 0.5 * b2L
    ptR = pR + 0.5 * b2R
    eL = pL / gm1 + 0.5 * rL * (uL * uL + vL * vL + wL * wL) + 0.5 * b2L
    eR = pR / gm1 + 0.5 * rR * (uR * uR + vR * vR + wR * wR) + 0.5 * b2R
    vbL = uL * bx + vL * byL + wL * bzL
    vbR = uR * bx + vR * byR + wR * bzR

    cfL = _fast_speed(rL, pL, bx, b2L, gamma)
    cfR = _fast_speed(rR, pR, bx, b2R, gamma)
    SL = min(uL - cfL, uR - cfR)
    SR = max(uL + cfL, uR + cfR)

    # physical fluxes
    fL0 = rL * uL
    fL1 = rL * uL * uL + ptL - bx2
    fL2 = rL * uL * vL - bx * byL
    fL3 = rL * uL * wL - bx * bzL
    fL4 = (eL + ptL) * uL - bx * vbL
    fL5 = byL * uL - bx * vL
    fL6 = bzL * uL - bx * wL

    fR0 = rR * uR
    fR1 = rR * uR * uR + ptR - bx2
    fR2 = rR * uR * vR - bx * byR
    fR3 = rR * uR * wR - bx * bzR
    fR4 = (eR + ptR) * uR - bx * vbR
    fR5 = byR * uR - bx * vR
    fR6 = bzR * uR - bx * wR

    if SL >= 0.0:
        out[0] = fL0; out[1] = fL1; out[2] = fL2; out[3] = fL3
        out[4] = fL4; out[5] = fL5; out[6] = fL6
        return
    if SR <= 0.0:
        out[0] = fR0; out[1] = fR1; out[2] = fR2; out[3] = fR3
        out[4] = fR4; out[5] = fR5; out[6] = fR6
        return

    if solver != SOLVER_HLLD:
        idS = 1.0 / (SR - SL)
        sLR = SL * SR
        out[0] = (SR * fL0 - SL * fR0 + sLR * (rR - rL)) * idS
        out[1] = (SR * fL1 - SL * fR1 + sLR * (rR * uR - rL * uL)) * idS
        out[2] = (SR * fL2 - SL * fR2 + sLR * (rR * vR - rL * vL)) * idS
        out[3] = (SR * fL3 - SL * fR3 + sLR * (rR * wR - rL * wL)) * idS
        out[4] = (SR * fL4 - SL * fR4 + sLR * (eR - eL)) * idS
        out[5] = (SR * fL5 - SL * fR5 + sLR * (byR - byL)) * idS
        out[6] = (SR * fL6 - SL * fR6 + sLR * (bzR - bzL)) * idS
        return

    # ---- HLLD ----
    sLu = SL - uL
    sRu = SR - uR
    den = sRu * rR - sLu * rL
    SM = (sRu * rR * uR - sLu * rL * uL - ptR + ptL) / den
    pts = (sRu * rR * ptL - sLu * rL * ptR + rL * rR * sRu * sLu * (uR - uL)) / den

    # left star state
    rLs = rL * sLu / (SL - SM)
    dL = rL * sLu * (SL - SM) - bx2
    if abs(dL) < 1e-8 * pts:
        vLs = vL; wLs = wL; byLs = byL; bzLs = bzL
    else:
        tmp = bx * (SM - uL) / dL
        vLs = vL - byL * tmp
        wLs = wL - bzL * tmp
        tmp = (rL * sLu * sLu - bx2) / dL
        byLs = byL * tmp
        bzLs = bzL * tmp
    vbLs = SM * bx + vLs * byLs + wLs * bzLs
    eLs = (sLu * eL - ptL * uL + pts * SM + bx * (vbL - vbLs)) / (SL - SM)

    # right star state
    rRs = rR * sRu / (SR - SM)
    dR = rR * sRu * (SR - SM) - bx2
    if abs(dR) < 1e-8 * pts:
        vRs = vR; wRs = wR; byRs = byR; bzRs = bzR
    else:
        tmp = bx * (SM - uR) / dR
        vRs = vR - byR * tmp
        wRs = wR - bzR * tmp
        tmp = (rR * sRu * sRu - bx2) / dR
        byRs = byR * tmp
        bzRs = bzR * tmp
    vbRs = SM * bx + vRs * byRs + wRs * bzRs
    eRs = (sRu * eR - ptR * uR + pts * SM + bx * (vbR - vbRs)) / (SR - SM)

    sqL = math.sqrt(rLs)
    sqR = math.sqrt(rRs)
    SLs = SM - abs(bx) / sqL
    SRs = SM + abs(bx) / sqR

    # F*_L = F_L + S_L (U*_L - U_L)
    fsL0 = fL0 + SL * (rLs - rL)
    fsL1 = fL1 + SL * (rLs * SM - rL * uL)
    fsL2 = fL2 + SL * (rLs * vLs - rL * vL)
    fsL3 = fL3 + SL * (rLs * wLs - rL * wL)
    fsL4 = fL4 + SL * (eLs - eL)
    fsL5 = fL5 + SL * (byLs - byL)
    fsL6 = fL6 + SL * (bzLs - bzL)

    fsR0 = fR0 + SR * (rRs - rR)
    fsR1 = fR1 + SR * (rRs * SM - rR * uR)
    fsR2 = fR2 + SR * (rRs * vRs - rR * vR)
    fsR3 = fR3 + SR * (rRs * wRs - rR * wR)
    fsR4 = fR4 + SR * (eRs - eR)
    fsR5 = fR5 + SR * (byRs - byR)
    fsR6 = fR6 + SR * (bzRs - bzR)

    if SLs >= 0.0:
        out[0] = fsL0; out[1] = fsL1; out[2] = fsL2; out[3] = fsL3
        out[4] = fsL4; out[5] = fsL5; out[6] = fsL6
        return
    if SRs <= 0.0:
        out[0] = fsR0; out[1] = fsR1; out[2] = fsR2; out[3] = fsR3
        out[4] = fsR4; out[5] = fsR5; out[6] = fsR6
        return

    # double-star (rotational discontinuity) states; only reached if bx != 0
    sgn = 1.0 if bx >= 0.0 else -1.0
    isq = 1.0 / (sqL + sqR)
    vss = (sqL * vLs + sqR * vRs + (byRs - byLs) * sgn) * isq
    wss = (sqL * wLs + sqR * wRs + (bzRs - bzLs) * sgn) * isq
    byss = (sqL * byRs + sqR * byLs + sqL * sqR * (vRs - vLs) * sgn) * isq
    bzss = (sqL * bzRs + sqR * bzLs + sqL * sqR * (wRs - wLs) * sgn) * isq
    vbss = SM * bx + vss * byss + wss * bzss

    if SM >= 0.0:
        eLss = eLs - sqL * (vbLs - vbss) * sgn
        out[0] = fsL0
        out[1] = fsL1
        out[2] = fsL2 + SLs * (rLs * vss - rLs * vLs)
        out[3] = fsL3 + SLs * (rLs * wss - rLs * wLs)
        out[4] = fsL4 + SLs * (eLss - eLs)
        out[5] = fsL5 + SLs * (byss - byLs)
        out[6] = fsL6 + SLs * (bzss - bzLs)
    else:
        eRss = eRs + sqR * (vbRs - vbss) * sgn
        out[0] = fsR0
        out[1] = fsR1
        out[2] = fsR2 + SRs * (rRs * vss - rRs * vRs)
        out[3] = fsR3 + SRs * (rRs * wss - rRs * wRs)
        out[4] = fsR4 + SRs * (eRss - eRs)
        out[5] = fsR5 + SRs * (byss - byRs)
        out[6] = fsR6 + SRs * (bzss - bzRs)


# =====================================================
# face fluxes
# =====================================================

@njit(**JIT)
def _dface(W, q, i, j, k, d, a, oi, oj, ok, inv_dx):
    """
    d q / d x_a at the lower d-face of cell (i,j,k): compact difference
    normal to the face, averaged central differences tangential to it.
    """
    if a == d:
        return (W[q, i, j, k] - W[q, i - oi, j - oj, k - ok]) * inv_dx
    ai = 1 if a == 0 else 0
    aj = 1 if a == 1 else 0
    ak = 1 if a == 2 else 0
    return 0.25 * inv_dx * (
        W[q, i + ai, j + aj, k + ak] - W[q, i - ai, j - aj, k - ak]
        + W[q, i - oi + ai, j - oj + aj, k - ok + ak]
        - W[q, i - oi - ai, j - oj - aj, k - ok - ak]
    )


@njit(**PJIT)
def compute_fluxes(W, F, d, dx, gamma, ch, solver, limiter,
                   eta0, spitzer, T_ref, eta_cap, nu, ng, hyperbolic):
    """
    Fluxes through every lower d-face of the interior (+1 layer in d).
    hyperbolic=False skips the Riemann solve and returns only the
    resistive/viscous fluxes (used for the once-per-step diffusion pass).
    """
    nv, nxg, nyg, nzg = W.shape
    oi = 1 if d == 0 else 0
    oj = 1 if d == 1 else 0
    ok = 1 if d == 2 else 0
    t1 = (d + 1) % 3
    t2 = (d + 2) % 3
    inv_dx = 1.0 / dx
    ch2 = ch * ch
    ni = nxg - 2 * ng + oi
    nj = nyg - 2 * ng + oj

    # flattened (i, j) loop: fine-grained work units balance better on
    # hybrid (performance + efficiency core) CPUs than one slab per thread
    for ij in prange(ni * nj):
        i = ng + ij // nj
        j = ng + ij % nj
        WL = np.empty(nv)
        WR = np.empty(nv)
        fl = np.empty(7)
        for k in range(ng, nzg - ng + ok):
            if not hyperbolic:
                for v in range(nv):
                    F[v, i, j, k] = 0.0
            else:
                # ---- PLM reconstruction (cell L = c - e_d, cell R = c) ----
                for v in range(nv):
                    qmm = W[v, i - 2 * oi, j - 2 * oj, k - 2 * ok]
                    qm = W[v, i - oi, j - oj, k - ok]
                    q0 = W[v, i, j, k]
                    qp = W[v, i + oi, j + oj, k + ok]
                    WL[v] = qm + 0.5 * _slope(qmm, qm, q0, limiter)
                    WR[v] = q0 - 0.5 * _slope(qm, q0, qp, limiter)
                if WL[0] <= 0.0 or WR[0] <= 0.0 or WL[4] <= 0.0 or WR[4] <= 0.0:
                    for v in range(nv):
                        WL[v] = W[v, i - oi, j - oj, k - ok]
                        WR[v] = W[v, i, j, k]

                # ---- GLM: exact solution of the (B_n, psi) subsystem ----
                bnL = WL[5 + d]
                bnR = WR[5 + d]
                bn = 0.5 * (bnL + bnR) - 0.5 * (WR[8] - WL[8]) / ch
                psi = 0.5 * (WL[8] + WR[8]) - 0.5 * ch * (bnR - bnL)

                _riemann(WL[0], WL[1 + d], WL[1 + t1], WL[1 + t2], WL[4], WL[5 + t1], WL[5 + t2],
                         WR[0], WR[1 + d], WR[1 + t1], WR[1 + t2], WR[4], WR[5 + t1], WR[5 + t2],
                         bn, gamma, solver, fl)

                F[0, i, j, k] = fl[0]
                F[1 + d, i, j, k] = fl[1]
                F[1 + t1, i, j, k] = fl[2]
                F[1 + t2, i, j, k] = fl[3]
                F[4, i, j, k] = fl[4]
                F[5 + d, i, j, k] = psi
                F[5 + t1, i, j, k] = fl[5]
                F[5 + t2, i, j, k] = fl[6]
                F[8, i, j, k] = ch2 * bn

            rhoL = W[0, i - oi, j - oj, k - ok]
            rhoR = W[0, i, j, k]

            # ---- resistive: B flux = eps_{i d k} eta J_k,  E flux = eta (J x B)_d ----
            # only the two J components tangential to the face are needed:
            # with (d, t1, t2) cyclic: J_t1 = dB_d/dx_t2 - dB_t2/dx_d,
            #                         J_t2 = dB_t1/dx_d - dB_d/dx_t1
            if eta0 > 0.0:
                T = 0.5 * (W[4, i - oi, j - oj, k - ok] / rhoL + W[4, i, j, k] / rhoR)
                eta = _eta_of_T(T, eta0, spitzer, T_ref, eta_cap)
                j_t1 = (_dface(W, 5 + d, i, j, k, d, t2, oi, oj, ok, inv_dx)
                        - _dface(W, 5 + t2, i, j, k, d, d, oi, oj, ok, inv_dx))
                j_t2 = (_dface(W, 5 + t1, i, j, k, d, d, oi, oj, ok, inv_dx)
                        - _dface(W, 5 + d, i, j, k, d, t1, oi, oj, ok, inv_dx))
                b_t1 = 0.5 * (W[5 + t1, i - oi, j - oj, k - ok] + W[5 + t1, i, j, k])
                b_t2 = 0.5 * (W[5 + t2, i - oi, j - oj, k - ok] + W[5 + t2, i, j, k])
                # (d, t1, t2) is a cyclic permutation, so eps_{t1 d t2} = -1, eps_{t2 d t1} = +1
                F[5 + t1, i, j, k] -= eta * j_t2
                F[5 + t2, i, j, k] += eta * j_t1
                F[4, i, j, k] += eta * (j_t1 * b_t2 - j_t2 * b_t1)

            # ---- viscous: momentum flux -tau_{d b}, energy flux -tau_{d b} v_b ----
            if nu > 0.0:
                mu = nu * 0.5 * (rhoL + rhoR)
                divv = (_dface(W, 1, i, j, k, d, 0, oi, oj, ok, inv_dx)
                        + _dface(W, 2, i, j, k, d, 1, oi, oj, ok, inv_dx)
                        + _dface(W, 3, i, j, k, d, 2, oi, oj, ok, inv_dx))
                work = 0.0
                for b in range(3):
                    tau = mu * (_dface(W, 1 + b, i, j, k, d, d, oi, oj, ok, inv_dx)
                                + _dface(W, 1 + d, i, j, k, d, b, oi, oj, ok, inv_dx))
                    if b == d:
                        tau -= mu * (2.0 / 3.0) * divv
                    vf = 0.5 * (W[1 + b, i - oi, j - oj, k - ok] + W[1 + b, i, j, k])
                    F[1 + b, i, j, k] -= tau
                    work += tau * vf
                F[4, i, j, k] -= work


@njit(**PJIT)
def accumulate(dU, F, d, dx, gy, W, ng, mode, U, U0, dt, a0, a1):
    """
    Adds -dF/dx along d into dU. For the y sweep also adds gravity
    (g = gy e_y): momentum source rho g, energy source g * (face mass flux
    averaged to the cell) - this form makes E + rho*Phi conserved exactly.

    mode 0: dU  = contribution          (first sweep, no separate zeroing pass)
    mode 1: dU += contribution
    mode 2: U   = a0*U0 + a1*(U + dt*(dU + contribution))   (last sweep, RK update fused in)
    """
    nv, nxg, nyg, nzg = dU.shape
    oi = 1 if d == 0 else 0
    oj = 1 if d == 1 else 0
    ok = 1 if d == 2 else 0
    inv_dx = 1.0 / dx
    nx = nxg - 2 * ng
    ny = nyg - 2 * ng
    for ij in prange(nx * ny):
        i = ng + ij // ny
        j = ng + ij % ny
        for v in range(nv):
            for k in range(ng, nzg - ng):
                c = -(F[v, i + oi, j + oj, k + ok] - F[v, i, j, k]) * inv_dx
                if d == 1 and gy != 0.0:
                    if v == 2:
                        c += W[0, i, j, k] * gy
                    elif v == 4:
                        c += gy * 0.5 * (F[0, i, j, k] + F[0, i, j + 1, k])
                if mode == 0:
                    dU[v, i, j, k] = c
                elif mode == 1:
                    dU[v, i, j, k] += c
                else:
                    U[v, i, j, k] = a0 * U0[v, i, j, k] + a1 * (U[v, i, j, k] + dt * (dU[v, i, j, k] + c))


@njit(**PJIT)
def damp_psi(U, factor):
    _, nxg, nyg, nzg = U.shape
    for i in prange(nxg):
        for j in range(nyg):
            for k in range(nzg):
                U[8, i, j, k] *= factor


@njit(**PJIT)
def radiative_cooling(U, gamma, coeff, dt, p_floor, ng):
    """
    Optically-thin bremsstrahlung, P_rad = coeff * rho^2 * sqrt(T), taken
    out of the total energy. Limited so a cell can lose at most half its
    thermal energy per step. Returns energy radiated (per unit dV).
    """
    _, nxg, nyg, nzg = U.shape
    gm1 = gamma - 1.0
    lost = np.zeros(nxg)
    for i in prange(ng, nxg - ng):
        for j in range(ng, nyg - ng):
            for k in range(ng, nzg - ng):
                rho = U[0, i, j, k]
                inv = 1.0 / rho
                ke = 0.5 * (U[1, i, j, k] ** 2 + U[2, i, j, k] ** 2 + U[3, i, j, k] ** 2) * inv
                me = 0.5 * (U[5, i, j, k] ** 2 + U[6, i, j, k] ** 2 + U[7, i, j, k] ** 2)
                eint = U[4, i, j, k] - ke - me
                if eint <= p_floor / gm1:
                    continue
                T = gm1 * eint * inv
                loss = coeff * rho * rho * math.sqrt(T) * dt
                cap = 0.5 * (eint - p_floor / gm1)
                if loss > cap:
                    loss = cap
                U[4, i, j, k] -= loss
                lost[i] += loss
    return lost.sum()


# =====================================================
# diagnostics
# =====================================================

@njit(**PJIT)
def energy_totals(U, gamma, gy, yc, ng):
    """Per-unit-volume sums: mass, kinetic, magnetic, thermal, potential, total E."""
    _, nxg, nyg, nzg = U.shape
    gm1 = gamma - 1.0
    acc = np.zeros((nxg, 6))
    for i in prange(ng, nxg - ng):
        for j in range(ng, nyg - ng):
            phi = -gy * yc[j]
            for k in range(ng, nzg - ng):
                rho = U[0, i, j, k]
                ke = 0.5 * (U[1, i, j, k] ** 2 + U[2, i, j, k] ** 2 + U[3, i, j, k] ** 2) / rho
                me = 0.5 * (U[5, i, j, k] ** 2 + U[6, i, j, k] ** 2 + U[7, i, j, k] ** 2)
                acc[i, 0] += rho
                acc[i, 1] += ke
                acc[i, 2] += me
                acc[i, 3] += U[4, i, j, k] - ke - me
                acc[i, 4] += rho * phi
                acc[i, 5] += U[4, i, j, k]
    out = np.zeros(6)
    for i in range(nxg):
        for q in range(6):
            out[q] += acc[i, q]
    return out


@njit(**PJIT)
def max_divb(W, dx, ng):
    """max |div B| * dx / |B| (relative divergence error, cell-centred)."""
    _, nxg, nyg, nzg = W.shape
    out = np.zeros(nxg)
    for i in prange(ng, nxg - ng):
        m = 0.0
        for j in range(ng, nyg - ng):
            for k in range(ng, nzg - ng):
                div = 0.5 * (W[5, i + 1, j, k] - W[5, i - 1, j, k]
                             + W[6, i, j + 1, k] - W[6, i, j - 1, k]
                             + W[7, i, j, k + 1] - W[7, i, j, k - 1])
                b = math.sqrt(W[5, i, j, k] ** 2 + W[6, i, j, k] ** 2 + W[7, i, j, k] ** 2)
                r = abs(div) / (b + 1e-12)
                if r > m:
                    m = r
        out[i] = m
    return out.max()


@njit(**PJIT)
def slice_moments(W, xc, yc, rho_bg, ng):
    """
    Per z-slice moments of the pinch, weighted by w = (rho - rho_bg)^2 (the
    square keeps the long Bennett tail from dominating; for a Bennett
    profile sqrt(2 <r^2>_w) is exactly the Bennett radius a).
    Columns: sum w, sum w x, sum w y, sum w r^2, sum w T, sum w rho,
             sum (p + Bz^2/2), mean (p + Bz^2/2) on the boundary ring.
    """
    _, nxg, nyg, nzg = W.shape
    nx = nxg - 2 * ng
    ny = nyg - 2 * ng
    nz = nzg - 2 * ng
    out = np.zeros((nz, 8))
    for k in prange(ng, nzg - ng):
        s0 = 0.0
        sx = 0.0
        sy = 0.0
        sr = 0.0
        sT = 0.0
        sd = 0.0
        sp = 0.0
        edge = 0.0
        n_edge = 0
        for i in range(ng, nxg - ng):
            for j in range(ng, nyg - ng):
                rho = W[0, i, j, k]
                ptot = W[4, i, j, k] + 0.5 * W[7, i, j, k] ** 2
                sp += ptot
                if i == ng or j == ng or i == nxg - ng - 1 or j == nyg - ng - 1:
                    edge += ptot
                    n_edge += 1
                w = rho - rho_bg
                if w > 0.0:
                    w = w * w
                    s0 += w
                    sx += w * xc[i]
                    sy += w * yc[j]
                    sr += w * (xc[i] ** 2 + yc[j] ** 2)
                    sT += w * W[4, i, j, k] / rho
                    sd += w * rho
        out[k - ng, 0] = s0
        out[k - ng, 1] = sx
        out[k - ng, 2] = sy
        out[k - ng, 3] = sr
        out[k - ng, 4] = sT
        out[k - ng, 5] = sd
        out[k - ng, 6] = sp
        out[k - ng, 7] = edge / max(n_edge, 1)
    return out


FIELD_DENSITY, FIELD_TEMPERATURE, FIELD_PRESSURE, FIELD_BMAG, FIELD_JMAG, \
    FIELD_VMAG, FIELD_BETA, FIELD_JZ = range(8)


@njit(**PJIT)
def derived_field(W, code, dx, ng, out):
    """Fills out (nx, ny, nz) float32 with a display field."""
    _, nxg, nyg, nzg = W.shape
    h = 0.5 / dx
    for i in prange(ng, nxg - ng):
        for j in range(ng, nyg - ng):
            for k in range(ng, nzg - ng):
                if code == FIELD_DENSITY:
                    val = W[0, i, j, k]
                elif code == FIELD_TEMPERATURE:
                    val = W[4, i, j, k] / W[0, i, j, k]
                elif code == FIELD_PRESSURE:
                    val = W[4, i, j, k]
                elif code == FIELD_BMAG:
                    val = math.sqrt(W[5, i, j, k] ** 2 + W[6, i, j, k] ** 2 + W[7, i, j, k] ** 2)
                elif code == FIELD_VMAG:
                    val = math.sqrt(W[1, i, j, k] ** 2 + W[2, i, j, k] ** 2 + W[3, i, j, k] ** 2)
                elif code == FIELD_BETA:
                    b2 = W[5, i, j, k] ** 2 + W[6, i, j, k] ** 2 + W[7, i, j, k] ** 2
                    val = 2.0 * W[4, i, j, k] / (b2 + 1e-30)
                else:
                    jz = h * (W[6, i + 1, j, k] - W[6, i - 1, j, k] - W[5, i, j + 1, k] + W[5, i, j - 1, k])
                    if code == FIELD_JZ:
                        val = jz
                    else:
                        jx = h * (W[7, i, j + 1, k] - W[7, i, j - 1, k] - W[6, i, j, k + 1] + W[6, i, j, k - 1])
                        jy = h * (W[5, i, j, k + 1] - W[5, i, j, k - 1] - W[7, i + 1, j, k] + W[7, i - 1, j, k])
                        val = math.sqrt(jx * jx + jy * jy + jz * jz)
                out[i - ng, j - ng, k - ng] = val


# =====================================================
# tracers
# =====================================================

@njit(**JIT)
def _interp_v(W, x, y, z, x0, y0, z0, inv_dx, ng):
    _, nxg, nyg, nzg = W.shape
    gx = (x - x0) * inv_dx - 0.5 + ng
    gy = (y - y0) * inv_dx - 0.5 + ng
    gz = (z - z0) * inv_dx - 0.5 + ng
    i0 = min(max(int(math.floor(gx)), 0), nxg - 2)
    j0 = min(max(int(math.floor(gy)), 0), nyg - 2)
    k0 = min(max(int(math.floor(gz)), 0), nzg - 2)
    fx = min(max(gx - i0, 0.0), 1.0)
    fy = min(max(gy - j0, 0.0), 1.0)
    fz = min(max(gz - k0, 0.0), 1.0)
    vx = 0.0
    vy = 0.0
    vz = 0.0
    for di in range(2):
        wx = fx if di else 1.0 - fx
        for dj in range(2):
            wy = fy if dj else 1.0 - fy
            for dk in range(2):
                w = wx * wy * (fz if dk else 1.0 - fz)
                vx += w * W[1, i0 + di, j0 + dj, k0 + dk]
                vy += w * W[2, i0 + di, j0 + dj, k0 + dk]
                vz += w * W[3, i0 + di, j0 + dj, k0 + dk]
    return vx, vy, vz


@njit(**JIT)
def _wrap_reflect(p, lo, hi, periodic):
    L = hi - lo
    if periodic:
        return lo + (p - lo) % L
    if p < lo:
        p = 2.0 * lo - p
    if p > hi:
        p = 2.0 * hi - p
    return min(max(p, lo), hi)


@njit(**PJIT)
def advect_tracers(pos, W, dt, lo, hi, dx, periodic, ng):
    """RK2 (midpoint) advection of passive tracers in the cell-centred v field."""
    inv_dx = 1.0 / dx
    for n in prange(pos.shape[0]):
        x = pos[n, 0]
        y = pos[n, 1]
        z = pos[n, 2]
        vx, vy, vz = _interp_v(W, x, y, z, lo[0], lo[1], lo[2], inv_dx, ng)
        xm = _wrap_reflect(x + 0.5 * dt * vx, lo[0], hi[0], periodic[0])
        ym = _wrap_reflect(y + 0.5 * dt * vy, lo[1], hi[1], periodic[1])
        zm = _wrap_reflect(z + 0.5 * dt * vz, lo[2], hi[2], periodic[2])
        vx, vy, vz = _interp_v(W, xm, ym, zm, lo[0], lo[1], lo[2], inv_dx, ng)
        pos[n, 0] = _wrap_reflect(x + dt * vx, lo[0], hi[0], periodic[0])
        pos[n, 1] = _wrap_reflect(y + dt * vy, lo[1], hi[1], periodic[1])
        pos[n, 2] = _wrap_reflect(z + dt * vz, lo[2], hi[2], periodic[2])
