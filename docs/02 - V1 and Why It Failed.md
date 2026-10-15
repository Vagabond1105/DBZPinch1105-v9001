---
tags: [zpinch, mhd, v1, post-mortem, beginner]
aliases: [V1, V1 Post-mortem]
---

# 02 · V1 — what it was, and why it failed

Series: [[01 - Vision]] → **02 V1 and Why It Failed** → [[03 - V2 Changes and Fixes]] → [[04 - V2 Complete Guide]]

> [!summary] TL;DR
> v1 had a good *architecture on paper* (clean module split, parameter objects, a validation mindset) but the **numerical core could not work**: it used an update rule that is mathematically unstable for the equations it solved, on a grid ~100× too large to run in pure NumPy, inside a single thread shared with the window. Measured directly:
> - On a 32³ "validation" grid, total energy grew **×2,700 in 3 steps** and the state was **NaN** ("not a number" — garbage) **within 10–36 steps** — *even with the current switched off*.
> - At its default 240×240×400 grid, **one step took 19.9 s and 12.7 GB of RAM**.
> - Several physics terms were not physics (a field "nudged" toward a target shape, momentum deleted in thin regions, a fluid "bounciness" coefficient, a broken magnetic clean-up step), and two sliders did nothing.

---

## 0. A primer: how simulations break (read this first if you're new)

You don't need to know anything about plasmas for this section. It explains the three ways a simulation goes wrong using a toy problem you can run yourself: `v2/examples/toy_advection.py`.

### 0.1 The toy problem

A block of dye sits in a river that flows right at speed 1. The river is a ring of 100 cells (what leaves on the right comes back on the left). The **exact** answer is trivial: the block just slides along, keeping its shape forever — maximum value 1, minimum 0, total amount of dye 0.2.

```
cells:  ░░░░░░░░░░████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   → flow
                  ↑ block of height 1
```

The computer only knows each cell's value and must work out the next value from the neighbours. Two possible rules:

| Rule | How it decides what a cell becomes next | Used by |
|---|---|---|
| **FTCS** — *Forward in Time, Centred in Space* | looks at the slope between its **left and right** neighbours | v1 |
| **Upwind** (simplest *finite volume*) | dye enters from the **upstream** (left) cell and leaves to the right; each cell gains what flows in and loses what flows out | the idea v2 builds on |

### 0.2 What actually happens (real output)

```
ftcs   CFL=0.5  steps=  20: max=     2.791 min=    -1.791 total=0.200000000000000
ftcs   CFL=0.5  steps= 100: max=      6206 min=     -6399 total=0.200000000000062
ftcs   CFL=0.5  steps= 200: max= 3.748e+08 min=-3.604e+08 total=0.200000000596046
ftcs   CFL=0.05 steps=2000: max=     1.974 min=    -1.542 total=0.200000000000000
upwind CFL=0.5  steps= 100: max=     0.954 min= 1.698e-17 total=0.200000000000000
upwind CFL=0.5  steps= 200: max=    0.8418 min= 1.069e-08 total=0.200000000000000
upwind CFL=1.5  steps=  20: max= 1.099e+05 min=-1.099e+05 total=0.200000000000000
upwind CFL=1.5  steps=  40: max= 8.073e+10 min=-8.073e+10 total=0.200000305175781
```

Four lessons hide in those eight lines:

1. **FTCS explodes.** The block (height 1) becomes 2.8 after 20 steps, 6,206 after 100, 380 million after 200 — with negative "amounts of dye", which is impossible. This is **instability**: every step amplifies the errors of the previous one.
2. **A smaller time step doesn't save it.** With a step 10× smaller (CFL 0.05, 2,000 steps to cover the same distance) FTCS still grows wiggles (1.97 and −1.54) — just more slowly. The rule itself is broken. *(The maths: for FTCS every wave pattern gets multiplied each step by a factor whose size is $\sqrt{1 + (\text{CFL}\cdot\sin k\Delta x)^2} > 1$. Anything multiplied by more than 1 thousands of times explodes.)*
3. **"Total conserved" doesn't mean "correct".** FTCS kept the total at 0.2 almost perfectly *while exploding*. Conservation is necessary but not sufficient.
4. **Even a good rule has a speed limit.** Upwind is perfectly stable at CFL 0.5 (it smears the block a bit — max 0.84 after 200 steps — but never goes wild). At **CFL 1.5** it explodes too. The **CFL number** is "how many cells the flow crosses in one step". If information travels more than one cell per step, the rule can't "see" where it came from. This is the **Courant–Friedrichs–Lewy (CFL) condition**, and every explicit simulation must respect it.

