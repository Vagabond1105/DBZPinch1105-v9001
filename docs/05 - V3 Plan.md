---
tags: [zpinch, mhd, v3, plan, machine-learning]
aliases: [V3 Plan, Run Analysis Plan]
---

# 05 · V3 Plan: end a run, classify it, explain it, write it up

> [!abstract] One-sentence version
> When you finish a simulation, v3 tells you **what kind of evolution you just watched**, for example "saturated helical kink", "kink → disruption" or "radiative collapse". It also tells you **why it happened**, using the run's own physics bookkeeping, and gives you a **curated write-up** that links your starting parameters to the outcome. The prose is readable by a student; every number a researcher would need sits underneath it.

Series: [[01 - Vision]] → [[02 - V1 and Why It Failed]] → [[03 - V2 Changes and Fixes]] → [[04 - V2 Complete Guide]] → **05 V3 Plan** → [[05.1 - V3 Phase 1 Results]] → [[05.2 - V3 Phase 3 Machine Learning]] → [[05.3 - V3 Phase 4 Write-up Library]] → [[05.4 - V3 Phase 5 Report Panel]] → [[06 - V3 Technical Overview]]

---

## Status (2026-10-20)

- **Phase 0 done:** commit `a85229e`, 27/27 tests passing.
- **Phase 2 sweep tool done:** `v2/tools/sweep.py` (commit `11ad9fb`), with subcommands `plan`, `bench`, `run`, `status` and `stop`. Runs are resumable and saved in `v2/dataset/` (git-ignored).
- **Parallel benchmark (default run, to t = 1):** 12 jobs × 1 thread is fastest, ≈10 % ahead of 6 × 2 and ≈2.8× one job on 12 threads. The laptop had dropped into the *power-saver* profile (low battery), which halved the speed (49 vs 20 ms/step). The sweep runs with `--keep-performance`.
- **Rehearsal (20 runs + 2 × 48³ twins, with a stop/resume in the middle):** 22/22 ok. Swept runs cost **~3× the default run**: median 187 s each at full load, 48³ twins ≈1000 s, so ≈230 runs/h, not the 300–700 of §6.4.
- **Overnight sweep, 2026-10-19 23:46 → 2026-10-20 07:08** in `v2/dataset/sweep-2026-10-19/`. It stopped early when the laptop was shut down (it was hot): **1109 runs** (1058 base + 51 of the 60 48³ twins), 0 real failures, 16 partial (wall-clock cap). It is resumable with the same `run` command. The early-stop rules never fired, because a disruption shrinks the radius-relative kink amplitude (see [[05.1 - V3 Phase 1 Results]] §4).
- **Phase 1 done (2026-10-20):** `v2/zpinch/analysis/` (features, rules, explain), `tools/analyse.py`, `--analyse`, *Finish & analyse* button, analysis in exports; 55/55 tests. Labels: disruption 435, saturated kink 259, gravity sag 198, quiescent 89, resistive 47, radiative collapse 30, sausage 0. The labels reproduce Kruskal–Shafranov ($nq$ of the seeded helix) cleanly; 50/51 twins keep their label at 48³. **Full write-up: [[05.1 - V3 Phase 1 Results]].** The class list in §3 below was revised against the data (sausage never dominates; compression is a phase, not a class).
- **Sweep resumed 2026-10-20 08:16** (same command, deadline 18:16), to fill the thin classes (radiative collapse, resistive).
- **Phase 3 first version done (2026-10-20):** `zpinch/analysis/model.py`, `tools/train.py`, models in `v2/models/` (with `MODEL_CARD.md`). On 216 locked-away test runs: (a) run classifier 98.6 %, (b) outcome predictor **88.0 %** vs 68.1 % for the n q rule alone. The GUI shows a live "Predicted outcome" under the Run buttons. **Write-up from zero: [[05.2 - V3 Phase 3 Machine Learning]].**
- **Phase 4 done (2026-10-20):** the curated write-up library: 20 entries (21 after the retrain) in `v2/zpinch/analysis/library/` (a general entry per class plus regime entries cut along the sweep's n q boundaries), `zpinch/analysis/writeup.py` (picks the most specific entry whose box contains the run, fills in its numbers), `tools/library.py` (stats, suggest, check, show). Sweep counts in the text are filled from a generated `stats.json`, so they update with the data. Every report (`--analyse`, *Finish & analyse*, export zips) now opens with *What happened*, *Why* and *Try next*, with the Phase 1 output underneath as the data appendix. All entries are `data-checked`; none is physicist-reviewed yet. Writing them found a **Phase 1 bug**: the kink diagnostic sees only n = 1–3, so columns seeded with n ≥ 4 were reported as "n = 1" (fixed; 05.1 corrected). **Write-up: [[05.3 - V3 Phase 4 Write-up Library]].**
- **Phase 5 done (2026-10-20):** a *Run report* panel docked beside the 3D view (write-up, three figures with the phases shaded, data appendix); runs **pause and analyse at t = 3** by default (the sweep's and the predictor's horizon); a *Textbook run* list and button load the exact settings of each entry's example run; *Save report...* writes a **standalone HTML report** (figures embedded, light/dark, no network), which the export zip also carries with `features.csv`; `--report` for headless runs. `zpinch/analysis/report.py` builds both the panel and the file from one function. The criteria table's sweep counts now come from `stats.json` too (they had gone stale). **Write-up: [[05.4 - V3 Phase 5 Report Panel]].**
- **Sweep finished 2026-10-20 18:16** (its deadline): **2902 runs** (2842 base at 32³ + 60 48³ twins), 36 partial (wall-clock cap), 0 failures. Labels: disruption 1140, saturated kink 745, gravity sag 485, quiescent 267, resistive 127, radiative collapse 77, still growing 1, sausage 0. The n q pattern holds on 2.7× the data: 0.5 ≤ n q < 1 saturated in 108 of 108 runs without gravity or cooling, n q ≥ 1.5 grew no kink in 110 of 110. Twins: 59 of 60 keep their label at 48³.
- **Retrain done (2026-10-20 evening):** on 2807 finished runs (562 locked-away test runs), **(a) 99.3 %** (was 98.6 %), **(b) 94.3 %** (was 88.0 %; balanced accuracy 76 → 93 %, nearly all from the thin classes) vs 67.6 % for the n q rule. Two more weak spots found and fixed: a near-miss radiative collapse was labelled high-confidence (r02076, found by the classifier disagreeing; the rules now flag it), and 4 pure Z-pinches labelled *saturated* were told an axial field held them (new entry `saturated-kink-no-bz`). After the fix, all 4 classifier–rule disagreements are runs the rules already call low-confidence. Notes 05.2 and 05.3 carry the new numbers.
- **Phase 6 done (2026-10-20):** **[[06 - V3 Technical Overview]]**, the whole of v3 from zero (pipeline, sweep, features, rules, ML, library, report, measured performance, limits, how to reproduce, glossary); a README results section; `tools/demo.py` builds a browsable gallery (headline scores + every textbook run's report); a 3-minute recording run sheet is in 06 §15.
- **v3 is complete.** Left for the user: record the demo (06 §15); optionally have library entries physicist-reviewed; scrub the old co-author trailers from `a85229e`, `f1a2a06`, `db0399f` before pushing to GitHub.
  - **User to do:** pick a *Textbook run*, press Start and read the report that opens at t = 3; check the "Predicted outcome" line. Optionally review library entries (`library/README.md`). Before pushing, scrub the old co-author trailers from `a85229e`, `f1a2a06` and `db0399f`.
- **Who builds what:** Claude writes all the code (agentically engineered). Every threshold is commented with its reason, each phase gets a plain-language summary, and note 06 is written for someone starting from zero.

## 0. Decisions already made

| Question | Decision |
|---|---|
| What does the ML do? | **(a) first:** classify a *finished* run from its time history. **(b) next:** predict the outcome from the *starting parameters alone*, before running, trained on the same dataset. |
| Where do write-ups come from? | A **fixed, curated library**: hand-checked entries with this run's numbers filled in. No free-form text generation, so no invented physics. |
| Audience | **Approachable for students** (plain language, like notes 01–04), with **full data for researchers** (fitted rates with uncertainties, stability criteria, energy tables, CSV export). |
| Purpose | **A demo of technical competency.** Scope is sized to be complete, honest and polished, not exhaustive. |
| Compute budget | **One overnight run (~10 h)**, enough for ~2000–5000 runs on the default grid (§6.4). |
| Final deliverable | Working v3 + **`06 - V3 Technical Overview`**, a complete technical document of how v3 works. |

---

## 1. Where v2 stands (starting point)

A health check on 2026-10-15 found **no solver bug**. Default run, *Very fast* grid:

| t | kink amplitude (n = 2 helix, in units of a) | sausage (m = 0) |
|---|---|---|
| 0.3 | 0.04 | 0.01 |
| 0.6 | 0.14 | 0.05 |
| 1.0 | 0.85 | 0.05 |
| 1.2 | 1.6 | 0.02 |
| 1.4 | 2.4 → column breaks up | n/a |

The kink grows cleanly and then disrupts. With $B_z = 0$ nothing can stop it, so that is correct physics. With an axial field it saturates instead:

| $B_z / B_\theta$ | peak kink amplitude | late time (t = 1.5–3) |
|---|---|---|
| 0 | 2.4 a | disrupted at t ≈ 1.3 |
| 0.6 | ≈ 0.6 a | persistent corkscrew, 0.1–0.45 a |
| 1.0 | ≈ 0.3 a | gentle helix, ≈ 0.15 a |

> [!important] Why this matters for v3
> The same code gives **very different outcomes** depending on its starting parameters. That spread of outcomes is what makes classification meaningful. It also shows that the outcome depends on *time*: a run stopped at t = 1 is "growing kink", and the same run stopped at t = 1.5 is "disruption". The classifier therefore has to look at the whole trajectory, not just the final frame.

Known v2 weak spots (**fixed in Phase 0, 2026-10-15**: per-n mode diagnostics, separate bulk-offset diagnostic, presets, corrected T1; 27/27 tests pass): the T1 tutorial claims the kink "saturates" (it actually disrupts); the $m=1$ diagnostic can't tell a gravity sag from a kink; there is no per-wavenumber mode diagnostic; the column is only ~8 cells across on the default grid.

---

## 2. What each piece can honestly do

| Piece | What it does well | Trap we are avoiding |
|---|---|---|
| **Rule-based labeller** | Applies physics criteria (growth fits, wall contact, energy flows) to give a transparent label. | Hard thresholds break on borderline or mixed runs. |
| **ML classifier (a)** | Learns the boundaries between classes from many runs, gives *probabilities*, and handles mixed and borderline cases. | There are no real-world labels. The labels come from the rules plus manual review, so on easy runs ML ≈ rules. Its value is on the hard runs, and in flagging runs that look unlike anything it has seen. |
| **Outcome predictor (b)** | "If I press Start with these settings, what will probably happen?" It answers instantly and draws a map of parameter space. | It is only trustworthy *inside* the region the sweep covered, so it must say when you're outside it. |
| **Causal explanation** | Comes from **physics bookkeeping**: which energy store paid for the motion, when exponential growth began, whether $q$ and the Kadomtsev number were above or below their thresholds, and when the column touched the wall. | ML feature-importance (e.g. SHAP) shows *correlation*, not *cause*. It appears only as a secondary "what the model looked at" panel and is never presented as the explanation. |
| **Write-up library** | Curated text, consistent and checkable, with numbers filled in. | A library can't cover every combination, so retrieval picks the *nearest* entry and the report says how close the match is. |

---

## 3. Outcome classes (draft taxonomy)

> [!note] Revised by the data (Phase 1)
> The final class list and the rules behind it are in [[05.1 - V3 Phase 1 Results]] §3. Changes: *compression / bounce* became an early **phase**, not a class; *sausage-dominated* is kept but no run in the sweep qualifies; *mixed / unclassified* is a **low-confidence flag** on the nearest class, not a class of its own.

| # | Class | Signature in the data |
|---|---|---|
| 1 | **Stable / quiescent** | All mode amplitudes flat or decaying; kinetic energy stays tiny |
| 2 | **Saturated helical kink** | $m=1$ grows exponentially, then plateaus well below the wall; magnetic energy drops, then levels off |
| 3 | **Kink → disruption** | $m=1$ keeps growing past ~1.5 a; wall contact; sudden spread of the spectrum to high $m$/$n$; sharp heating |
| 4 | **Sausage-dominated** | $m=0$ grows faster than $m=1$; necks; peak density spikes on axis |
| 5 | **Compression / bounce** | Driven current > Bennett value; radius falls, then oscillates; Bennett ratio oscillates around 1 |
| 6 | **Radiative collapse** | Radiated energy dominates the budget; core temperature falls while density rises |
| 7 | **Resistive decay / diffusion** | Ohmic heating dominates; current profile broadens smoothly; no mode growth |
| 8 | **Gravity sag** | Centroid shifts as a whole (axial wavenumber n = 0) toward −y; no helical (n ≥ 1) structure |
| 9 | **Mixed / unclassified** | Low confidence or rules and ML disagree, and the report says so openly |

Classes can **combine in sequence** (e.g. compression → kink → disruption). So the output is a *timeline of phases*, with one class per phase, plus an overall label.

---

## 4. Features: what the classifier sees

Each run is reduced to ~40 physical numbers. They are named, have units, and are meaningful to a researcher:

- **Starting parameters (all setup + live values):** current, rise time, η, ν, cooling, gravity, $B_z$, a, $L_z$, background density, seed.
- **Derived stability numbers at t = 0:** safety factor $q(a) = 2\pi a B_z/(L_z B_\theta)$, Kadomtsev margin $B_z^2 / (B_\theta^2/2)$, Lundquist number $S = a v_A/\eta$, plasma β.
- **Mode growth:** fitted exponential rate and its uncertainty for $m=0$ and $m=1$ at each axial n, onset time, saturation level, time of peak.
- **Energy flows:** the fraction of magnetic energy converted to kinetic and to thermal, injected energy, radiated energy, and vacuum-floor energy (a numerical-health flag).
- **Geometry:** minimum, maximum and final radius; peak centroid offset; wall-contact time; centroid drift direction.
- **Extremes:** peak density, peak temperature and when each occurred; energy-error and ∇·B maxima (to flag numerically suspect runs).
- **Spectrum spread:** how much energy reaches the high-m and high-n modes (the signature of turbulence and disruption).

The model also gets the **down-sampled time series** (~200 points per diagnostic), which leaves room for a small sequence model later if trees on features turn out not to be enough.

---

## 5. Architecture

```
zpinch/analysis/
  diagnostics_ext.py   mode spectrum per axial n, wall-contact & floor-activity flags,
                       sparse snapshots (every Δt) for the report figures
  features.py          history → feature table (§4)
  rules.py             physics labeller: training "teacher" + runtime fallback
  model.py             (a) run classifier, (b) outcome predictor - gradient-boosted trees,
                       saved as versioned files with the dataset hash they were trained on
  explain.py           phase timeline + causal chain from the energy budget and criteria
  library/             curated write-ups (markdown + front-matter, §7)
  report.py            assembles the report: narrative, figures, data appendix, CSV
tools/
  sweep.py             batch headless runs → dataset/ (one row per run + time series)
  train.py             trains and evaluates both models, writes a model card
```

**Flow when you click _Finish & analyse_:**

```
history ──▶ features ──┬──▶ rules ──┐
                       └──▶ ML (a) ─┴─▶ label + confidence (+ "rules and ML disagree" flag)
                                                │
energy budget + criteria ──▶ explain ──▶ phase timeline + causes
                                                │
label + parameters ──▶ nearest library entry ──▶ fill in run's numbers ──▶ report
```

**Before pressing Start (b):** the setup panel shows "Predicted outcome: saturated kink (78 %) · disruption (19 %) · …", plus a warning if the settings lie outside the training region.

---

## 6. Compute budget, explained

### 6.1 Why it costs what it costs

A run's cost is **cells × time steps**. Doubling the grid size N gives 8× the cells *and*, because each step must shrink with the cell size (the CFL limit), 2× the steps. Cost therefore scales as **N⁴**:

| Grid | Relative cost per run |
|---|---|
| 24 × 24 × 36 | ≈ 0.3× |
| 32 × 32 × 48 (*Very fast*) | 1× |
| 48 × 48 × 72 (*Fast*) | ≈ 5× |

Some settings are slower still, because fast waves force smaller time steps: high current, strong $B_z$, low background density, violent compression. They can cost **2–5×** more.

### 6.2 Measured (clean benchmark, 2026-10-15)

Default run, *Very fast* 32³ grid, to t = 3, nothing else running:

| Threads | Wall time | Note |
|---|---|---|
| 12 | **17.6 s** | 1191 steps, 14.8 ms/step |
| 2 | **28.2 s** | 23.7 ms/step |
| 2 (24³ grid) | 6.9 s | 748 steps |

> [!warning] Correction
> An earlier draft of this plan estimated 3–6 min per run. That number was measured while the GUI was using ~7 of the 12 cores and my diagnostic script was adding overhead. Clean runs are **~10× faster**, which changes the budget completely (§6.4).

> [!tip] Throughput trick
> 12 threads is only 1.6× faster than 2 threads on this grid, so running **~6 simulations side by side at 2 threads each** should give ~3–4× more runs per hour than one at a time. This is an estimate until the Phase 2 benchmark measures it, since parallel jobs compete for memory bandwidth.

### 6.3 How many runs are needed

- **(a) Classifier:** ~100–200 examples per class × ~9 classes. Classes are uneven, because random settings rarely produce e.g. radiative collapse, so we sample those regions on purpose. That gives **~1000–1500 runs**.
- **(b) Predictor:** must cover the swept parameter space densely enough to draw an outcome map, so it wants **~2000+ runs**. It uses the same dataset as (a).
- **Resolution check:** repeat a subset at a finer grid to see whether the *label* changes with resolution.

### 6.4 What one night buys

At ~30 s per run per 2 threads, 6 runs in parallel, and slow regimes (high current, strong $B_z$, violent compression) costing 2–5× more:

| | Estimate |
|---|---|
| Runs per hour (32³) | ~300–700 |
| **Runs per night (~10 h, 32³)** | **~2000–5000** |

**This is enough for both (a) and (b) on the default 32³ grid.** No coarse 24³ grid is needed, so the "trained on coarse runs, used on fine runs" risk disappears for the GUI's default grid.

Storage is small: features plus down-sampled histories are ≈ 100 kB per run, so ≈ 0.5 GB for 5000 runs. Full 3D snapshots are kept only for a handful of reference runs.

### 6.5 Decision: one overnight sweep at 32³

- **Grid:** the GUI default, 32³ (*Very fast*).
- **Swept parameters (8):** current, rise time, axial field $B_z$, resistivity, viscosity, cooling, gravity, column length. Pinch radius and background density stay fixed, because changing them changes how many cells the column spans (a resolution effect, not physics).
- **Stop runs early** once they have clearly ended (disrupted, or flat for a long stretch), with t = 3 as the cap.
- **Oversample the rare classes** (radiative collapse, sausage, gravity sag) by biasing the sampling toward their regions.
- **Resolution check:** ~100 runs repeated at 48³ (5× cost each) during the same night.
- **Rehearse first:** a 20-run, ~5-minute dry run checks the pipeline before the overnight launch, so the night isn't wasted on a bug.

Phase 1 still needs no sweep at all.

---

## 7. The curated write-up library

**Size:** ~15–25 entries (one general entry per class plus regime entries for the common classes). Each one covers a class × parameter regime (e.g. *saturated kink, near-marginal $B_z$*; *disruption, pure Z-pinch*; *radiative collapse under compression*).

**Format** (one markdown file per entry):

```markdown
---
id: kink-saturated-marginal-bz
class: saturated_kink
regime: {axial_field: [0.4, 1.2], current: [0.8, 1.3], cooling: [0, 0.1]}
---
## What happened
The column bent into a corkscrew that grew for about {t_onset_to_sat:.1f} Alfvén
times and then stopped growing at {m1_sat:.2f} column radii ...

## Why
Your axial field gave q(a) = {q_a:.2f}. Below 1 the longest kink is unstable,
but the field lines' stiffness ...

## Try next
Raise B_z to {bz_stable:.2f} and the kink should not grow at all (T3).
```

**Two layers per report:**
1. **Narrative (students):** what happened, why, what to try next. Plain language, consistent with notes 01–04.
2. **Data appendix (researchers):** fitted growth rates ± uncertainty, criteria values, the energy-partition table, the phase timeline with times, classifier probabilities, library match distance, model version, and a CSV of every feature.

**Who writes them:** Claude drafts, you review the physics, and each entry is marked `reviewed: yes/no`. Unreviewed entries are never shipped.

**Retrieval:** filter by class, then pick the entry whose regime box contains (or is nearest to) the run's parameters. If nothing is close, the report falls back to the class's general entry and says so.

---

## 8. Phases and "done" criteria

| Phase | Work | Done when |
|---|---|---|
| **0 · v2 fixes** | Per-n mode diagnostic, gravity-sag detector, T1 wording, $B_z ≈ 0.6$ "saturated kink" preset, run `./test.sh` cleanly | Tests pass; T1 matches what the code does |
| **1 · Rules + features + explain** | §3–§5 without ML; *Finish & analyse* button; `--analyse` headless flag | Hand-picked runs from every class are labelled and explained correctly |
| **2 · Sweep** | `tools/sweep.py`, clean benchmark, 20-run rehearsal, one overnight sweep + resolution check (§6.5) | Every class has enough runs to evaluate (target ≥ 100); resolution sensitivity is measured |
| **3a · Classifier (a)** | Train on run histories, evaluate on held-out runs, confusion matrix, rules-vs-ML disagreement review, model card | Held-out accuracy reported per class; disagreements inspected by hand |
| **3b · Outcome predictor (b)** | Same dataset and tooling as 3a; inputs = the 8 swept parameters + derived criteria ($q$, Kadomtsev margin, Lundquist number); target = dominant outcome by t = 3. Calibration check, out-of-range warning, **outcome-map plot** (predicted outcome over $B_z$ × current with theory thresholds and real runs overlaid), live prediction in the GUI setup panel. No active-learning top-up (needs a second night). ~350 lines | Held-out accuracy and calibration curve reported; outcome map reproduces the Kruskal–Shafranov trend; GUI prediction updates as sliders move |
| **4 · Library** | ~15–25 entries drafted, reviewed, regime-tagged | Every class has a general entry plus regime entries; all are reviewed |
| **5 · Integration** | GUI report panel, export zip includes report + CSV + standalone HTML report | A student can run, finish and read the report without help |
| **6 · Write-up & demo** | `06 - V3 Technical Overview` (full technical document: architecture, data pipeline, features, rules, models, evaluation results, limitations); README results section; short screen recording | Someone reading only note 06 understands every part of v3 and its measured performance |

---

## 9. Risks

- **Labels are only as good as the rules.** Mitigated by manual review of disagreements and of low-confidence runs.
- **Grid dependence.** The dataset uses the GUI default grid (32³); the 48³ check in Phase 2 measures how much labels shift on finer grids, and the report states the grid the model was trained on.
- **Time-dependence of outcomes.** Handled by classifying phases along the timeline, not just the end state.
- **Predictor overconfidence outside the sweep.** Handled by the out-of-range check plus a calibration test.
- **Compute.** Phase 1 is useful with zero sweep, so nothing blocks on it.

## 10. Resolved questions

- **Standalone HTML report:** yes. It's easy to show in a demo without launching the GUI.
- **Fixed end time vs early stop:** early stop (§6.5), with t = 3 as the cap.
- **Which classes to oversample:** the rare ones (radiative collapse, sausage, gravity sag), so every class can be evaluated.

## 11. What makes this a strong demo

- **Real substrate:** a validated 3D MHD solver with exact energy bookkeeping, not a toy dataset.
- **End-to-end pipeline:** simulation → automated dataset generation → features → models → explanations → report.
- **Honest evaluation:** held-out accuracy per class, confusion matrix, calibration of the predictor, a resolution-sensitivity check, and an explicit comparison of ML against the physics rules.
- **Correct division of labour:** causes come from physics, and ML is used where it actually helps (borderline runs, instant prediction). Overclaiming "the AI explains the physics" is exactly what an expert reviewer would catch.
