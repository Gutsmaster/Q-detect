"""
Fair comparison of the aggregate detector against Q-DETECT's basis-resolved
monitor, run against the ACTUAL pipeline (teleportation -> SARG04 ->
Weng protocol -> detector), not a standalone model of it.

Why this script exists
-----------------------
qdetect_verdict's Mahalanobis test calibrates itself automatically to the
observed sample size (see detector.py). The aggregate path has no such
calibration: qdetect_verdict's `aggregate_alarm` output compares against a
hardcoded 10% cutoff, which sits well above the honest mean at the demo
operating point (~7%), so it essentially never fires. That is not a fair
baseline -- it's an uncalibrated one, and it would make the standard
detector look better than it is, not worse.

To compare fairly, this script gives the aggregate path the same courtesy
we give the monitor: the *best available* fixed threshold, calibrated on
held-out honest data, exactly per the project's own standing rule --
"best available fixed threshold for the calibrated channel, not a weak
one." See PROTOCOL.md / the assumptions slide for that principle.

Two-phase design (kept separate so each phase finishes inside a normal
tool/CI time budget):

    python experiments/detector_comparison.py calibrate   # phase 1
    python experiments/detector_comparison.py test        # phase 2
    python experiments/detector_comparison.py plot        # phase 3 (needs matplotlib)

Phase 1 estimates the 99th-percentile honest aggregate error rate from a
calibration set and writes it to disk. Phase 2 runs a held-out set of
honest and z_bias(intensity=1.0) trials, applies that threshold to the
aggregate path and reads the pipeline's own (already self-calibrating)
Mahalanobis verdict for the monitor path, and writes FAR/TPR for both
plus the raw (aggregate, mahalanobis, label) triples used for the
scatter plot. Phase 3 renders that scatter plot to a PNG.

Every number this script prints is measured from this run, not carried
over from any earlier document. Re-run it before trusting a number on a
slide.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path

from qdetect.contract import KeyPool
from qdetect.simulator import SimulationConfig, reset_session, run_pipeline

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)
CALIB_FILE = RESULTS_DIR / "detector_comparison_calibration.json"
OUT_FILE = RESULTS_DIR / "detector_comparison.json"

N_RAW = 200_000          # matches the "detector demo, 7% fibre" operating point
N_CALIBRATE = 100        # honest runs used only to set the aggregate threshold
N_TEST_PER_CONDITION = 150   # held-out honest / z_bias runs used to measure FAR/TPR
FAR_TARGET = 0.99        # calibrate the aggregate threshold at the 99th percentile


def _one_run(attack: str, seed: int) -> dict:
    reset_session()
    pool = KeyPool(pairs_generated=50_000_000)
    with contextlib.redirect_stdout(io.StringIO()):
        r = run_pipeline(
            SimulationConfig(n_pulses=N_RAW, seed=seed, attack=attack,
                              length_km=0.0, force_click=True),
            pool=pool,
        )
    return r.public_dict()


def phase_calibrate() -> None:
    aggs = []
    for s in range(N_CALIBRATE):
        d = _one_run("none", seed=100_000 + s)  # seed range disjoint from phase 2
        aggs.append(d["charlie_axis"]["aggregate"])
    aggs.sort()
    idx = int(FAR_TARGET * (len(aggs) - 1))
    threshold = aggs[idx]
    CALIB_FILE.write_text(json.dumps({
        "n_calibrate": N_CALIBRATE,
        "far_target": FAR_TARGET,
        "aggregate_threshold_99": threshold,
        "aggregate_samples": aggs,
    }, indent=2))
    print(f"Calibrated aggregate threshold (99th pct of {N_CALIBRATE} honest "
          f"runs): {threshold:.5f} ({threshold*100:.3f}%)")
    print(f"Written to {CALIB_FILE}")


def phase_test() -> None:
    if not CALIB_FILE.exists():
        print("Run 'calibrate' first.", file=sys.stderr)
        sys.exit(1)
    calib = json.loads(CALIB_FILE.read_text())
    agg_threshold = calib["aggregate_threshold_99"]

    rows = []  # one dict per run: aggregate, mahalanobis, condition, agg_alarm, mon_violation

    def run_condition(attack: str, condition_label: str, seed_offset: int):
        for s in range(N_TEST_PER_CONDITION):
            d = _one_run(attack, seed=seed_offset + s)
            ax = d["charlie_axis"]
            mon = d["monitor_charlie"]
            rows.append({
                "condition": condition_label,
                "aggregate": ax["aggregate"],
                "mahalanobis": mon.get("mahalanobis"),
                "monitor_label": mon["label"],
                "agg_alarm_calibrated": ax["aggregate"] > agg_threshold,
                "mon_violation": mon["label"] == "VIOLATION",
            })

    run_condition("none", "honest", seed_offset=0)
    run_condition("z_bias", "z_bias", seed_offset=50_000)

    honest = [r for r in rows if r["condition"] == "honest"]
    attack = [r for r in rows if r["condition"] == "z_bias"]

    far_agg = sum(r["agg_alarm_calibrated"] for r in honest) / len(honest)
    far_mon = sum(r["mon_violation"] for r in honest) / len(honest)
    tpr_agg = sum(r["agg_alarm_calibrated"] for r in attack) / len(attack)
    tpr_mon = sum(r["mon_violation"] for r in attack) / len(attack)

    summary = {
        "n_raw": N_RAW,
        "n_per_condition": N_TEST_PER_CONDITION,
        "aggregate_threshold_used": agg_threshold,
        "false_alarm_rate": {"aggregate": far_agg, "qdetect": far_mon},
        "detection_rate": {"aggregate": tpr_agg, "qdetect": tpr_mon},
        "rows": rows,
    }
    OUT_FILE.write_text(json.dumps(summary, indent=2))

    print(f"n={N_TEST_PER_CONDITION} per condition, N_raw={N_RAW}, "
          f"calibrated aggregate threshold={agg_threshold*100:.3f}%\n")
    print(f"{'detector':<12} {'false alarm':>12} {'detection':>12}")
    print(f"{'aggregate':<12} {far_agg:>11.2%} {tpr_agg:>11.2%}")
    print(f"{'q-detect':<12} {far_mon:>11.2%} {tpr_mon:>11.2%}")
    print(f"\nWritten to {OUT_FILE}")


def phase_plot() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if not OUT_FILE.exists():
        print("Run 'test' first.", file=sys.stderr)
        sys.exit(1)
    data = json.loads(OUT_FILE.read_text())
    rows = data["rows"]

    honest = [r for r in rows if r["condition"] == "honest"]
    attack = [r for r in rows if r["condition"] == "z_bias"]

    # Mahalanobis D^2 is heavy-tailed here: a handful of attack runs land
    # on a near-singular covariance direction and blow up to ~1e9, which
    # would otherwise compress every other point onto the x-axis. A log
    # scale is the honest way to show a statistic like this -- it is not
    # hiding the outliers, it is the correct axis for a quantity that
    # spans many orders of magnitude. +1 keeps exact-zero honest points
    # (D^2 = 0 is possible when the recovered shape matches the
    # calibration mean exactly) representable on a log axis.
    EPS = 1.0

    fig, ax = plt.subplots(figsize=(7, 5.5), dpi=200)
    ax.scatter([r["aggregate"] * 100 for r in honest],
               [r["mahalanobis"] + EPS for r in honest],
               s=24, alpha=0.8, color="#178a58", label="Honest", zorder=3)
    ax.scatter([r["aggregate"] * 100 for r in attack],
               [r["mahalanobis"] + EPS for r in attack],
               s=24, alpha=0.8, color="#d5393e", label="Attacked (z-bias)", zorder=3)
    ax.set_yscale("log")

    honest_d2 = sorted(r["mahalanobis"] for r in honest if r["mahalanobis"] is not None)
    if honest_d2:
        line_y = honest_d2[int(0.99 * (len(honest_d2) - 1))] + EPS
        ax.axhline(line_y, ls="--", color="#666b87", lw=1.2, zorder=2)
        ax.text(ax.get_xlim()[0], line_y, "Detection threshold  ",
                va="bottom", ha="left", fontsize=9, color="#666b87")

    ax.set_xlabel("Aggregate Error Rate (%)")
    ax.set_ylabel("Q-DETECT Statistical Distance (Mahalanobis D², log scale)")
    ax.set_title("Same aggregate error rate.\nCompletely different statistical signature.",
                  fontsize=12, fontweight="bold")
    ax.legend(loc="upper right", frameon=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()

    out_path = RESULTS_DIR / "detection_separation_scatter.png"
    fig.savefig(out_path)
    print(f"Scatter plot written to {out_path}")


if __name__ == "__main__":
    phase = sys.argv[1] if len(sys.argv) > 1 else ""
    if phase == "calibrate":
        phase_calibrate()
    elif phase == "test":
        phase_test()
    elif phase == "plot":
        phase_plot()
    else:
        print(__doc__)
        sys.exit(1)
