---
tags: [zpinch, mhd, v3, overview, machine-learning, technical]
aliases: [V3 Technical Overview, V3 Overview, How v3 works]
---

# 06 · Z-Pinch MHD v3: technical overview

Series: [[01 - Vision]] → [[02 - V1 and Why It Failed]] → [[03 - V2 Changes and Fixes]] → [[04 - V2 Complete Guide]] → [[05 - V3 Plan]] (with [[05.1 - V3 Phase 1 Results|05.1]], [[05.2 - V3 Phase 3 Machine Learning|05.2]], [[05.3 - V3 Phase 4 Write-up Library|05.3]], [[05.4 - V3 Phase 5 Report Panel|05.4]]) → **06 V3 Technical Overview**

> [!abstract] v3 in one paragraph
> v2 is a 3D magnetohydrodynamics (MHD) simulator of a Z-pinch: it shows a plasma column carrying a current, and how it bends, necks, sags or collapses. **v3 makes the program say what happened, why, and what to try next.** A run is turned into 65 physical numbers. Transparent physics rules label it with one of 8 outcomes and build a timeline. The energy bookkeeping and the textbook stability criteria explain it. A curated library supplies a hand-written explanation with the run's own numbers. Two machine-learning models, trained on **2902 overnight simulations**, cross-check the label (**99.3 %** agreement) and **forecast the outcome before the run starts** (**94.3 %** right on runs they never saw, against 67.6 % for the best one-line physics rule). Everything ends up in a report panel in the GUI and a standalone HTML report.

> [!info] How to read this note
> - **Only want the result?** Read §1, look at the tables in §10, and skim §11 (limits).
> - **Want to understand every part?** Read it top to bottom. Each section starts from zero. The physics background (fluids, magnetic fields, MHD, what "kink" and "sausage" mean) is in [[04 - V2 Complete Guide]] Part I. This note doesn't repeat it, but each physics idea gets a one-line reminder where it's used.
> - **Want to check a number?** §12 has the commands that reproduce every one of them.
>
> v3 is built on top of v2; the folder is still `v2/`. File paths below are relative to `v2/` unless they start with `docs/`.

## Contents

