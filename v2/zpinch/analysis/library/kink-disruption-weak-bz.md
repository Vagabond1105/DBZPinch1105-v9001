---
id: kink-disruption-weak-bz
class: kink_disruption
title: Disruption with too weak an axial field
regime: axial_field 0.001..inf
compare: axial_field 0.001..inf; nq_seed 0..0.5; gravity 0..0.3; cooling 0..0.3
example: r00192
reviewed: data-checked
---
## What happened
The column bent into a corkscrew that kept growing until it tore the column apart. The kink passed {nonlinear:g} radii at t = {t_nonlinear:.2f}, and by t = {t_mixed:.2f} the plasma had spread most of the way to the wall.

## Why
Your axial field (B_z = {axial_field:.2f}) resists bending, but it was too weak. The helix the seed started (n = {seed_n} turns along the column) had n q = {nq_seed:.2f}. The Kruskal-Shafranov rule says a helix can grow whenever n q < 1, and the further below 1, the more energy the kink can release before the stretched axial field stops it. Far enough below, that is enough to destroy the column. The kink grew at {m1_gamma_tA:.2f} per Alfven time. In the overnight sweep, the {regime_runs} runs with an axial field but n q below 0.5 (little gravity or cooling) ended as: {regime_mix}.

## Try next
Raise B_z to {bz_saturate:.2f} (n q = {nq_saturate:.2f}) for a kink that saturates instead, or to {bz_stable:.2f} (n q = {nq_stable:.2f}) for a column that stays straight.
