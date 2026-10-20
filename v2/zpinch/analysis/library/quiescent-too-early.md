---
id: quiescent-too-early
class: quiescent
title: Quiet so far: the kink has not had time to show
regime: nq_seed 0..1.0; t_final 0..1.5
compare: nq_seed 0..1.0; gravity 0..0.3; cooling 0..0.3
preset: Pure Z-pinch: kink -> disruption
reviewed: data-checked
---
## What happened
So far nothing has grown: at t = {t_final:.2f} the kink is {m1_peak:.2f} radii, about the size of the starting nudge. But the run is young.

## Why
The helix the seed started has n q = {nq_seed:.2f}, below the Kruskal-Shafranov limit of 1, so the column should be kink-unstable. A kink starts from the tiny seed and grows by the same factor every Alfven time (the time a magnetic wave needs to cross the column, {t_alfven:.2f} here). At the typical rate in the sweep it needs until about t = {t_kink_needed:.1f} to reach {grown:g} radii, so it has not had time to show yet. Runs with n q this low that ran to t = 3 (overnight sweep, without strong gravity or cooling) ended as: {regime_mix}.

## Try next
Resume the run until at least t = {t_kink_needed:.1f}, ideally t = 3, then press Finish & analyse again.