> [!tip] The intuition behind upwinding
> Dye flowing right comes **from the left**. A rule that asks the left neighbour ("upwind") follows the physics; a rule that averages left and right ("central") listens equally to the downstream cell, which has *no* information about what's coming. MHD is full of waves travelling in both directions at different speeds, so a good MHD solver has to figure out, at every cell face, which waves come from which side. That job is done by a **Riemann solver** ([[03 - V2 Changes and Fixes#2.1 Unstable FTCS → Godunov finite-volume scheme]]).

### 0.3 Other vocabulary used below

- **NaN** ("not a number"): what a computer produces from things like 0/0 or ∞−∞. Once one appears it spreads to everything it touches. A simulation full of NaN is dead.
- **Floor**: a minimum value forced onto a quantity (e.g. "density may not go below 10⁻⁶"). Floors stop crashes but *create* mass or energy from nothing, so an honest code must count what they add.
- **Float64 / double precision**: the standard computer number, 8 bytes, about 16 significant digits. That's why "error 10⁻¹⁶" means "exact to the last digit the computer can store".
- **Thread / GIL**: a thread is one line of execution in a program. Python has a **Global Interpreter Lock** (GIL) — only one thread can run Python code at a time. If the window and the physics share one thread, a slow physics step freezes the window.

---

## 1. What v1 contained

```
v1/
├── constants.py          normalised reference units, floors, time-step limits, "provisional" tuning knobs
├── parameters.py         Parameter / InitParams / RTParams (value + bounds + type)
├── simstate.py           SimState: grid arrays, initial column, tracers, history lists, derived fields
├── solvers.py            vector calculus, transport coefficients, dt, boundaries, divergence cleaning, evolve_simstate()
├── cic_interpolation.py  cloud-in-cell interpolation (one particle at a time)
├── visualisation.py      VisPy canvas, density isosurface, tracer markers, iso-level slider
├── ui_ux.py              camera controller, runtime text, buttons, sliders, tutorial box (all drawn inside VisPy)
├── exports_diagnostics.py matplotlib graphs → zip
├── main.py               Application class wiring it all together, two VisPy timers
└── .venv/                (380 MB virtual environment stored inside the project folder)
```

### 1.1 The intended algorithm, in plain words

Every step, `solvers.py:evolve_simstate` did this:

1. Work out velocity, pressure, temperature and the electric current from the stored quantities.
2. Choose a time step $\Delta t$.
3. Move density around: $\rho \leftarrow \rho - \Delta t\,\nabla\cdot(\rho\mathbf{v})$ ("density decreases where plasma flows out").
4. Update momentum: carried along by the flow, pushed by pressure differences, the magnetic force $\mathbf{J}\times\mathbf{B}$, gravity and viscosity.
5. Update internal (heat) energy: carried along, compression heating, resistive heating, a viscous-heating estimate.
6. Update the magnetic field: dragged by the flow, diffused by resistance, **plus a "pull toward a target shape" term** (see §3.5).
7. Fix up the cells on the edges of the box.
8. Move tracer particles one by one.
9. Record diagnostics.

Every derivative ("slope between neighbours") was a **central difference** and every time update was **forward Euler** ("new = old + Δt × rate") — i.e. FTCS from the primer above.

---

## 2. How it was measured

v1's own `SimState` + `evolve_simstate` were run unmodified, with v1's own virtual environment:

