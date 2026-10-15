---
tags: [zpinch, mhd, v2, changelog, beginner]
aliases: [V2 Changes, V2 Fixes]
---

# 03 · What changed in v2, and how each v1 problem was fixed

Series: [[01 - Vision]] → [[02 - V1 and Why It Failed]] → **03 V2 Changes and Fixes** → [[04 - V2 Complete Guide]]

> [!summary] TL;DR
> v2 is a **rewrite**, not a patch. The physics is the same family (resistive MHD + tracers), but every layer was replaced:
> - **Numerics:** the exploding FTCS rule → a **finite-volume Godunov scheme** (sloped cells + **HLLD** Riemann solver + two-stage Runge–Kutta), proper **divergence cleaning**, and conservative resistance/friction.
> - **Physics:** "bend the field toward a target" → a **current driven through the walls** by a circuit, starting from an exact **Bennett equilibrium**; energy enters as measured electromagnetic (Poynting) flow.
> - **Proof:** mass and the full energy budget are conserved to **~10⁻¹⁶** and shown live; **25 automated tests** against exact solutions.
> - **Speed:** 19.9 s/step on 23 M cells → **compiled parallel code** on 49 k–1.3 M cells: **~10 ms/step** on the default grid, **~65–75 steps/s in the window**; physics runs in a **separate process** so the window never freezes.
> - **UI:** sliders drawn inside the 3D scene → a **native control panel** generated automatically from the parameter definitions; GPU volume rendering; live plots.

> [!tip] How to read this note
> Every fix has three layers: **In plain words** (an analogy), **Technically** (what the code does), and **Evidence** (how we know it works). Skip the technical layer on a first read if you like.

---

## 1. Side-by-side

| Aspect | v1 | v2 |
|---|---|---|
| How cells exchange plasma | central differences (listen to both neighbours equally) | **finite volume**: explicit flows through each cell face, decided by a Riemann solver |
| Shape inside a cell | flat | **sloped** (piecewise-linear) with a **limiter** that never invents new peaks |
| Time stepping | forward Euler | two-stage Runge–Kutta ("predict, then correct") |
| Stability | **always unstable** | stable; tested on shocks and nonlinear waves |
| Energy variable | heat only (separate accounts) | **total** energy (one account) |
| Mass/energy bookkeeping | not conserved, not measured | exact to ~16 digits, **shown live** |
| Magnetic clean-up ($\nabla\cdot\mathbf{B}$) | wrong units, could explode | GLM cleaning built into every face flux, exact decay |
| Current drive | field pulled toward a target shape | wall field set by a circuit current $I(t)$; Ampère's law does the rest |
| Starting state | uniform cylinder, 10⁸ pressure jump, no field | exact **Bennett equilibrium** + small controlled nudge |
| Resistance | $\eta_0T^{-1.5}$, clipped | uniform or Spitzer, conservative, heats automatically |
| Viscosity (friction) | $\nu_0T^{2.5}\nabla^2\mathbf{v}$ + heating guess | full friction law, conservative, heats automatically |
| Radiation | – | optional bremsstrahlung cooling, counted |
| Gravity | force only, energy inconsistent | force + matching energy term; $E + \rho\Phi$ conserved exactly |
| Walls | "bouncy" damped walls + leaky ends | frictionless walls that carry the drive field; periodic (wrap-around) ends |
| Floors | silent | relative to the background, **counted** |
| Tracers | Python loop, crude stepping | compiled, parallel, 2nd-order, follow the flow |
| Grid | 240×240×400 = 23 M cells | presets from 32×32×48 (49 k) to 96×96×144 (1.3 M) |
| Speed | 19.9 s/step | 9.6 ms/step (default grid, headless) |
| Memory | 12.7 GB | 0.17–1.2 GB |
| Threads | one, shared with the window | physics in its own **process**, multi-threaded inside |
| Controls | shapes drawn in the 3D scene | real Qt widgets generated from parameter metadata |
| Rendering | CPU isosurface | GPU ray-cast volume (glow / translucent / MIP / iso) + slices |
| Dead sliders | `temp_ext`, `pressure_ext` | none |
| Diagnostics | energies, "confinement", "Lawson proxy" | energies + budget, mass error, $\nabla\cdot\mathbf{B}$, instability amplitudes, Bennett ratio, measured current, radius, temperatures, densities |
| Tests | none | 25 |

