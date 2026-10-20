---
id: kink-disruption-driven
class: kink_disruption
title: Driven pinch: kink -> disruption
regime: current 1.5..inf
compare: current 1.5..inf; nq_seed 0..0.5; gravity 0..0.3; cooling 0..0.3
example: r00302
preset: Implosion (snowplow)
priority: 1
reviewed: data-checked
---
## What happened
The circuit drove the current toward {current:.2f} times the Bennett value (rise time {rise_time:.2f}). The column then bent into a corkscrew that kept growing until it tore the column apart: the kink passed {nonlinear:g} radii at t = {t_nonlinear:.2f}, and by t = {t_mixed:.2f} the plasma had spread most of the way to the wall.

## Why
More current means a stronger wrapped field and a harder squeeze, so you might expect the column to be held tighter. In this setup, though, most of the extra current flows in a sheath of background gas that the rising field sweeps up outside the column. The core itself was squeezed to at most {core_density_max:.2f} times its starting density. What decides the kink is still the safety factor with the starting current. The helix the seed started had n q = {nq_seed:.2f}, below the Kruskal-Shafranov limit of 1, so the kink grew at {m1_gamma_tA:.2f} per Alfven time and nothing stopped it. The circuit fed the break-up: it put in {e_injected:.0f} % of the starting energy over the run. In the overnight sweep, the {regime_runs} strongly driven runs (current above 1.5, n q below 0.5, little gravity or cooling) ended as: {regime_mix}.

## Try next
More drive does not save the column, but an axial field does: B_z = {bz_saturate:.2f} (n q = {nq_saturate:.2f}) should give a saturated kink at this same current.
