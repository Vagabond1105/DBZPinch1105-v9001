---
id: saturated-kink-no-bz
class: saturated_kink
title: A pure Z-pinch that only just escaped the disruption label
regime: axial_field 0..0; t_mixed 0..inf
compare: axial_field 0..0; gravity 0..0.3; cooling 0..0.3
priority: 1
reviewed: data-checked
---
## What happened
The column bent into a large corkscrew, peaking at {m1_peak:.2f} radii at t = {m1_t_peak:.2f}, and its plasma then spread out to {radius_max:.1f} radii. The rules call that a disruption only if the spreading follows within {disrupt_delay:g} time unit of the kink going nonlinear (passing {nonlinear:g} radii at t = {t_nonlinear:.2f}). Here it took until t = {t_mixed:.2f}, just too slow, so the run was labelled a saturated kink. Read it as a slow disruption.

## Why
With no axial field nothing resists bending: the safety factor is q = 0 and every helix is kink-unstable (Kruskal-Shafranov needs n q > 1). A real saturated kink is held by the axial field lines it stretches, and here there are none to stretch. What slowed the late stage is most likely the drive current and the viscosity: the few sweep runs that got this label all had a low drive current (here I = {current:.2f} Bennett currents) and most had a high viscosity (here {viscosity:.2g}), which damps the flow that spreads the plasma. In the overnight sweep, the {regime_runs} pure Z-pinches (little gravity or cooling) ended as: {regime_mix}.

## Try next
Rerun with another random seed (Setup: Random seed) and it will most likely be called a disruption; a longer run will not change the label, because the spreading has already happened. To get a genuine saturated kink, add an axial field: B_z = {bz_saturate:.2f} gives n q = {nq_saturate:.2f}.
