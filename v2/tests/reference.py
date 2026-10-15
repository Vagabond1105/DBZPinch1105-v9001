"""Analytic reference solutions used by the tests."""

import numpy as np


def exact_sod(x, t, x0=0.5, gamma=1.4,
              left=(1.0, 0.0, 1.0), right=(0.125, 0.0, 0.1)):
    """Exact Euler Riemann solution (Toro, ch. 4). Returns rho, u, p at x."""
    rL, uL, pL = left
    rR, uR, pR = right
    cL = np.sqrt(gamma * pL / rL)
    cR = np.sqrt(gamma * pR / rR)
    g1 = (gamma - 1.0) / (2.0 * gamma)
    g2 = (gamma + 1.0) / (2.0 * gamma)

    def f(p, rk, pk, ck):
        if p > pk:
            A = 2.0 / ((gamma + 1.0) * rk)
            B = (gamma - 1.0) / (gamma + 1.0) * pk
            q = np.sqrt(A / (p + B))
            return (p - pk) * q, q * (1.0 - 0.5 * (p - pk) / (p + B))
        r = (p / pk) ** g1
        return 2.0 * ck / (gamma - 1.0) * (r - 1.0), (p / pk) ** (-g2) / (rk * ck)

    p = 0.5 * (pL + pR)
    for _ in range(100):
        fL, dL = f(p, rL, pL, cL)
        fR, dR = f(p, rR, pR, cR)
        dp = (fL + fR + uR - uL) / (dL + dR)
        p = max(p - dp, 1e-12)
        if abs(dp) < 1e-14 * p:
            break
    fL, _ = f(p, rL, pL, cL)
    fR, _ = f(p, rR, pR, cR)
    us = 0.5 * (uL + uR) + 0.5 * (fR - fL)
    ps = p

    xi = (np.asarray(x) - x0) / t
    rho = np.empty_like(xi)
    u = np.empty_like(xi)
    pr = np.empty_like(xi)
    gm = (gamma - 1.0) / (gamma + 1.0)
    for n, s in enumerate(xi):
        if s < us:
            if ps > pL:   # left shock
                rs = rL * (ps / pL + gm) / (gm * ps / pL + 1.0)
                S = uL - cL * np.sqrt(g2 * ps / pL + g1)
                rho[n], u[n], pr[n] = (rL, uL, pL) if s < S else (rs, us, ps)
            else:         # left rarefaction
                cs = cL * (ps / pL) ** g1
                if s < uL - cL:
                    rho[n], u[n], pr[n] = rL, uL, pL
                elif s > us - cs:
                    rho[n], u[n], pr[n] = rL * (ps / pL) ** (1.0 / gamma), us, ps
                else:
                    uu = 2.0 / (gamma + 1.0) * (cL + (gamma - 1.0) / 2.0 * uL + s)
                    cc = 2.0 / (gamma + 1.0) * (cL + (gamma - 1.0) / 2.0 * (uL - s))
                    rho[n] = rL * (cc / cL) ** (2.0 / (gamma - 1.0))
                    u[n] = uu
                    pr[n] = pL * (cc / cL) ** (2.0 * gamma / (gamma - 1.0))
        else:
            if ps > pR:   # right shock
                rs = rR * (ps / pR + gm) / (gm * ps / pR + 1.0)
                S = uR + cR * np.sqrt(g2 * ps / pR + g1)
                rho[n], u[n], pr[n] = (rR, uR, pR) if s > S else (rs, us, ps)
            else:         # right rarefaction
                cs = cR * (ps / pR) ** g1
                if s > uR + cR:
                    rho[n], u[n], pr[n] = rR, uR, pR
                elif s < us + cs:
                    rho[n], u[n], pr[n] = rR * (ps / pR) ** (1.0 / gamma), us, ps
                else:
                    uu = 2.0 / (gamma + 1.0) * (-cR + (gamma - 1.0) / 2.0 * uR + s)
                    cc = 2.0 / (gamma + 1.0) * (cR - (gamma - 1.0) / 2.0 * (uR - s))
                    rho[n] = rR * (cc / cR) ** (2.0 / (gamma - 1.0))
                    u[n] = uu
                    pr[n] = pR * (cc / cR) ** (2.0 * gamma / (gamma - 1.0))
    return rho, u, pr
