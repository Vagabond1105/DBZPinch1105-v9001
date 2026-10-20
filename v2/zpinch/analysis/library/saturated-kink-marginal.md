---
id: saturated-kink-marginal
class: saturated_kink
title: Saturated kink just inside the Kruskal-Shafranov limit
regime: nq_seed 0.5..1.0
compare: nq_seed 0.5..1.0; gravity 0..0.3; cooling 0..0.3
example: r00273
preset: Saturated kink (Bz = 0.6)
reviewed: data-checked
---
## What happened
The column bent into a corkscrew that grew for a while and then stopped, levelling off at about {m1_sat:.2f} radii (t = {t_sat:.2f}). It survived as a bent helix to the end of the run ({m1_final:.2f} radii at t = {t_final:.2f}). This is the textbook saturated kink.

## Why
With B_z = {axial_field:.2f}, the safety factor at the column's edge is q = {q_a:.2f}. The helix the seed started (n = {seed_n} turns along the column) therefore has n q = {nq_seed:.2f}: below 1, so Kruskal-Shafranov says it is unstable, but not far below. It grew at {m1_gamma_tA:.2f} per Alfven time. Being close to the limit means the axial field almost stiffens the column enough. As the helix deepens, the stretched axial field lines resist more and more, and growth stops once the magnetic energy the kink can reach is used up. In the overnight sweep, {regime_same} of the {regime_runs} runs in this band (n q from 0.5 to 1, little gravity or cooling) saturated like this.

## Try next
Raise B_z to {bz_stable:.2f} (n q = {nq_stable:.2f}) and the kink should not grow at all. Lower it to {bz_disrupt:.2f} (n q = {nq_disrupt:.2f}) and the column should be torn apart instead.
