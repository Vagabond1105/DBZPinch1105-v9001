---
id: saturated-kink-general
class: saturated_kink
title: Saturated helical kink
reviewed: data-checked
---
## What happened
The column bent into a corkscrew (a helical kink), which grew for a while and then stopped. It levelled off at about {m1_sat:.2f} radii (t = {t_sat:.2f}), and the column survived bent but whole. At the end the kink was {m1_final:.2f} radii.

## Why
The kink grows because a bent current channel is squeezed harder on the inside of the bend, where the wrapped field lines crowd together, than on the outside, so the bend deepens. The energy comes from that wrapped magnetic field. It grew at {m1_gamma_tA:.2f} per Alfven time (the time a magnetic wave needs to cross the column), the pace expected for an ideal kink. The axial field (B_z = {axial_field:.2f}) fights back: bending stretches its field lines, and the further the column bends, the more that costs. The kink stops once the wrapped field has no more energy it can release at that price. The helix the seed started had n q = {nq_seed:.2f}; the Kruskal-Shafranov rule says helices with n q < 1 can grow.

## Try next
Raise B_z to {bz_stable:.2f} (n q = {nq_stable:.2f}) and the kink should not grow at all; set it to 0 and the same column should disrupt.
