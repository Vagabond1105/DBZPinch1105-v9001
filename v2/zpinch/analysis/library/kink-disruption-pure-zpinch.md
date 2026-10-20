---
id: kink-disruption-pure-zpinch
class: kink_disruption
title: Pure Z-pinch: kink -> disruption
regime: axial_field 0..0; current 0..1.5
compare: axial_field 0..0; current 0..1.5; gravity 0..0.3; cooling 0..0.3
example: r00706
preset: Pure Z-pinch: kink -> disruption
reviewed: data-checked
---
## What happened
This is the classic Z-pinch failure. The column bent into a corkscrew that grew exponentially from t = {kink_growth_start:.2f}, passed {nonlinear:g} radii at t = {t_nonlinear:.2f} and then tore the column apart. By t = {t_mixed:.2f} its plasma had spread most of the way to the wall.

## Why
With no axial field, nothing resists bending. A bent current channel is squeezed harder on the inside of the bend, where the wrapped field lines crowd together, than on the outside, so any bend deepens. The kink grew at {m1_gamma_tA:.2f} per Alfven time (the time a magnetic wave needs to cross the column), the pace expected for an ideal kink: it grows as fast as the magnetic field can push the plasma. The safety factor is q = 0, so every helix is unstable (Kruskal-Shafranov stability needs n q > 1). This is why practical pinches add an axial field or a close-fitting conducting wall. In the overnight sweep, {regime_same} of the {regime_runs} pure Z-pinches near the Bennett current (little gravity or cooling) disrupted like this one.

## Try next
Set B_z to {bz_saturate:.2f} (n q = {nq_saturate:.2f}) and rerun: the kink should grow and then stop (compare the Saturated kink preset). At B_z = {bz_stable:.2f} (n q = {nq_stable:.2f}) it should not grow at all.
