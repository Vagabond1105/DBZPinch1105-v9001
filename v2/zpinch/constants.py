"""
Normalised units and numerical constants.

Units (Alfvenic normalisation, mu_0 = 1):
    length      L0   = domain width
    density     rho0 = peak density of the initial Bennett profile
    pressure    p0   = peak (on-axis excess) pressure of the Bennett profile
    velocity    v0   = sqrt(p0 / rho0)
    time        t0   = L0 / v0
    magnetic    B0   = sqrt(mu_0 * p0)      (so B^2/2 is a pressure)
    current     I0   = B0 * L0 / mu_0

With mu_0 = 1 the MHD equations below carry no extra factors: magnetic
pressure is B^2/2, J = curl(B), and Ampere's law around a line current I
gives B_theta = I / (2 pi r).
"""

GAMMA = 5.0 / 3.0          # monatomic ideal gas (fully ionised hydrogen)

# conserved-variable slots (primitive slots reuse the same indices:
# RHO, VX, VY, VZ, PR, BX, BY, BZ, PSI)
RHO, MX, MY, MZ, EN, BX, BY, BZ, PSI = range(9)
VX, VY, VZ, PR = MX, MY, MZ, EN
NVAR = 9
NG = 2                     # ghost layers needed by PLM reconstruction

# numerical floors - only ever hit in pathological cases; every unit of
# mass/energy they add is tallied so the energy budget stays honest
RHO_FLOOR = 1e-5
P_FLOOR = 1e-7

CFL = 0.3                  # safe for unsplit 3D RK2 + PLM
DIFF_SAFETY = 1.0 / 6.5    # explicit diffusion: dt <= dx^2 / (6 D) in 3D
DIFF_MAX_LAG = 8           # resistive/viscous pass applied at most every 8 steps (accumulated dt)
GLM_ALPHA = 0.2            # Dedner psi damping: psi *= exp(-alpha ch dt/dx)

# boundary condition codes (per axis)
BC_PERIODIC = 0
BC_OUTFLOW = 1
BC_PINCH_WALL = 2          # slip wall, B in ghosts = field of the drive current
BC_CONDUCTING = 3          # slip wall, perfectly conducting (B_n mirrored)

# Riemann solvers
SOLVER_HLL = 0
SOLVER_HLLD = 1

# slope limiters
LIMITER_MINMOD = 0
LIMITER_VANLEER = 1
LIMITER_MC = 2