---

## 2. Fix-by-fix (v1 issue → v2 solution)

### 2.1 Unstable FTCS → Godunov finite-volume scheme
*v1 issue: [[02 - V1 and Why It Failed#3.1 ❌ The time-stepping scheme is unconditionally unstable (fatal)]]*

**In plain words.** Treat every cell like a **bank account** holding mass, momentum, energy and magnetic field. Plasma can only change accounts by **transfers through the shared walls (faces)** between neighbouring cells. Whatever leaves one cell enters the next, so the grand total can't drift — like money moving between accounts at the same bank. The hard part is deciding each transfer, and that's done by asking: "if I removed the wall between these two cells, what would flow through it?" That question is the **Riemann problem** — the physics of a *dam break*: two different states suddenly in contact, sending waves left and right. Answering it at every face makes the scheme **upwind** automatically (it listens to the side the waves come from), which is exactly what the toy in note 02's primer showed you need.

**Technically.** Cells store **averages** of the conserved quantities $U = (\rho, \rho\mathbf{v}, E, \mathbf{B}, \psi)$:

$$
\frac{dU_{ijk}}{dt} = -\frac{F_{i+\frac12}-F_{i-\frac12}}{\Delta x}-\frac{G_{j+\frac12}-G_{j-\frac12}}{\Delta y}-\frac{H_{k+\frac12}-H_{k-\frac12}}{\Delta z}+S_{ijk}
$$

*In words:* the change in a cell = (what flows in through its faces − what flows out) / cell size + any sources (like gravity). $F, G, H$ are the face flows ("fluxes") in $x, y, z$, computed by the **HLLD** Riemann solver, which resolves all the MHD wave families (fast, Alfvén, slow, contact). **Second order** accuracy comes from giving each cell a **limited slope** ("PLM") and from two-stage **SSP-RK2** time stepping (predict a step, re-evaluate, average).

Why the limiter matters — the toy `v2/examples/toy_muscl.py` (real output, moving block, one full lap):

```
1st-order upwind             max=0.8418  min=+0.0000  error=0.1125
2nd order, NO limiter        max=1.1662  min=-0.1663  error=0.0648
2nd order, van Leer limiter  max=0.9984  min=+0.0000  error=0.0462
```

Without a limiter, the sloped cells overshoot to 1.17 and dip to **−0.17** — a negative density, which is impossible. The limiter flattens slopes near peaks and jumps, keeping the sharpness of second order (error 0.046) without inventing wiggles. v2 uses this van Leer limiter on all variables.

**Evidence.** The Sod shock tube matches the exact solution (density error 2.3×10⁻³ at 256 cells) along x, y and z; the circularly polarised Alfvén wave (an exact nonlinear MHD solution) converges at ~2nd order. → `tests/test_physics.py`.

### 2.2 Pressure cliff, no equilibrium → Bennett equilibrium
*v1 issue: [[02 - V1 and Why It Failed#3.2 ❌ Initial state — a pressure cliff of 10⁸ with nothing to hold it]]*

**In plain words.** Instead of a gas tank opened in space, v2 starts with a column that is **already perfectly balanced** — the smooth Bennett profile, dense and hot in the middle, thinning gradually outward, with exactly the magnetic squeeze needed to hold it. Then it gives it a *tiny, controlled* nudge (2 %) and lets the instability grow from that, instead of from numerical garbage.

**Technically.**

$$
\rho = \rho_{bg} + \frac{\rho_0}{(1+r^2/a^2)^2},\quad p = T_0\rho,\quad B_\theta = \frac{I_B}{2\pi}\frac{r}{r^2+a^2},\quad I_B^2 = 8\pi^2a^2p_0
$$

satisfies $dp/dr = -J_zB_\theta$ ("pressure gradient = magnetic squeeze") exactly; derivation in [[04 - V2 Complete Guide#Bennett equilibrium (derivation)]].

**Evidence.** Without a nudge the column stays put: spurious velocities stay below 3 % of the Alfvén speed and **shrink as the grid is refined** (they are discretisation error, not physics) — tested.

### 2.3 `dt_min` clamp → an honest speed limit
**In plain words.** The time step is always chosen so no wave crosses more than ~0.3 of a cell per step — never forced bigger. If the step gets small, it's because the physics got fast (e.g. strong field in near-vacuum), and the status bar tells you.

**Technically.** $\Delta t = 0.3\,\Delta x / \max(|v| + c_f)$, where $c_f$ is the fastest wave speed (the fast magnetosonic speed), and also below the explicit diffusion limit.

### 2.4 Leaky bookkeeping → total-energy flux form + a full budget
*v1 issue: [[02 - V1 and Why It Failed#3.4 ❌ Not conservative — energy, mass and momentum could not be trusted]]*

**In plain words.** One energy account instead of three, and an auditor: the program records **everything** that crosses the walls, everything radiated away, and everything the floors add, and checks every step that

> energy now − energy at start = energy delivered by the circuit − energy radiated + energy added by floors

**Technically.** Evolve the total $E = \frac{p}{\gamma-1} + \frac12\rho v^2 + \frac12 B^2$ in flux form; interior fluxes cancel in the sum ("telescope"), so only boundary fluxes, sources and floors can change totals, and each is tallied:

$$
E_\text{box}(t) - E_\text{box}(0) = W_\text{circuit} - E_\text{rad} + E_\text{floors}
$$

**Evidence.** Relative error ~10⁻¹⁶ (the last digit a computer can store) with every effect switched on — tested to < 10⁻¹². Mass likewise. No more deleting momentum.

### 2.5 "Option C" nudging → a real current drive
*v1 issue: [[02 - V1 and Why It Failed#3.5 ❌ The pinch drive was not physics ("Option C")]]*

**In plain words.** In a real pinch, a capacitor bank pushes current through the plasma and back through an outer conductor. v2 does the equivalent: the walls of the box carry the magnetic field that the circuit current would produce. Physics (Ampère's law) then forces that current to flow through the plasma. Turning up the current raises the magnetic pressure at the walls; a compression wave travels inward and squeezes the column — the energy for it flows in through the walls and is measured.

**Technically.** Wall ghost cells hold $B_\theta = I(t)/(2\pi r)$ (Bennett-shaped so $t=0$ is exact). The circuit responds like a resistor–inductor (RL) circuit with an adjustable rise time:

$$
I(t) = I_\text{set} + (I_0 - I_\text{set})\,e^{-(t-t_0)/\tau}
$$

The current is also **measured independently** by Ampère's law ($\oint\mathbf{B}\cdot d\boldsymbol\ell$ around the box) and shown next to the circuit value.

### 2.6 Broken Dedner cleaning → GLM inside the Riemann solver
*v1 issue: [[02 - V1 and Why It Failed#3.6 ❌ Divergence cleaning that was itself unstable and dimensionally wrong]]*

**In plain words.** Tiny numerical errors make magnetic field lines appear to start or end. v2 adds a "cleaning crew" variable $\psi$ that **carries those errors away as a wave** and **lets them fade out**, instead of letting them pile up. The fade is computed exactly, so it can never overshoot.

**Technically.** At every face the $(B_n, \psi)$ pair is solved exactly first:

$$
B_n^* = \tfrac12(B_n^L+B_n^R) - \tfrac{1}{2c_h}(\psi^R-\psi^L),\qquad
\psi^* = \tfrac12(\psi^L+\psi^R) - \tfrac{c_h}{2}(B_n^R-B_n^L)
$$

then the decay $\psi \leftarrow \psi\,e^{-0.2\,c_h\Delta t/\Delta x}$. $c_h$ = the fastest wave speed, so cleaning never slows the time step.

**Evidence.** The relative divergence error is shown live; typically 10⁻³–10⁻², bounded, tested < 0.1 under a violent current ramp.

### 2.7 Resistance and friction → conservative face fluxes (and now operator-split)
*v1 issue: [[02 - V1 and Why It Failed#3.7 ⚠️ Transport coefficients — right idea, wrong use]]*

**In plain words.** Resistance and viscosity are computed as *transfers between cells* too, so they can't leak. Magnetic and motion energy they remove stays in the energy account and shows up as **heat** — exactly what resistance (Ohmic heating) and friction do in reality. No "heating formula" is written by hand.

**Technically.** Resistive flux of $B_i$ through a face with normal $d$: $\epsilon_{idk}\eta J_k$; energy flux $\eta(\mathbf{J}\times\mathbf{B})_d$. Viscous stress $\tau = \rho\nu(\nabla\mathbf{v} + \nabla\mathbf{v}^T - \frac23\nabla\cdot\mathbf{v}\,\mathbf{I})$; momentum flux $-\tau$, energy flux $-\tau\cdot\mathbf{v}$. Optional Spitzer scaling $\eta \propto T^{-3/2}$ (capped at 10×).

Since the speed update (§2.10) these terms are applied in a separate pass (**operator splitting**) once every few steps with the accumulated time — they are slow processes, and doing them in both RK stages every step was costing as much as the whole wave solver.

**Evidence.** A sine-shaped field or shear flow decays at exactly $e^{-Dk^2t}$ (within 0.2 %) for every component and direction, with total energy constant to 10⁻¹³.

### 2.8 Walls
**In plain words.** Side walls are frictionless and impermeable (plasma slides along but not through) and carry the drive field. The top and bottom wrap around (what leaves the top re-enters at the bottom) — so the box represents a slice of a very long column, the standard way pinch instabilities are studied. No "bounciness" coefficient.

**Technically.** x/y: mirror density/pressure, reverse normal velocity, set $B_x, B_y$ to the drive field; z: periodic. Tracers follow the interpolated flow (2nd-order Runge–Kutta).

### 2.9 Every control is physical; every diagnostic is measurable
- Removed: `temp_ext`, `pressure_ext`, "confinement time", "Lawson proxy".
- New live controls: current **and its rise time**, Spitzer toggle, radiative cooling, Riemann-solver choice; gravity with a sensible range.
- New setup controls: background density, **axial guide field $B_z$**, perturbation type/amplitude, random seed, *Very fast* resolution.
- New diagnostics: Bennett ratio, Ampère-measured current, $m=0$ / $m=1$ amplitudes (so you can read off growth rates), radius, core/peak temperature and density, energy-budget error, mass error, $\nabla\cdot\mathbf{B}$.

### 2.10 Performance (two rounds)
*v1 issue: [[02 - V1 and Why It Failed#3.10 ❌ Performance — the design could never be interactive]]*

**In plain words.** Four ideas: (1) compute only what you need, at a sensible resolution; (2) translate the heavy loops into machine code and use several CPU cores; (3) give the physics its own process so the window and the physics never wait for each other; (4) don't do slow physics as often as fast physics.

| Change | Effect |
|---|---|
| Grid presets sized for a laptop (32–96 cells across) | 17–470× fewer cells than v1 |
| Heavy loops compiled with **numba** (`@njit(parallel=True)`): Python → machine code, multi-core, cached on disk | the core speed-up |
| Fused kernels; only the face gradients actually needed | less memory traffic |
| Physics in a **separate process** | no GIL fight: window speed went 5.5 → 16.7 steps/s (first round) |
| **Diffusion operator-split and applied every ≤ 8 steps** (round 2) | every preset 1.3–1.6× faster |
| **Dynamic work chunks** (round 2) | removes 3× slow-downs when a core is busy (hybrid P/E-core CPUs) |
| **8 physics threads** in the GUI by default (measured best on a 12-thread laptop; 12 was 2.5× slower because of competition with the window) + a live *Physics CPU threads* control | |
| New default **Very fast (32×32×48)** grid (round 2) | ~5× more simulated time per second than *Fast*; kink visible in ~5–8 s |
| Status bar shows **t/s** (simulated time per real second) | you can see the speed |
| GPU ray-casting for rendering | rendering is ~free compared with physics |

Measured (headless, 12 threads): Very fast **9.6 ms/step**, Fast 30 ms, Medium 78 ms, High 157 ms, Very high 242 ms. In the window (8 threads): Very fast ~65–75 steps/s, Fast ~23 steps/s. Full table: [[04 - V2 Complete Guide#Performance and tuning]].

### 2.11 UI
- A native Qt panel, **built automatically** from the parameter definitions (label, range, log scale, tooltip explaining the physics). Adding a parameter = one line.
- Slider + typed number for every value; log-scale sliders for coefficients spanning decades.
- The 3D view is its own widget → "camera moves while dragging sliders" is gone by construction.
- Setup changes highlight the Reset button; errors stop the run with a helpful dialog.
- Live plot dock refreshed every second.

### 2.12 Engineering
- Own virtual environment, pinned `requirements.txt`, `.gitignore`.
- `run.sh` / `test.sh` clear `PYTHONPATH` so unrelated packages (ROS on this machine) can't interfere; `main.py` relaunches itself with `v2/.venv` if started by the wrong Python (e.g. VS Code pointing at v1's).
- Headless command-line mode for batch runs.
- `examples/` with the two toy scripts used in these notes.
- 25 tests, ~30 seconds.

---

## 3. How we know it's right (the verification philosophy)

1. **Test against exact answers.** Shock tube, nonlinear Alfvén wave, diffusion decay — problems with known solutions, run along every axis so a bug in one direction can't hide.
2. **Test conservation as an identity**, not "roughly": the budget must close to round-off with every effect switched on.
3. **Test convergence**: results must get *better* as the grid gets finer (equilibrium flows shrink; wave errors fall ~4× per doubling).
4. **Test the physics we expect**: the kink must grow; its growth rate must not depend on resolution (measured 0.84 and 0.85 per Alfvén time at two resolutions, 0.84 on the *Very fast* grid).
5. **Look at it**: every render mode was checked by screenshot.

---

## 4. Bugs found and fixed *during* the v2 build

An honest log (all caught by the tests or diagnostics above):

| Bug | Caught by | Fix |
|---|---|---|
| Sign of two face current components reversed | derivation review / diffusion test | corrected formulas |
| Floor energy over-counted ×2 in RK stage 2 | energy-budget error jumped to 10⁻³ | weighted by ½ (the stage's weight in the final average) |
| Potential energy of mass crossing a wall not counted | budget test with gravity: 2.7×10⁻⁵ | added $\Phi_\text{wall}\times$ wall mass flow |
| Time step collapse at 2.5× current (box corners emptied, Alfvén speed 14) | stress test | floors relative to the background ($\rho \ge 0.1\rho_{bg}$, $T \ge 0.02T_0$), counted |
| GUI ran 4× slower than headless | timing | physics moved to its own process |
| 12 threads slower than 8 in the GUI; 3× timing spikes | timing (round 2) | 8 threads default + dynamic chunks |
| Diffusion cost as much as the wave solver | profiling (round 2) | operator splitting, applied every ≤ 8 steps |
| Glow rendering showed a blue haze | screenshot | colour map fades to black at the low end |
| Slice view drew misplaced strips | screenshot | slices drawn as positioned images |
| Default resistivity diffused the column too fast | experiments | defaults lowered to $3\times10^{-4}$ |
| ROS plugins crashed the tests | running the suite | `test.sh` disables plugin autoload |
| Running from VS Code used v1's Python | user report | `main.py` relaunches with `v2/.venv` |

→ Next: [[04 - V2 Complete Guide]]