| Probe | Grid | Result |
|---|---|---|
| "validation" grid | 32³, cell length 4, column radius 30, current 5 | energy +11 % after 1 step, **×2,700 after 3**, velocities 7×10⁵, **NaN at step 10** |
| same, **current = 0** (pure gas, no magnetism — v1's default) | 32³ | energy ×3,180 after 4 steps, velocities 10¹¹⁵ by step 32, **NaN at step 36** |
| v1 defaults | 240×240×400 | **19.85 s per step**, **12.7 GB** peak memory |

So the failure isn't one bug — the method itself diverges, and at full size it would take days of computer time just to reach the point where it diverges.

---

## 3. Root causes, ranked by severity

Each cause has an **In plain words** line first.

### 3.1 ❌ The time-stepping scheme is unconditionally unstable (fatal)

**In plain words:** v1 used the FTCS rule from the primer — the one that explodes no matter how small the step.

For the simplest wave equation $\partial_t q + c\,\partial_x q = 0$, FTCS multiplies a wave pattern $e^{ikx}$ by

$$
G = 1 - i\,\frac{c\Delta t}{\Delta x}\sin(k\Delta x),\qquad |G|^2 = 1 + \left(\frac{c\Delta t}{\Delta x}\right)^2\sin^2(k\Delta x) > 1
$$

every step. $|G| > 1$ for **every** step size. MHD is a system of such wave equations (sound waves, Alfvén waves, magnetosonic waves), so v1's core loop amplifies noise exponentially, and the sharp column edge (next point) supplies plenty of noise. No choice of time step fixes FTCS — it needs upwinding (Riemann solvers), artificial viscosity, or a different time integrator.

### 3.2 ❌ Initial state — a pressure cliff of 10⁸ with nothing to hold it

**In plain words:** the starting plasma was a solid cylinder of hot gas sitting in near-vacuum, with no magnetic field to hold it — like opening a pressurised gas tank in space.

`simstate.py:125-129` sets density 1 and internal energy 1.5 inside the cylinder and $10^{-6}$ / $10^{-8}$ outside — a jump of **eight orders of magnitude in pressure across one cell**. With the default `axial_current = 0` (`parameters.py:101`) there's **no magnetic field at all**, so nothing confines the column; physically it should just explode outward. Central differences across such a jump produce violent wiggles → negative densities/pressures → clamped by floors → more wiggles. There was also no **equilibrium** to start from: no field profile v1 could make balances a uniform column with a sharp edge.

### 3.3 ❌ `dt_min` clamp forces steps beyond the speed limit

**In plain words:** when things sped up and the CFL rule demanded a tiny step, v1 refused to go below a minimum step — breaking the speed limit from primer lesson 4.

`solvers.py:179` does `np.clip(dt, dt_min=1e-6, dt_max=0.1)`. Once velocities reach 10⁶, the stable step is ~10⁻⁷ but it's clamped *up* to 10⁻⁶ — 10× too large — accelerating the blow-up (in the probe: `dt=1.00e-06` from step 4 on, energy climbing 10¹⁰× per step).

### 3.4 ❌ Not conservative — energy, mass and momentum could not be trusted

**In plain words:** the bookkeeping leaked. Energy was tracked in three separate "accounts" (motion, heat, magnetic) updated by different rules that didn't agree, and some quantities were simply deleted.

- **Internal-energy formulation.** Heat energy, kinetic energy (from momentum) and magnetic energy (from $\mathbf{B}$) were each updated separately; nothing tied the three together, so their sum drifted even when stable. The "total energy" graph could never confirm anything.
- **Momentum deleted** in thin cells: `solvers.py:422-423` `m[vac] = 0.0` destroys momentum (and kinetic energy) wherever density ≤ the floor.
- **Floors not counted:** whenever a floor clipped a cell, mass/energy appeared from nowhere and was never recorded.
- **Edges ignored:** the derivative functions returned 0 on the outermost cells, then boundary code copied neighbours over them — flow through the boundary was never computed consistently.

### 3.5 ❌ The pinch drive was not physics ("Option C")

**In plain words:** instead of passing a current through the plasma, v1 reached in every step and *bent the magnetic field toward a pre-drawn shape*. That's like animating a balloon shrinking instead of letting the air out.

`solvers.py:446`:

$$
\partial_t \mathbf{B} \mathrel{+}= k_{\text{relax}}\,(\mathbf{B}_{\text{target}} - \mathbf{B})
$$

with a hand-tuned rate (`ampere_relax_rate = 1.0`, flagged *PROVISIONAL* in `constants.py:88`). This:
- creates and destroys magnetic energy **from nowhere** (no energy flows in from any power supply);
- fights the plasma's real response;
- has no physical time scale (no circuit, no rise time) — just a tuning knob;
- cuts the target field off at the column ends (`simstate.py:293-294`), implying current flowing sideways through vacuum.

### 3.6 ❌ Divergence cleaning that was itself unstable and dimensionally wrong

**In plain words:** magnetic field lines can never begin or end ("$\nabla\cdot\mathbf{B}=0$"). Numerical errors break this slightly, so codes run a clean-up step. v1's clean-up step had the wrong units and could itself explode.

`solvers.py:336-338`:

```python
cp = ch / dx
psi += dt * (-(ch**2) * divB - (cp**2) * psi)
```

- The damping term $c_p^2\psi$ has units of $[\psi]/\text{time}^2$; a damping *rate* must be $[\psi]/\text{time}$.
- A decay term updated with forward Euler, $\psi \leftarrow \psi(1 - \lambda\Delta t)$, flips sign and grows if $\lambda\Delta t > 2$. Here $\lambda\Delta t \approx 0.2\,c_h/\Delta x$, which exceeds 2 as soon as the cleaning speed exceeds 10 cells per time unit.

### 3.7 ⚠️ Transport coefficients — right idea, wrong use

**In plain words:** the *trends* were right (resistance falls as plasma heats; friction rises), but the way they were put into the equations didn't conserve momentum or energy.

- Resistivity $\eta\propto T^{-3/2}$ (Spitzer) — correct trend — but clipped at an untuned `transport_coeff_max = 10`.
- Viscosity $\nu\propto T^{+5/2}$ applied as $\nu\nabla^2\mathbf{v}$ (not the proper stress tensor; not momentum-conserving when $\nu$ varies), with a self-described "proxy" for the heating, so friction losses and friction heating didn't match.

### 3.8 ⚠️ Unphysical boundary conditions

**In plain words:** at the walls, v1 treated the plasma like a bouncing ball that loses 30 % of its speed each bounce. Fluids don't do that.

- **Fluid "coefficient of restitution"** (`solvers.py:204-233`): momentum reflected at the walls was multiplied by `-e_coeff` (0.7). That destroys kinetic energy without heating anything.
- The wall flipped the normal magnetic field (a conductor) while the drive field was imposed *inside* the domain — two contradictory statements about what the wall is.
- Tracers "bounced" too — but tracers are markers of the flow; they should go wherever the fluid goes.

### 3.9 ⚠️ Sliders and diagnostics that meant nothing

- `temp_ext` and `pressure_ext` (`parameters.py:103-104`) were **never used** (admitted in `solvers.py:360`).
- Gravity up to 100 in units where the sound speed is ~1: any real value crushes everything to the floor almost instantly.
- **"Confinement time"** = heat energy / resistive heating power (`solvers.py:513`) — resistive heating is a *gain*, not a loss, so this isn't a confinement time.
- **"Lawson proxy"** = density × temperature × that number, against an arbitrary threshold of 1.0 (`constants.py:133`, flagged *UNPHYSICAL*).

### 3.10 ❌ Performance — the design could never be interactive

**In plain words:** 23 million cells in pure Python/NumPy is like trying to paint a stadium with a toothbrush — and the window had to wait for every stroke.

| Cost | Where | Why |
|---|---|---|
| 23 M cells × 9 fields × 8 bytes + 3 full coordinate grids | `simstate.py:77` | ~2 GB just to hold the state |
| Dozens of full-grid temporary arrays per step | `np.cross`, `curl`, `laplacian`, `gradient` | each 3-component temporary = 550 MB → **12.7 GB peak** |
| `ampere_bfield_target()` rebuilt every step | `simstate.py:259` | square roots over 23 M cells every step |
| Python loop over 20 000 tracers, one function call each | `solvers.py:469` | ~20 k slow interpreter calls per step |
| Isosurface rebuilt (marching cubes on 23 M cells) after each step | `visualisation.py:198-200` | seconds per rebuild |
| Pressure and temperature of the whole grid recomputed **60 times a second** for the text display | `ui_ux.py:167-168` | 23 M-cell passes at 60 Hz |
| Physics and window in one thread (`app.Timer(interval=0.001)`) | `main.py:114` | a 20 s step freezes the window for 20 s |

Memory arithmetic, for the curious: $240\times240\times400 = 23{,}040{,}000$ cells; one number per cell in float64 is $23.04\text{M}\times8\text{ B} = 184$ MB; a 3-component vector field is 553 MB. v1 held ~12 such numbers per cell plus three coordinate grids → ~2.2 GB, and every operation like `np.cross(J, B)` creates another 553 MB temporary.

### 3.11 ⚠️ UI built inside the 3D scene

Sliders and buttons were drawn as shapes inside the same canvas as the 3D view, with hand-written click detection. Every mouse drag went to *both* the slider and the camera — the bug written at the bottom of `main.py:399`: **"CAMERA MOVES WHILE MOVING SLIDERS"**. The workaround toggled `camera.interactive` *after* the event had already been handled (`main.py:264`).

### 3.12 Minor
- `SimState.update_dt_cfl` defined but never used; the time-step rule counted the cleaning speed twice, halving $\Delta t$ for nothing.
- A 240-unit-wide box with a 60-cell radius column; the isosurface level was relative to the current maximum, so it jumped around.
- A 380 MB `.venv` inside the project folder.

---

## 4. What v1 got right (and v2 kept)

> [!success] Kept ideas
> - **Normalised units** ($\mu_0 = 1$, reference density/pressure) — kept, made explicit.
> - **Split between setup and live parameters**, each with bounds/defaults — kept; they now *generate* the control panel automatically.
> - **Spitzer-like $\eta \propto T^{-3/2}$** — kept as an option, correctly capped and documented.
> - **Tracer particles** — kept, now moved by fast compiled code with a better (2nd-order) integrator.
> - **Divergence cleaning (Dedner)** — kept, in its correct form.
> - **Isosurface + tracers + orbit camera** — kept, plus volume rendering and slices.
> - **Export of graphs** — kept, plus the full data.
> - **Energy accounting as the validation target** — kept and *achieved*.
> - **Gravity along −y** — kept, energy-consistent.

---

## 5. Lessons learned (useful far beyond this project)

1. **Validate on a tiny problem with a known answer before going big.** A 1D shock tube or a moving block would have exposed FTCS in seconds.
2. **Stability, accuracy and conservation are three different properties.** Check all three separately (the toy shows FTCS conserving perfectly while exploding).
3. **Never clamp the time step from below.** If $\Delta t$ wants to be tiny, the physics (or a bug) is telling you something.
4. **No shortcuts around the physics.** "Relax toward a target" terms and restitution coefficients make energy accounting impossible and hide real behaviour.
5. **Count everything you add by hand** (floors, sources) — otherwise you can't tell a physics result from a bookkeeping error.
6. **Measure performance early.** Multiply cells × fields × bytes before choosing a grid size; time one step before building a UI around it.
7. **Never run heavy computation on the UI thread.**
8. **Don't ship controls that do nothing.** Either wire a slider to a real term or remove it.

→ Next: [[03 - V2 Changes and Fixes]]
