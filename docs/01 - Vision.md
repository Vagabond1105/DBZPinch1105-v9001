---
tags: [zpinch, mhd, vision, beginner]
aliases: [Vision, Project Vision, Start Here]
---

# 01 · Vision — an interactive Z-pinch plasma laboratory

> [!abstract] One-sentence version
> A desktop program where you can **watch a magnetically squeezed column of plasma live in 3D**, turn the knobs a real experimenter would turn (electric current, magnetic field, resistance, cooling…), and trust that what you see is **what the laws of physics actually predict** — not an animation that merely looks plausible.

Series: **01 Vision** → [[02 - V1 and Why It Failed]] → [[03 - V2 Changes and Fixes]] → [[04 - V2 Complete Guide]]

---

## 0. Start here — how to read these four notes

These notes are written so that someone with **high-school physics** (force, energy, electric current, magnets) and **a little programming** (you know what a variable, a loop and a function are) can follow everything. Nothing beyond that is assumed; every new idea is explained the first time it appears, and the [[04 - V2 Complete Guide#Glossary|Glossary]] has every term in one place.

| Note | What it is | Read it if… |
|---|---|---|
| **01 Vision** (this one) | the story: what a plasma and a Z-pinch are, why simulate them, what the program is meant to be | always — start here |
| [[02 - V1 and Why It Failed]] | a post-mortem of the first version, with a gentle introduction to *why* simulations break | you want to learn the classic mistakes in simulation code |
| [[03 - V2 Changes and Fixes]] | every fix in v2, each explained in plain words first, then technically | you want to know what "doing it properly" means |
| [[04 - V2 Complete Guide]] | the full manual + textbook: foundations, how to use it, how it works, the code, exercises | you want to use, understand, or modify the program |

**Suggested paths**

- *"I just want to play with it"* → this note §1–2 → [[04 - V2 Complete Guide#Your first session]] → [[04 - V2 Complete Guide#Tutorials — experiments to run]].
- *"I want to understand the physics"* → this note → [[04 - V2 Complete Guide#Part I — Foundations]] → [[04 - V2 Complete Guide#The physics model]].
- *"I want to learn how physics simulations are built"* → this note → [[02 - V1 and Why It Failed]] → [[03 - V2 Changes and Fixes]] → [[04 - V2 Complete Guide#Numerical method]] → [[04 - V2 Complete Guide#A guided tour of the code]].

> [!note] About the maths
> Equations are written in LaTeX and rendered by Obsidian. **Every equation is also explained in words** — if a formula looks scary, read the sentence next to it; that is the part that matters. Symbols like $\nabla$ ("nabla") and $\partial$ ("partial") are introduced gently in [[04 - V2 Complete Guide#0.1 Numbers, vectors and fields]].

---

## 1. The physics story, in plain words

### 1.1 Plasma — the fourth state of matter

Heat ice and it melts into water; heat water and it boils into steam. Heat a gas hot enough (thousands to millions of degrees) and the atoms are shaken so violently that **electrons are knocked off**. What's left is a soup of free, negatively charged electrons and positively charged ions. That soup is a **plasma**.

```
 solid  ──heat──▶  liquid  ──heat──▶  gas  ──lots of heat──▶  plasma
 (ice)            (water)            (steam)                  (e⁻ and ions, free)
```

You've seen plasma: **lightning**, **neon signs**, **the Sun**, the aurora, a welding arc. Most of the visible matter in the universe is plasma.

Because its particles are electrically charged, a plasma behaves very differently from an ordinary gas:

- It **conducts electricity** extremely well (better than copper when hot enough).
- It **responds to magnetic fields** — and a current flowing through it **creates** magnetic fields that push back on it.

That two-way conversation between the fluid and the field is the whole subject of **magnetohydrodynamics (MHD)**: *magneto* (magnetic) + *hydro* (fluid) + *dynamics* (motion).

### 1.2 Currents make magnetic fields that wrap around them

Any electric current — electrons flowing in a wire, or in a plasma — creates a magnetic field that **circles around** it. Point your right thumb along the current; your curled fingers show the direction of the field (the **right-hand rule**). The field gets weaker with distance $r$ from the current:

$$
B = \frac{\mu_0 I}{2\pi r}
$$

*In words:* the field strength $B$ is proportional to the current $I$ and falls off as one over the distance. ($\mu_0$ is just a fixed constant of nature that sets the units.)

```
        ↺ field lines circle the current
     ╭─────────╮
    │  ╭─────╮  │
    │ │   ⊙   │ │      ⊙ = current coming out of the page
    │  ╰─────╯  │
     ╰─────────╯
```

### 1.3 Parallel currents attract — the "pinch effect"

Two wires carrying current in the **same direction attract** each other (this is how the ampere was historically defined). A plasma column carrying a current along its length is like **millions of parallel wires bundled together** — every bit of current attracts every other bit. The whole column therefore **squeezes itself inward**. That is the **pinch effect**, and a column squeezed this way, with the current along the $z$ axis, is a **Z-pinch**.

The same effect, in a more technical description: the current density $\mathbf{J}$ (current per unit area) crossed with the field $\mathbf{B}$ gives a force per unit volume $\mathbf{J}\times\mathbf{B}$ that points toward the axis.

> [!example] A real-world pinch: the crushed lightning rod (1905)
> In 1905 two physicists in Sydney, Pollock and Barraclough, examined a copper lightning-conductor tube at a colliery that had been **crushed flat** by a lightning strike. They showed the culprit was the magnetic pinch force of the enormous lightning current — one of the first recorded observations of the pinch effect.

### 1.4 Balance: the Bennett equilibrium

The plasma also has **pressure** — its hot particles push outward, like the air in a balloon. A Z-pinch can sit still when the **outward plasma pressure exactly balances the inward magnetic squeeze**:

$$
\text{outward push of pressure} \;=\; \text{inward squeeze of } \mathbf{J}\times\mathbf{B}
$$

Willard Bennett worked out the exact shape of such a balanced column in 1934 — the **Bennett equilibrium**. He also found the famous **Bennett relation**: the current needed to hold a column together depends only on *how many particles there are per metre of column* and *how hot they are*:

$$
\frac{\mu_0 I^2}{8\pi} = N\,k_B\,(T_e + T_i)
$$

*In words:* current squared ∝ (particles per metre) × (temperature). Double the temperature at fixed particle number and you need $\sqrt2 \approx 1.41$ times the current to hold the column.

### 1.5 But the balance is unstable

Balanced is not the same as **stable**. A pencil balanced on its tip is in equilibrium, but the tiniest nudge makes it fall. A marble at the bottom of a bowl is in a *stable* equilibrium: nudge it and it rolls back.

A Z-pinch is a pencil on its tip. Two famous ways it falls over:

```
   sausage (m = 0)                 kink (m = 1)
     ║    ║                          ║  ║
     ╲    ╱  ← neck                   ╲  ╲
      ║  ║                             ║  ║
     ╱    ╲  ← bulge                  ╱  ╱
     ║    ║                          ║  ║
     ╲    ╱                           ╲  ╲
```

- **Sausage ($m=0$):** where the column gets slightly thinner, the same current is squeezed into a smaller radius, so the field there is *stronger* ($B \propto 1/r$), so the squeeze is *stronger*, so it gets thinner still… The column pinches off into a string of sausages.
- **Kink ($m=1$):** where the column bends slightly, the field lines bunch together on the inside of the bend and spread apart on the outside. Bunched field lines push harder, so the bend gets *worse*. The column twists into a corkscrew.

The label $m$ counts how many times the pattern repeats as you go once around the column: $m=0$ means it's the same all the way round (a symmetric neck); $m=1$ means one side goes out while the other comes in (a sideways shift).

A **magnetic field along the axis** ($B_z$) acts like a stiff spine: field lines resist being bent or squeezed. Enough of it stops the sausage; a lot more (the **Kruskal–Shafranov** limit) stops the kink. Watching these instabilities grow — and be tamed — is the best intuition-builder in plasma physics, and it's what the program is built to show.

### 1.6 Why anyone cares

- **Fusion energy.** Fusing light nuclei (e.g. deuterium + tritium) releases enormous energy, but only if a plasma is **hot** (~100 million °C), **dense**, and **confined long enough** (the *Lawson criterion*: density × temperature × confinement time must exceed a threshold). A Z-pinch squeezes and heats plasma with nothing but a current, which makes it the simplest confinement idea there is. The 1950s fusion programmes (e.g. Britain's ZETA in 1957–58) were built around pinches — and were defeated largely by the instabilities above. Modern efforts (e.g. *sheared-flow-stabilised* Z-pinches developed at the University of Washington and by Zap Energy) find new ways to suppress them.
- **The most powerful X-ray sources on Earth.** Sandia's **Z machine** drives tens of millions of amperes through a pinch to produce intense X-ray bursts for materials and weapons physics research.
- **Astrophysics.** Current-carrying plasma columns appear in solar flares and in jets from young stars and black holes.

### 1.7 A short timeline

| Year | Event |
|---|---|
| 1905 | Pollock & Barraclough explain a lightning-crushed copper tube by the pinch effect |
| 1934 | Bennett derives the pinch equilibrium and the Bennett relation |
| 1950s | Pinch devices at the heart of early fusion research; kink and sausage instabilities identified; Kruskal and Shafranov derive the kink-stability limit |
| 1957–58 | ZETA (UK) reports neutrons; later shown not to be from thermonuclear fusion — instabilities again |
| 1990s– | Sandia's Z machine: multi-mega-ampere pinches as X-ray sources |
| 2000s– | Sheared-flow-stabilised Z-pinch research (FuZE, Zap Energy) |

---

## 2. What a "simulation" is

A **simulation** is a virtual experiment: instead of building a machine, you write the laws of physics as rules a computer can follow, give it a starting state, and let it play the rules forward in time.

### 2.1 The three ingredients

1. **A description of the state.** We chop the box of plasma into small cubes (**cells**) — like pixels, but 3D (**voxels**). Each cell stores a few numbers: how much plasma is in it (density), how fast it moves (velocity), how hot it is (pressure/temperature), and the magnetic field.
2. **Update rules.** The laws of physics say how each of those numbers changes depending on its neighbours: plasma flows from cell to cell, pressure pushes, magnetic forces squeeze. Turned into arithmetic, they become "new value = old value + (small time step) × (rate of change)".
3. **A clock.** Repeat the update thousands of times with a small **time step** $\Delta t$. Each repeat is a **step**.

```
 state at t ──[apply the laws for Δt]──▶ state at t+Δt ──▶ state at t+2Δt ──▶ …
```

### 2.2 Why it's an approximation — and why that's fine if you're careful

Real plasma is continuous; our cells are finite. So a simulation is always an **approximation**, and three things can go wrong:

| Problem | What it means | Analogy |
|---|---|---|
| **Inaccuracy** | the answer is a bit off because cells/steps are too coarse | a low-resolution photo |
| **Instability** | small errors grow every step until the numbers explode | microphone feedback howl |
| **Non-conservation** | the rules leak or create mass/energy that physics says can't appear | a bank that loses pennies on every transfer |

A good simulation **controls all three** and — crucially — **checks itself**: it measures that mass and energy add up, and it is tested against problems whose exact answers are known. Version 1 of this program fell into all three traps ([[02 - V1 and Why It Failed]]); version 2 was built to avoid them and to prove it ([[03 - V2 Changes and Fixes]]).

---

## 3. The program, as it was imagined

The original design (v1, in `v1/`) set out these pillars. They are still the goals for v2.

### 3.1 A real 3D fluid simulation of the plasma
- The plasma is a **fluid on a 3D grid**: density, momentum, energy and magnetic field in every cell.
- It evolves under **magnetohydrodynamics** — Newton's laws for a conducting fluid coupled to Maxwell's laws of electromagnetism.
- It includes **resistivity** (electrical resistance turns current into heat — hotter plasma conducts better) and **viscosity** (internal friction).
- An **axial current** drives the pinch.
- Optional **gravity** for exploring how a heavy plasma sags against a magnetic field.

### 3.2 Tracer particles
Thousands of massless **tracer particles** — think of them as specks of glitter in water — carried along with the flow, so you can *see* swirls, compression and the corkscrew of a kink that a density cloud alone hides.

### 3.3 Live, hands-on control

| Kind | When it applies | Examples |
|---|---|---|
| **Setup parameters** | fixed once a run starts (they define the grid and the starting state) | resolution, column radius & length, axial field, particle count |
| **Live parameters** | adjustable *while it runs* | current, resistivity, viscosity, cooling, gravity |

Start / pause / resume, restart, restart with defaults.

### 3.4 3D visualisation
A rendered plasma you can orbit and zoom, with tracers on top.

### 3.5 Live diagnostics and export
On-screen numbers and graphs — energies, core temperature and density, instability amplitudes — and an **export** of all the data and graphs.

### 3.6 A physics-validation mindset
The v1 comments repeatedly mention a **"32³ physics-validation grid"**: the intention was always that the simulation be *checked*, especially that **total energy is conserved** once you account for what flows in and out. That intention is the heart of v2.

---

## 4. The guiding principles (made explicit for v2)

> [!important] The three rules
> 1. **Physics first.** Every effect on screen must come from a term in a real law of physics. No "nudge the field toward a target" shortcuts, no sliders that do nothing.
> 2. **Prove it.** Mass and energy are checked *every step* and shown live; the solver is tested against problems with exact answers.
> 3. **Interactive means interactive.** The window never freezes; the physics runs at full speed on its own; on a laptop you see an instability develop within seconds.

### 4.1 Which laws, concretely

| Law | Plain words | How it shows up in the program |
|---|---|---|
| Conservation of mass | plasma is never created or destroyed, only moved | mass is exact to ~16 digits |
| Newton's 2nd law + magnetic force | each bit of plasma accelerates according to the pressure, magnetic, friction and gravity forces on it | the momentum equation |
| Conservation of energy | energy changes form (motion ↔ heat ↔ magnetic) but the total only changes by what crosses the walls or radiates away | measured live, error ~10⁻¹⁶ |
| Faraday's + Ohm's laws | moving plasma drags magnetic field with it; resistance lets field slip and turns current into heat | the induction equation |
| Ampère's law | current *is* the "swirl" of the magnetic field; the drive current enters through the walls as in a real machine | the drive circuit + a measured current |
| No magnetic monopoles | magnetic field lines never start or end | $\nabla\cdot\mathbf{B}=0$, actively cleaned and monitored |
| Poynting's theorem | energy delivered by the circuit flows in as electromagnetic energy | measured as "circuit energy in" |
| 2nd law of thermodynamics | friction and resistance only ever turn ordered energy into heat | heating appears automatically, never by hand |
| Bremsstrahlung | hot dense plasma glows (in X-rays) and cools | optional radiative cooling |

### 4.2 What it deliberately does *not* try to be
- Not a model of individual particles or separate electron/ion temperatures (that's "kinetic" or "two-fluid" physics). Single-fluid MHD is the right level for pinch equilibria and instabilities.
- Not a fusion-yield predictor. It reports things it can actually measure (radius, temperature, Bennett ratio, instability growth) instead of decorative "fusion scores".
- Not tied to one machine size: it runs in **normalised units** (see [[04 - V2 Complete Guide#Units]]), so results scale to any size.

---

## 5. What you'll be able to do after reading all four notes

- Explain, in your own words, why a current squeezes a plasma, why the column kinks, and how an axial field stops it.
- Run experiments: compress a column, stabilise it, heat it resistively, make it radiate, and read the graphs.
- Explain why naive simulation code explodes, and what finite volumes, Riemann solvers, slope limiters and time-step limits are for.
- Read and modify the code: add a parameter, a diagnostic, or a new plot.

## 6. Success criteria

| Criterion | Target | v2 status |
|---|---|---|
| Runs, no crashes on defaults | ✓ | ✓ |
| Window never blocks on physics | ✓ | ✓ (physics in a separate process) |
| Default run shows an instability quickly on a laptop | < 1 min | ✓ **~5–8 s** on the default *Very fast* grid; ~15–25 s on *Fast* |
| Mass conserved | exact | ~10⁻¹⁶ relative |
| Energy budget closed | exact | ~10⁻¹⁶ relative |
| Solver matches exact solutions | ✓ | shock tube, nonlinear Alfvén wave, diffusion decay — all directions |
| Every slider does something physical | ✓ | ✓ |

→ Next: [[02 - V1 and Why It Failed]]
