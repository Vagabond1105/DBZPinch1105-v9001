"""
v3 run analysis (plan: docs/05 - V3 Plan.md).

    features.py   history -> named physical numbers (one row per run)
    rules.py      physics labeller: phase timeline + overall outcome class
    explain.py    causes from the energy budget and stability criteria, text report

    from zpinch.analysis import analyse_sim, analyse_npz
    report = analyse_npz("dataset/sweep-2026-10-19/runs/r00000.npz")
    print(format_report(report))
"""

from .explain import analyse, analyse_npz, analyse_sim, format_report  # noqa: F401