1. [[#1. What v3 adds, and why]]
2. [[#2. The pipeline at a glance]]
3. [[#3. The data: one overnight sweep]]
4. [[#4. Features: a run as 65 numbers]]
5. [[#5. The rules: labelling a run with physics]]
6. [[#6. Explaining a run: energy and stability criteria]]
7. [[#7. Machine learning, from zero]]
8. [[#8. The curated write-up library]]
9. [[#9. The report, the GUI and the textbook runs]]
10. [[#10. Measured performance, in one place]]
11. [[#11. Honest limits]]
12. [[#12. Reproducing everything]]
13. [[#13. File map]]
14. [[#14. Glossary of the new words]]
15. [[#15. The demo]]

---

## 1. What v3 adds, and why

A simulator on its own shows you pictures and curves. You still have to know enough plasma physics to read them: is that bend a kink? Did it stop growing or tear the column apart? Why did it happen here and not with a stronger axial field? v3 closes that gap, for a student first and with the full data for a researcher.

When you press **Finish & analyse** (or the run reaches t = 3, where it now pauses by itself), the report answers four questions:

| Question | Answered by | Section |
|---|---|---|
| *What happened?* | an **outcome class** (one of 8) and a **timeline** of phases | §5 |
| *Why?* | the **energy bookkeeping** (which store paid for it) and the **stability criteria** (Kruskal–Shafranov, Kadomtsev, Lundquist, cooling) | §6 |
| *What should I try next?* | a hand-written **library entry**, chosen for this run's regime and filled with its numbers | §8 |
| *How sure is that?* | a **confidence** flag from the rules, a learned **run classifier** as a cross-check, and a **pre-run forecast** | §5, §7 |

### The decisions that shaped it

These were fixed in the plan ([[05 - V3 Plan]] §0) before any code was written:

| Decision | Why |
|---|---|
| **Physics rules give the labels; ML only learns from them and checks them.** | There is no "ground truth" for a simulated outcome except physical definitions. Rules are transparent: every threshold has a reason and a run that justifies it. |
| **No free text generation.** Every explanation is a fixed, hand-checked sentence; only the numbers change. | A text generator could invent physics. A library can't, and every claim in it can be checked against the data. |
| **Two audiences in one report.** Plain language first, full data underneath. | It's a learning tool for students and a technical demo for researchers. |
| **One overnight sweep of compute.** | Big enough to train both models at the GUI's default grid, small enough to run on one laptop. |
| **Honesty is a feature.** Low confidence, borderline numbers, unreviewed text and settings outside the training data are all shown, not hidden. | A model that is confidently wrong is worse than no model. |

---

## 2. The pipeline at a glance

```
                       ┌──────────────── once, offline ────────────────┐
  tools/sweep.py  ──▶  2902 runs  ──▶  tools/analyse.py  ──▶  labels.csv  ──▶  tools/train.py  ──▶  models/
  (overnight)          (dataset/)       (rules on every run)  (65 features     (2 models,          (+ model card)
                                                                + label)         tested)
                                                    └──▶  tools/library.py stats/check  ──▶  library/stats.json,
                                                                                               examples.json
                       └───────────────────────────────────────────────┘

  every run, in the GUI or headless:

  simulation history ──▶ features (65 numbers) ──┬──▶ rules ──▶ label, timeline, confidence ──┐
                                                 └──▶ model (a) ──▶ cross-check ──────────────┤
  settings before Start ──▶ model (b) ──▶ forecast ───────────────────────────────────────────┤
  energy budget + criteria ──▶ causes ────────────────────────────────────────────────────────┤
  label + features ──▶ library entry (most specific box) ──▶ filled-in text ──────────────────┤
                                                                                              ▼
                                         report: write-up · 3 figures · data appendix  (panel / HTML / zip)
```

**The key idea:** the rules sit in the middle. They label the training data, they label every new run, and their output feeds the explanation. The models are trained to reproduce the rules' labels, so they never contradict physics by design. They add *probabilities*, a *second opinion*, and a forecast that needs no simulation.

| Stage | Code | Section |
|---|---|---|
| Simulation (v2) | `zpinch/pinch.py`, `solver.py`, `kernels.py` | [[04 - V2 Complete Guide]] Part III |
| Sweep | `tools/sweep.py` | §3 |
| Features | `zpinch/analysis/features.py` | §4 |
| Rules | `zpinch/analysis/rules.py` | §5 |
| Causes, criteria, text report | `zpinch/analysis/explain.py` | §6 |
| Models | `zpinch/analysis/model.py`, `tools/train.py` | §7 |
| Library | `zpinch/analysis/writeup.py`, `zpinch/analysis/library/`, `tools/library.py` | §8 |
| Report, GUI | `zpinch/analysis/report.py`, `zpinch/gui/app.py`, `zpinch/gui/worker.py` | §9 |

---

## 3. The data: one overnight sweep

### Why simulate thousands of runs?

Two reasons. First, the rules' thresholds have to be **checked** against many runs, not guessed: "a kink counts as grown at 0.10 radii" is only believable if quiet runs never reach it and unstable runs always do. Second, a model can only **learn** the link between settings and outcome from many examples of it.

### What was varied

Each run starts from the GUI defaults and changes **8 parameters** plus the random seed of the starting perturbation. The ranges (`tools/sweep.py`, `_broad`):

| Parameter | Range | How it's drawn | Why |
|---|---|---|---|
| drive current I / I_Bennett | 0.4 – 2.8 | uniform; exactly 1.0 in 30 % of runs | I = 1 is the equilibrium current, the most common GUI case |
| current rise time | 0.05 – 1.0 | log-uniform | spans "sudden" to "gentle" drive |
| axial field B_z / B_θ(a) | 0 – 1.5 | uniform; exactly 0 in 30 % | B_z = 0 is the pure Z-pinch; 1.5 is the slider maximum |
| resistivity η | 1e-4 – 1e-2 | log-uniform | from nearly ideal to visibly resistive within t = 3 |
| viscosity ν | 1e-4 – 1e-2 | log-uniform | same span |
| cooling C | 0.01 – 2 | log-uniform; exactly 0 in 50 % | radiation absent half the time |
| gravity g | 0.05 – 2 | uniform; exactly 0 in 60 % | gravity absent most of the time |
| column length L | 1 – 3 | uniform | sets how many helix wavelengths fit (§4) |

*Log-uniform* means every factor of 10 gets the same share of runs. That's right for η and ν, where 1e-4 and 1e-3 are as different as 1e-3 and 1e-2.

Everything else is fixed: grid 32 × 32 × 48 cells (*Very fast*, the GUI default; the grid stretches with the column length), pinch radius a = 0.12, background density 0.05, perturbation "random + m = 0 + m = 1" at 2 %, HLLD solver, no Spitzer resistivity. **The models know nothing about other values of these**, and the GUI says so when you change one (§7.6).

### Oversampling the rare outcomes (strata)

A purely random sample would contain very few radiative collapses or stable columns, too few to learn or test. So 45 % of the runs were drawn from **strata**: boxes where a rare outcome should occur. Each overrides a few of the random draws above and leaves the rest random.

| Stratum | Share | What it forces | Physics reason |
|---|---|---|---|
| broad | 55 % | nothing | a fair, uniform sample of the whole box |
| radiative | 10 % | C 0.3–2, I 1–2.5 | dense compressed plasma radiates fastest (P ∝ ρ²√T) |
| sausage | 10 % | B_z 0–0.3, I 1.3–2.8, fast rise, short column | a weak B_z doesn't stiffen against necking (Kadomtsev) |
| gravity | 10 % | g 0.3–2, B_z 0.8–1.5, short column | a kink-stable column makes the sag visible |
| stable | 5 % | B_z 1–1.5, short column | Kruskal–Shafranov needs a large q |
| resistive | 5 % | η 3e-3 – 1e-2 | the diffusion time a²/η is ~1.4–5, inside the run |
| compression | 5 % | I 1.5–2.8, fast rise, B_z 0.5–1.5 | a strong, fast drive squeezes the column |

The stratum is saved with each run. So a model can also be scored on the **broad** runs alone, a fair sample with no oversampling (§10).

### How the sweep ran

- **Time cap:** every run stops at t = 3, about 18 Alfvén times. (The Alfvén time is how long a magnetic wave takes to cross the column; at the sweep's fixed radius and density it is 0.17 time units.) That's long enough for every outcome seen in the GUI to develop.
- **Saved per run** (`dataset/sweep-2026-10-19/runs/rNNNNN.npz`): the starting parameters, the derived stability numbers, and the full diagnostic history sampled every 0.005 time units (energies, mode amplitudes, radius, core density and temperature, currents, conservation errors).
- **Parallelism:** 12 worker processes with 1 numba thread each. A benchmark found this ≈10 % faster than 6 × 2 and ≈2.8× faster than one job on 12 threads. Median 187 s per run, about 177 runs per hour.
- **Resumable:** each finished run is appended to `index.jsonl`, so the sweep can be killed and restarted with the same command. It was: the laptop was shut down at 07:08 (1109 runs) and the sweep resumed 08:16 – 18:16.
- **Resolution check:** 60 runs were repeated on a finer 48³ grid ("twins"), about 5× the cost each.

**Result:** 2902 runs: 2842 at 32³ plus the 60 twins. 36 stopped early at the wall-clock cap (kept, marked *partial*), and none failed.

| Outcome (rule label) | runs | share |
|---|---|---|
| kink → disruption | 1140 | 40.1 % |
| saturated helical kink | 745 | 26.2 % |
| gravity sag | 485 | 17.1 % |
| quiescent column | 267 | 9.4 % |
| resistive diffusion | 127 | 4.5 % |
| radiative collapse | 77 | 2.7 % |
| kink still growing | 1 | 0.0 % |
| sausage-dominated | 0 | 0 % |

No run is sausage-dominated, even in the sausage stratum: in this setup the kink always grows first (§5). The class stays in the program (a GUI user can reach it) and is tested on a synthetic run.

**Twins:** 59 of the 60 keep their label on the finer grid. The one that changes (r00340, quiescent → saturated kink) sat at the kink threshold.

---

## 4. Features: a run as 65 numbers

### What a feature is

A *feature* is one number that describes a whole run: "the largest kink amplitude", "the time the column first spread past 2 radii", "the share of the starting energy lost to radiation". The simulation history is thousands of numbers per curve; 65 well-chosen features say what matters about it in a table row. The rules read them, the models learn from them, and the library quotes them. `zpinch/analysis/features.py` computes them all, each with its unit and meaning (`FEATURES`).

| Group | How many | Examples | What they capture |
|---|---|---|---|
| Starting parameters | 10 | current, axial_field, length | what the user set |
| Stability numbers at t = 0 | 9 | q_a, kadomtsev_margin, lundquist, t_cooling | textbook criteria computed from the settings alone |
| Kink (m = 1) | 12 | m1_peak, m1_gamma, m1_t_onset, nq_seed | how big the kink got, how fast it grew, which helix |
| Sausage (m = 0) | 5 | m0_peak, m0_gamma | the same for necking |
| Bulk offset | 3 | shift_peak | the whole column moving (a gravity sag) |
| Geometry | 5 | radius_max, t_mixed | spreading and break-up |
| Core and extremes | 8 | core_temp_min, core_density_max | cooling, compression, collapse |
| Energy flows | 8 | d_magnetic, injected, radiated | which store gained and which lost |
| Numerical health | 4 | floor_energy, energy_error_max, divb_max, t_final | whether to trust the run |

(Amplitudes are in units of the column radius, *a*. Energies are fractions of the starting energy, *E0*. Times are in the code's time unit, *t0*; one Alfvén time is about 0.17 t0.)

### Three features worth understanding

**The growth rate, `m1_gamma`.** An instability grows exponentially, A(t) = A₀ e^{γt}, so ln A is a straight line with slope γ. The code fits that line over the window where the kink has clearly left its starting level (twice its minimum) but isn't yet nonlinear (half its peak). It also stores the fit's standard error and R² (1 = a clean exponential). The growth rate in Alfvén units, `m1_gamma_tA`, has a median of 0.80 across the sweep (10–90 %: 0.59–0.95). That is of order one, as ideal MHD expects for a current-driven kink, which grows on the Alfvén time.

**The seeded helix and `nq_seed`.** The starting perturbation is a helix with wavenumber k ≈ 1.2/a, so `seed_n` ≈ L_z / 5a whole twists fit along the column. The Kruskal–Shafranov criterion says a helix with n twists is kink-unstable when **n q < 1**. Here q = 2πaB_z/(L_z B_θ) is the *safety factor*, how many times a field line winds the long way round per time it winds the short way. So `nq_seed` = n × q is the single most important number in v3. Because n ∝ L_z and q ∝ 1/L_z, **n q ≈ 2πB_z/5 almost regardless of the column length or radius.**

**A blind spot, and `m1_resolved_frac`.** The saved history splits the kink into its n = 1, 2, 3 parts only. A column seeded with n ≥ 4 (anything longer than about 2.1 at the default radius) keeps its kink in a helix the split can't see. `m1_resolved_frac` records how much of the kink n = 1–3 carry. When it's below half, the dominant helix is reported as *unknown*, not guessed. (An early version guessed "n = 1", and the report told 287 runs something false; see [[05.3 - V3 Phase 4 Write-up Library]] §4.) With that fixed, the kink stays in the seeded helix in **all 1446** runs where it can be resolved.

---

## 5. The rules: labelling a run with physics

`zpinch/analysis/rules.py` turns a run into **phases** (a timeline) and **one outcome class**. It is the "teacher" for the models and the fallback if no model is installed.

### The 8 classes, and which wins

Several things can happen in one run (a kink grows, saturates, then the column sags), so the classes have a **priority**: the most violent end state names the run, and the others are listed as *secondary*.

| Priority | Class | Detected when (thresholds below) |
|---|---|---|
| 1 | radiative collapse | core temperature < 0.4 T0 **and** core density > 1.5× its start |
| 2 | kink → disruption | kink passes 0.3 a, then the column spreads past 2 a within 1.0 time unit |
| 3 | sausage-dominated | necking > 0.15 a, larger than the kink, for at least 0.1 time units |
| 4 | kink still growing | the kink peaks in the last 0.1 time units and still grows at ≥ ½ its fitted rate |
| 5 | saturated helical kink | kink passes 0.10 a, then stops growing; the column survives |
| 6 | gravity sag | the whole column falls by > 0.5 a |
| 7 | resistive diffusion | quiet, core density < 0.5× start, gained ≥ 4 % of E0 as heat, resistive time ≤ 2× the run |
| 8 | quiescent | none of the above |

### Every threshold has a reason

The rule is: **no threshold without a reason and a run that justifies it.** Each one is commented in `rules.py` with the runs it was checked on. The main ones:

| Threshold | Value | Why this value |
|---|---|---|
| `GROWN` | 0.10 a | 5× the 0.02 seed. Quiet runs settle at 0.03–0.09 after a start-up transient (r00194, r00739, r00027), so 0.10 sits just above them. |
| `NONLINEAR` | 0.30 a | in runs without gravity or cooling, fast radius growth first appears at a peak kink of 0.3–0.4 a |
| `DISRUPT_DELAY` | 1.0 t0 | a break-up follows the nonlinear kink quickly; a slow spread much later is diffusion |
| `SAG` | 0.5 a | gravity runs reach 0.5–1.5 a by t ≈ 0.5; without gravity the offset stays below ~0.3 a until break-up |
| `COLLAPSE_T`, `COLLAPSE_RHO` | 0.4 T0, 1.5× | the core-temperature minimum is bimodal (collapsed runs reach 0.05–0.15, the rest stay above 0.6); density separates a collapse from a column that cools while it expands |
| `RESISTIVE_CORE`, `RESISTIVE_HEAT` | 0.5×, 4 % E0 | quiet runs at η ~ 1e-4 fall only to ~0.7× (numerical diffusion) and gain ~1.5 %; at η ≥ 3e-3 they fall below 0.45× and gain ≥ 5 % |

**Compression** (core density +30 % while the drive is above 1.1 I_B) is a *phase*, not a class. In this setup the magnetic piston sweeps the background gas into a sheath and squeezes the core only briefly.

### Confidence: when is a label borderline?

If a number that decided the label is within **±15 %** of its threshold, the label is **low confidence** and the report says which number (`borderline()`), in the form "m1_peak = 0.107 is within 1.15x of its threshold 0.1". Nudging that threshold by 15 % would flip the label, so the user should know. 697 of 2842 runs are borderline, mostly saturated kinks near the 0.10 line.

Two extra checks were added because the run classifier disagreed with the rules (§7.5):
- **The tear-up delay** (r00817): the column spread 0.97 time units after the kink went nonlinear, against a cut-off of 1.0.
- **A near-miss radiative collapse** (r02076): the core cooled to 0.42 T0, just above 0.40, while 2.3× denser.

### Numerical health

Separately, a run is flagged when the **vacuum floors** added more than 5 % of the starting energy, or the **energy budget error** exceeded 0.1 %. (Floors are the minimum density and pressure the solver enforces in near-vacuum; adding energy there means the near-vacuum was under-resolved.) A flagged run still gets a label, but the report warns that details are suspect. In the sweep, 445 runs trip the floor flag and 250 the energy flag. All 445 floor-flagged runs and 215 of the 250 energy-flagged ones have a drive current above 1.5, and about three quarters are disruptions: violent, strongly driven runs.

### How the rules were checked

- **Hand-picked runs.** 12 sweep runs, at least one per class that occurs, were inspected by eye and are pinned in `tests/test_analysis.py`.
- **Kruskal–Shafranov, on the whole sweep.** For runs without gravity or cooling, the label against n q of the seeded helix:

| n q | runs | outcome |
|---|---|---|
| 0 – 0.25 | 262 | 260 disrupt, 2 saturate |
| 0.25 – 0.5 | 88 | 65 disrupt, 23 saturate |
| **0.5 – 1** | **108** | **all 108 saturate** |
| 1 – 1.5 | 130 | 85 saturate, 19 quiet, 26 resistive |
| **≥ 1.5** | **110** | **none grows a kink** (77 quiet, 33 resistive) |

That's the textbook criterion, reproduced by a simulation and a set of rules that knew nothing about it. Two details are physics, not noise:
- **Why stability sets in at 1.5, not 1.** For the Bennett profile B_θ ∝ r/(r² + a²), so q(r) ∝ r² + a²: **on the axis, q is half its edge value.** Just above n q = 1 the inner column is still unstable, which is why the kinks there are small (saturated kinks peak at a median 0.19 a, against 0.39 a below n q = 1).
- **Use the starting q, not q/I.** A strong drive's extra current flows mostly in the swept-up sheath, outside the column. So q < 0.1 at the start disrupts 96 % of the time, but q/I < 0.1 only 86 %.

---

## 6. Explaining a run: energy and stability criteria

`zpinch/analysis/explain.py` turns the label into *causes*. It uses two tools a physicist would use.

### Who paid for it? (energy bookkeeping)

The solver tracks every energy store: kinetic, magnetic, thermal, gravitational. It also tracks every flow across the boundary: the circuit's input, radiation, and the floor corrections. Their sum closes to about 10⁻¹⁵ of E0 in a typical run; this is the dotted-line check in the energy figure. For each phase of the timeline, `explain.py` takes the change in each store and says which ones paid and which gained:

> *The kink stopped growing at ~0.36 radii (t = 0.78) and the column survived as a bent helix. … Paid for by the magnetic field (6 % of E0); it went into heat (thermal) (4 %), the drive circuit (energy taken back out) (2 %).*

That's the physical story of a kink: it releases magnetic energy, and the released energy ends up as heat.

### What did theory predict? (stability criteria)

Each report has a table that compares textbook criteria, computed from the settings, with what the run did:

| Criterion | What it says |
|---|---|
| Kruskal–Shafranov q(a) and n q of the seeded helix | n q < 1: that helix can kink |
| Kadomtsev margin B_z² / (B_θ²/2) | > 1: the edge is stiff against sausage necking |
| Lundquist number S = a v_A / η | large: field lines are frozen into the plasma; small: they slip |
| Radiative cooling time | shorter than the run: cooling matters |
| Drive current vs Bennett | above 1: the field squeezes the column harder than its pressure pushes back |

Each row is marked ✓ (agrees) or ✗ (doesn't). The quoted sweep counts ("sweep: 184 of 184 such runs saturated") are read from `library/stats.json`, so they always match the data and the write-up beside them. An early version had counts typed in by hand, and they went stale.

---

## 7. Machine learning, from zero

### 7.1 The task: classification

*Classification* means: given some numbers about an example, say which of a fixed set of categories it belongs to. Here the example is a run, the numbers are its features, and the categories are the 6 outcome classes with enough runs to learn (kink still growing has 1 run and sausage 0, so those two are left to the rules). A model doesn't just name one class; it gives a **probability** for each: "saturated kink 78 %, disruption 19 %, …".

v3 has two models with different inputs:

| | (a) run classifier | (b) outcome predictor |
|---|---|---|
| Input | all **65 features** of a *finished* run | only what's known **before pressing Start**: the 8 settings plus 7 stability numbers computed from them (q_a, n q, seed n, Kadomtsev margin, resistive and cooling times, Lundquist number): **15 inputs** |
| Question | "what happened in this run?" | "what will happen if I run these settings?" |
| Honest value | it mostly re-learns the rules; its value is the probabilities and the **disagreements**, which point at weak spots in the rules | **a new capability**: an instant forecast, no simulation needed |
| Shown in | the report's "Machine-learning view" | the GUI's "Predicted outcome" line, live as you move sliders |

### 7.2 The model: gradient-boosted decision trees

**A decision tree** is a flowchart of yes/no questions about the inputs: "is n q < 0.42? If yes, is gravity > 0.3? …", ending in a leaf that holds a prediction. A single tree is easy to read but crude.

**Boosting** builds many small trees one after another. Each new tree is fitted to the *mistakes* of all the trees before it, and their outputs are added up. It's like a team of students where each one studies only the questions the others got wrong. After a few hundred small trees, the sum is accurate, and it still varies smoothly enough to give sensible probabilities.

v3 uses scikit-learn's `HistGradientBoostingClassifier`. It suits this problem:
- It works on a table of a few thousand rows of physical numbers.
- It needs no rescaling of inputs (a tree only asks "above or below?", so units don't matter).
- It handles missing values natively (`m1_dominant_n` is *unknown* for some runs).

The main settings:
- **max_leaf_nodes:** how big each tree may grow; smaller is simpler.
- **l2_regularization:** a penalty that keeps any one tree's contribution modest.
- **learning_rate:** how much of each new tree is added.
- 200 trees in all.

### 7.3 The one rule that matters: test on data the model never saw

A model can memorise its training examples and still be useless on new ones. This is *overfitting*, like a student who memorised last year's exam answers. So `tools/train.py` works in this order:

1. **Lock away 20 % of the runs as a test set** (562 runs) before anything else. The split is *stratified*: every class keeps its share, so the rare classes aren't all on one side.
2. **Choose the settings by 5-fold cross-validation on the other 80 %.** Split the training runs into 5 parts; train on 4 and score on the 5th; rotate, so every part is scored once. Average the 5 scores. Six combinations were tried (leaf nodes 4, 7, 15 × regularisation 0, 1). The winner is the one with the best *log loss* (below), not the best accuracy, because the probabilities matter. The grid is deliberately small: every extra combination tried is another chance to fit noise.
3. **Score the chosen model once on the locked-away test runs.** These are the numbers reported.
4. **Refit on all runs** for the saved model, now that the settings are fixed.

### 7.4 The scores, explained

| Score | Meaning | Why it's reported |
|---|---|---|
| **accuracy** | the share of test runs whose top answer matches the rule label | the headline |
| **balanced accuracy** | the hit rate averaged *per class*, so a 15-run class counts as much as a 227-run class | accuracy alone hides failure on rare classes |
| **macro F1** | per class, the balance of *precision* (when it says X, is it X?) and *recall* (of the real X, how many did it find?), averaged | catches a class that's over- or under-predicted |
| **log loss** | how much probability the model put on the right answer (lower is better); being 99 % sure and wrong costs a lot | rewards honest probabilities |
| **calibration error (ECE)** | group predictions by confidence; in each group, the gap between the stated confidence and the real hit rate, averaged | "when it says 80 %, is it right 80 % of the time?" |

**Baselines.** A score means nothing without something to beat. Two were used:
- **Always guess the commonest class (disruption):** 40.4 %.
- **The best one-line physics rule, using n q alone:** 67.6 %. It can't see gravity, cooling or resistivity.

### 7.5 Results

On the 562 locked-away test runs:

| | accuracy | balanced accuracy | macro F1 | log loss | ECE |
|---|---|---|---|---|---|
| **(a) run classifier** | **99.3 %** | 98.8 % | 0.983 | 0.023 | 0.005 |
| **(b) outcome predictor** | **94.3 %** | 93.3 % | 0.911 | 0.175 | 0.021 |
| n q rule only | 67.6 % | 44.6 % | 0.353 | – | – |
| always "disruption" | 40.4 % | 16.7 % | 0.096 | – | – |

On the broad stratum alone (a fair sample, 316 test runs): (a) 99.7 %, (b) 96.2 %.

**(b) class by class.** It finds 99 % of disruptions, 94 % of quiescent columns, 92 % of sags, 89 % of saturated kinks, all 25 resistive runs and 13 of 15 radiative collapses. Its weakest number: only 65 % of its *collapse* predictions are right. Cooling near the collapse threshold sometimes collapses and sometimes doesn't, depending on the random seed, which (b) can't see.

**More data helped.** The first training, on 1078 runs, scored (a) 98.6 % and (b) 88.0 % (balanced 76 %). Almost all of the gain since came from the thin classes, which is why the sweep was resumed for a second day.

**What (b) relies on.** Scramble one input across the test runs and see how much accuracy drops (*permutation importance*):

| Input | Accuracy lost when scrambled |
|---|---|
| **n q of the seeded helix** | **56 %** |
| gravity | 17 % |
| resistivity | 8 % |
| cooling | 5 % |
| drive current | 4 % |
| anything else | ≤ 1 % |

The model rediscovered the physics: **Kruskal–Shafranov decides the kink; gravity, resistivity and cooling decide the rest.**

**The outcome map** (`models/outcome_map.png`) shows (b)'s prediction over axial field × drive current, with real sweep runs overlaid. It reads like a phase diagram: disruption below n q ≈ 0.35–0.45, saturated kink in the middle, quiescent only at n q ≳ 1.4. Between n q = 1 and 1.5 the real runs are mixed, and the map is paler there (less sure).

**Calibration.** When (b) is more than 95 % sure, it's right 98 % of the time. When it says 55–75 %, it's a little over-confident (right 46–67 % of the time); those are borderline settings.

**The disagreements are the point of (a).** On the test runs, (a) disagreed with the rules 4 times. Each was checked by hand. Twice in the project's history a disagreement exposed a real weak spot, and the rules were improved:
- r00817: a tear-up delay at the cut-off.
- r02076: a near-miss collapse labelled high-confidence.

After those fixes, **all 4 remaining disagreements are runs the rules already call low-confidence.** The classifier never contradicts a confident rule label.

### 7.6 Knowing when not to trust the forecast

(b) has only seen the swept box. Before showing a forecast, `model.py` checks three things and appends a warning:

| Check | Warning |
|---|---|
| A setting outside the swept range (2 % slack) | "outside the training sweep: gravity" |
| A setting the sweep never varied (grid, radius, density, perturbation, solver, Spitzer) | "the sweep kept … at the default: treat as a rough guess" |
| The nearest training run is farther than 95 % of training runs are from their own nearest neighbour | "few training runs near these settings: less certain" |

The last test measures distance in the 8 swept parameters, on a log scale for the ones swept log-uniformly. A fixed radius doesn't work in 8 dimensions, so the threshold is relative to how densely the sweep covers the box.

The models are saved in `models/` with a **model card** (`MODEL_CARD.md`). It records what they were trained on (run count, dataset hash, scikit-learn version), every score above, the confusion matrices, the calibration curve, the outcome map, and the list of disagreements.

---

## 8. The curated write-up library

The rules and the causes are accurate but read like a lab log. The library puts a readable explanation on top, the way notes 01–04 are written.

### An entry

Each of the **21 entries** is a markdown file in `zpinch/analysis/library/`. A header says:
- which class the entry is for;
- which **regime box** of settings it covers (e.g. `nq_seed 0.5..1.0`);
- which **compare box** of sweep runs its statistics come from;
- an **example run** and a GUI **preset**, where there is one;
- a **review state**.

Three sections of text follow (*What happened*, *Why*, *Try next*), with `{placeholders}` for the run's numbers:

> *With B_z = {axial_field:.2f}, the safety factor at the column's edge is q = {q_a:.2f}. … In the overnight sweep, {regime_same} of the {regime_runs} runs in this band … saturated like this.*

### Choosing the entry

`writeup.py` takes every entry for the run's class whose regime box **contains** the run, and picks the most specific one (the most conditions; ties broken by priority). If none contains it, the class's **general** entry is used, and the report names the nearest regime entry and how far outside its box the run is. **An entry is never stretched beyond its box.** Every class has exactly one general entry, so every run gets text.

### Keeping the text true

- **Sweep statistics are counted, not typed.** `tools/library.py stats` counts the runs in each entry's compare box and writes `stats.json`; the placeholders read it. After the retrain, every count in every report updated in one command.
- **Every entry is tested on its example.** `tools/library.py check` re-analyses each example run and fails unless it gets the entry's class, picks that entry, and fills every number. It reports 0 problems.
- **"Try next" stays on the sliders.** A suggested B_z is computed for the run's own length and radius (e.g. the field that gives n q = 1.5). If it would be above the slider's maximum, the report says so.
- **Review state is shown.** All entries are *data-checked*: every claim was checked against the sweep data. None is *physicist-reviewed* yet, and each report says so. Entries marked `no` are never used.

Writing and checking the entries found two bugs in earlier phases (the helix blind spot of §4, and a "longer helix took over" claim with no data behind it). The retrain found a third case: pure Z-pinches labelled *saturated* were being told "the weak axial field held just enough", which is false with B_z = 0. They're slow disruptions on the cut-off, and a new entry says exactly that. Details: [[05.3 - V3 Phase 4 Write-up Library]].

---

## 9. The report, the GUI and the textbook runs

### One report, three places

`zpinch/analysis/report.py` builds the report as HTML from the analysis result:
1. the write-up (title, outcome, confidence, warnings, the three sections, where the text came from);
2. **three figures:**
   - the instability amplitudes, with each phase of the timeline shaded;
   - the energy stores, with the bookkeeping check line;
   - the column's radius, core temperature and core density;
3. the **data appendix**: timeline, causes, stability criteria, the ML view, the whole-run energy budget, all parameters and all 65 features.

The same builder makes two versions:
- **The GUI panel version.** Qt's text widget renders only a subset of HTML, so this version gets plain headings and the panel serves the figures from memory.
- **A standalone `.html` page.** Figures are embedded, it follows the browser's light/dark theme, nothing is fetched from the network, and long tables fold away.

Both versions use the same words. The report appears:
- in the **GUI's *Run report* panel**;
- as **report.html** in every export zip (next to `analysis.txt`, `analysis.json`, `features.csv` and the time series);
- from the command line: `--report run.html`, or `tools/library.py show RUN --html out.html` for any sweep run.

### The GUI flow

1. Pick a preset, your own settings, or a **Textbook run**: the exact settings of one of the 12 sweep runs the library entries were checked on. A textbook run sets every value itself, so the **Preset** box goes blank while one is loaded (it would otherwise still name a preset that isn't in use); picking a preset or **Reset to defaults** fills it again.
2. Watch the **Predicted outcome** line under the Run buttons; it updates as you move sliders.
3. Press **Start**. The run **pauses itself at t = 3**, the horizon of the sweep and of the forecast, so everything compares like with like. Then the report opens.
4. Read it top to bottom. The panel's buttons save it (HTML or text), copy it, load the textbook run for this write-up, or load the preset it names.

The analysis runs in the physics process, not the window, so the GUI never freezes while a report is built.

### Do textbook runs reproduce?

The sweep ran each case on **one** CPU thread; the GUI runs on several. More threads change the order in which parallel loops add numbers, so the last digits differ, and a kink grows exponentially from noise. So reproducing isn't automatic. `tools/library.py replay` re-simulates every textbook run from its saved settings alone, on 8 threads with tracers, exactly as the GUI does. The result:

**All 12 reproduce.** Re-simulated on 8 threads from `examples.json` alone (2026-10-20), every textbook run reaches the same outcome as in the sweep, selects the same library entry, and peaks at the same kink amplitude to two decimals (from 0.05 a for the stable screw pinch to 0.98 a for the pure Z-pinch). The thread count changes the last digits, but not the physics. Each run took 2–7 minutes.

---

## 10. Measured performance, in one place

| What | Number | Where it's measured |
|---|---|---|
| Sweep size | 2902 runs (2842 at 32³ + 60 at 48³), 0 failures | `tools/sweep.py status` |
| Labels stable under grid refinement | 59 of 60 twins | `analysis/summary.txt` |
| Kruskal–Shafranov reproduced | 0.5 ≤ n q < 1: 108/108 saturate; n q ≥ 1.5: 110/110 no kink | `analysis/summary.txt` |
| Energy bookkeeping | error ~1e-15 typical; 250 of 2842 runs above 1e-3 (flagged) | per run, `energy_error_max` |
| (a) run classifier vs rules | 99.3 % (balanced 98.8 %), ECE 0.005 | `models/MODEL_CARD.md` |
| (b) outcome predictor | **94.3 %** (balanced 93.3 %), ECE 0.021 | `models/MODEL_CARD.md` |
| (b) baseline: n q rule only | 67.6 % | `models/MODEL_CARD.md` |
| (a) on the 48³ twins (never trained on) | 60 of 60 agree with the rules | `models/MODEL_CARD.md` |
| Library entries on their example runs | 12 of 12 correct, 0 problems | `tools/library.py check` |
| Textbook runs reproducing on 8 threads | 12 of 12: same outcome, same entry, same kink peak to 2 decimals | `tools/library.py replay` |
| Automated tests | 107 (physics 27, analysis 28, models 7, library 31, report 14) | `./test.sh` |

---

## 11. Honest limits

- **The labels come from rules, not from nature.** A wrong rule teaches both models the same mistake. (a) agreeing 99.3 % says the rules are consistent and learnable, not that they're right. The rules are checked against theory (Kruskal–Shafranov, §5) and by eye, not against experiments.
- **One grid.** Everything is at 32³, the GUI default. 59 of 60 twins keep their label at 48³, but finer details (growth rates, the exact n q of the stability line) shift with resolution.
- **One box of settings.** Pinch radius, background density, perturbation, solver and Spitzer resistivity were never varied. The forecast says so when you change them.
- **The random seed matters near boundaries.** Two runs with the same settings and different seeds can end differently. (b) can't see the seed, which caps its accuracy below 100 %.
- **Thin classes.** 77 radiative collapses and 127 resistive runs, so their per-class test numbers are uncertain by about ±10–20 %. No run in the sweep is sausage-dominated.
- **The helix diagnostic sees n = 1–3 only.** Kinks in longer columns (n ≥ 4) are measured as a total, not by helix.
- **The write-ups are data-checked, not physicist-reviewed.** The report says so.
- **t = 3 is the horizon.** The sweep, the labels and the forecast all describe the outcome at t = 3; a longer run can move on (a saturated kink can still disrupt later).

---

## 12. Reproducing everything

From `v2/` (the full pipeline takes one night plus a few minutes):

```bash
# the data (resumable; ~177 runs per hour on 12 cores)
.venv/bin/python tools/sweep.py plan   dataset/sweep-2026-10-19 --n 8000 --res-check 60
.venv/bin/python tools/sweep.py run    dataset/sweep-2026-10-19 --jobs 12 --threads 1 --hours 10
.venv/bin/python tools/sweep.py status dataset/sweep-2026-10-19

# labels, models, library (about 2 minutes)
.venv/bin/python tools/analyse.py dataset/sweep-2026-10-19         # -> analysis/labels.csv, summary.txt
.venv/bin/python tools/train.py   dataset/sweep-2026-10-19         # -> models/, MODEL_CARD.md
.venv/bin/python tools/library.py stats dataset/sweep-2026-10-19   # -> library/stats.json
.venv/bin/python tools/library.py check dataset/sweep-2026-10-19   # every entry on its example
.venv/bin/python tools/library.py replay                           # textbook runs, re-simulated (~40 min)

# one run, one report
./run.sh --headless --t-end 3 --preset "Saturated kink (Bz = 0.6)" --analyse --report sat.html
.venv/bin/python tools/analyse.py dataset/sweep-2026-10-19/runs/r00273.npz

./test.sh                                                          # 107 tests
```

Pytest note for this machine: run it as `env -u PYTHONPATH PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest`, because a ROS installation on `PYTHONPATH` breaks pytest's plugin loading.

---

## 13. File map

```
v2/
  main.py                          entry point: GUI, or --headless [--analyse] [--report] [--export]
  zpinch/                          (v2) the simulator: solver, kernels, Z-pinch setup, parameters
    diagnostics.py                 plots + export zip (now with report.html, features.csv)
    analysis/
      features.py                  history -> 65 named numbers (§4)
      rules.py                     physics labeller: classes, timeline, confidence, health (§5)
      explain.py                   causes, stability criteria, plain-text report (§6)
      model.py                     loading and using the two models, coverage warnings (§7)
      writeup.py                   library loading, entry selection, filling (§8)
      report.py                    HTML report: panel + standalone, figures (§9)
      library/                     21 entries (*.md), stats.json, examples.json, README.md
    gui/
      app.py                       main window: report panel, textbook runs, pause at t = 3, forecast line
      worker.py                    physics process: runs the solver, builds reports, stop_at
  tools/
    sweep.py                       plan / bench / run / status / stop the overnight sweep (§3)
    analyse.py                     label one run or a whole sweep -> labels.csv, summary.txt
    train.py                       train + test both models, write the model card (§7)
    library.py                     stats / suggest / check / show / replay (§8, §9)
  models/                          run_classifier.joblib, outcome_predictor.joblib, MODEL_CARD.md,
                                   metrics.json, confusion.png, calibration.png, outcome_map.png,
                                   disagreements.md
  dataset/                         the sweep (git-ignored: 2902 runs)
  tests/                           test_physics, test_analysis, test_model, test_library, test_report
  screenshots/                     demo.gif, zpinch-demo.mp4, gui_report.png, gui_kink.png, gallery.png (§15)
  README.md                        results, screenshots, how to run
README.md                          the repo's front page: one paragraph, the main screenshot, links
docs/
  05 - V3 Plan.md                  the plan and its status log
  05.1 … 05.4                      one plain-language note per phase
  06 - V3 Technical Overview.md    this note
```

---

## 14. Glossary of the new words

| Word | Meaning |
|---|---|
| **Alfvén time** | the time a magnetic wave takes to cross the column, a / v_A; kinks grow on this clock |
| **balanced accuracy** | accuracy averaged per class, so rare classes count equally |
| **baseline** | a simple method a model must beat to be worth having |
| **boosting** | building many small models in sequence, each correcting the errors of the ones before |
| **borderline** | a label whose deciding number is within 15 % of its threshold |
| **calibration** | whether stated probabilities match real hit rates |
| **class** | one of the 8 outcomes a run can have |
| **compare box** | the sweep runs a library entry's statistics are counted over |
| **cross-validation** | scoring a model on held-out parts of the training data, in rotation, to choose its settings |
| **decision tree** | a flowchart of yes/no questions about the inputs ending in a prediction |
| **feature** | one number that summarises a whole run |
| **general entry** | a library entry with no regime box, used when no specific entry covers a run |
| **log loss** | a score for probabilities: how much was put on the right answer |
| **model card** | a document saved with a model saying what it was trained on and how well it does |
| **n q** | the Kruskal–Shafranov number of a helix with n twists: below 1 it can kink |
| **overfitting** | memorising training examples instead of learning the pattern |
| **permutation importance** | how much accuracy drops when one input is scrambled |
| **precision / recall** | of the runs predicted X, how many were X / of the real X, how many were found |
| **regime box** | the range of settings a library entry is written for |
| **rule label** | the class the physics rules give; the models' training target |
| **stratified split / strata** | keeping each class's share when splitting / sub-boxes oversampled for rare outcomes |
| **sweep** | many simulations with settings drawn across a box of parameters |
| **test set** | runs locked away before training, used once for the final score |
| **textbook run** | a clean sweep run a library entry was checked on, loadable in the GUI |
| **twin** | a sweep run repeated on a finer grid to check the label doesn't depend on resolution |

---

## 15. The demo

### A gallery anyone can open

```bash
.venv/bin/python tools/demo.py dataset/sweep-2026-10-19 demo/     # ~15 s
xdg-open demo/index.html
```

`demo/index.html` is one page: the headline scores, a card for each of the 12 textbook runs (outcome, settings, the opening sentence of its write-up, and its kink plot with the phases shaded), and the outcome map, calibration and confusion figures. Each card links to that run's full standalone report. Every page has its figures embedded, so the folder can be zipped and sent, and it opens without Python or the GUI. Nothing in it is computed afresh; it presents what the pipeline measured. (`v2/demo/` is git-ignored: regenerate it rather than commit it.)

### Screenshots

Most people who look at the project won't install it, so the READMEs carry three pictures (in `v2/screenshots/`):

- **`gui_report.png`**: the textbook run *Saturated kink just inside the Kruskal–Shafranov limit* (sweep run r00273), paused at t = 3. The 3D view shows the column bent into a helix, and the Run report on the right explains why it stopped. This is also the picture on the repo's front page (`README.md` at the top level).
- **`gui_kink.png`**: the same run at t = 1.6, when the kink is near its largest.
- **`gallery.png`**: the top of `demo/index.html`: the scores and the first six textbook-run cards.

The two GUI shots were taken by a small script that drives the real window: load the textbook run, set *Pause & analyse at t =* to 1.6, press Start, capture, then resume to t = 3 and capture again. One detail: the 3D view is drawn with OpenGL, which an ordinary window capture can return black, so the script paints the 3D view's own render over that part of the picture. To retake them by hand, do the same and use the screenshot key.

### The recording

Recorded 2026-10-20 with GNOME's screen recorder (three takes) and cut with ffmpeg into:

- **`v2/screenshots/zpinch-demo.mp4`** (55 s, for LinkedIn or a CV link): the textbook saturated-kink run at 10× then 6× speed, its report at t = 3 (full window, then zoomed onto the panel), then a pure Z-pinch with no axial field and the drive current raised to 3× Bennett at 10× speed, tearing apart, and its report. That report carries the coverage warning *outside the training sweep: current* (§7.6), since the sweep never went above about 2.8×.
- **`v2/screenshots/demo.gif`** (18 s, 760 px wide, 5 MB): the two runs only, faster, at the top of both READMEs. GitHub plays a GIF inline; it won't play an MP4 stored in the repo inside a README, which is why both exist.

Each segment has a caption naming what's happening and its speed-up. The 3-minute take was sped up rather than cut, so the physics shown is continuous; one accidental camera zoom (about 7 s) was cut out of the textbook run.

### A three-minute screen recording: the run sheet

The run sheet the recording was planned from: Start the GUI first and let it compile its kernels (first launch only), so the recording doesn't open on a wait.

| Time | On screen | Say (roughly) |
|---|---|---|
| 0:00 | the window, default settings, 3D view of the column | "A 3D MHD simulation of a Z-pinch: a plasma column held together by its own current's magnetic field." |
| 0:15 | move the **axial field** slider from 0 to 0.6 to 1.4, pausing on each; point at **Predicted outcome** | "Before running anything, a model trained on 2900 simulations forecasts the outcome. Watch it move from disruption to saturated kink to stable as the axial field grows: that's the Kruskal–Shafranov criterion, learned from data." |
| 0:45 | **Textbook run** → *Saturated kink just inside the Kruskal–Shafranov limit*; press **Start** | "This loads the exact settings of a run from the sweep." |
| 0:55 | the 3D view as the column bends into a helix and stops (orbit the camera once) | "The kink grows exponentially, then the stretched axial field stops it." |
| 1:30 | the run pauses at t = 3 and the **Run report** opens; scroll slowly through *What happened*, *Why*, *Try next* | "It pauses at t = 3 and explains itself in plain language, with this run's own numbers, plus the sweep statistics behind the claim." |
| 2:00 | scroll to the figures (phases shaded), then the criteria table and the ML view | "Underneath: the timeline, the energy bookkeeping, the stability criteria against theory, and the classifier's second opinion." |
| 2:30 | **Save report...**, then open the HTML in a browser; then `demo/index.html` | "The same report as a standalone page, and a gallery of every textbook run." |
| 2:50 | `models/outcome_map.png` | "94 % accurate before the run starts, against 68 % for the textbook rule alone." |

To record on Ubuntu: GNOME's built-in recorder (Ctrl + Shift + Alt + R, or Print Screen and switch the bar to video) saves a WebM in `~/Videos/Screencasts`. Or use OBS for the window only. A 40-second silent cut (load the textbook run, Start, orbit once, scroll the report) is enough for a README GIF.

