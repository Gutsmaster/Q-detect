#!/usr/bin/env python3
"""Seeded experiment generator.

    python experiments/generate_experiment.py --seed 141 --condition all

Heavy conditions use N_raw = 200_000 (brief §3.8). Live dashboard uses a
scaled-down N; these files are the stable, regenerable evidence.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qmeter.contract import KeyPool
from qmeter.simulator import SimulationConfig, reset_session, run_pipeline

RESULTS = Path(__file__).resolve().parent / "results"

CONDITIONS = {
    "honest_nominal": dict(attack="none", intensity=1.0, n_pulses=200000),
    "honest_drift": dict(attack="honest_drift", intensity=1.0, n_pulses=200000),
    "adversarial": dict(attack="z_bias", intensity=1.0, n_pulses=200000),
    "severe_honest_degradation": dict(attack="shape_preserving", intensity=1.0, n_pulses=80000),
    "severe_manipulation": dict(attack="z_bias", intensity=1.0, n_pulses=80000),
    "nonunital": dict(attack="nonunital", intensity=1.0, n_pulses=80000),
    "forgery": dict(attack="forgery", intensity=1.0, n_pulses=40000),
    "correction_bits": dict(attack="correction_bits", intensity=1.0, n_pulses=40000),
    "live_honest": dict(attack="none", intensity=1.0, n_pulses=12000),
    "live_adversarial": dict(attack="z_bias", intensity=1.0, n_pulses=12000),
}


def run_one(name: str, seed: int) -> dict:
    kw = CONDITIONS[name]
    pool = KeyPool(pairs_generated=50_000_000)
    cfg = SimulationConfig(seed=seed, force_click=True, key_id=f"{name}-{seed}", **kw)
    result = run_pipeline(cfg, pool=pool)
    payload = result.public_dict()
    payload["condition"] = name
    payload["seed"] = seed
    return payload


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--seed", type=int, default=141)
    p.add_argument("--condition", default="all")
    args = p.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)
    names = list(CONDITIONS) if args.condition == "all" else [args.condition]
    index = []
    reset_session()
    for name in names:
        reset_session()  # fresh credentials / key pool per condition
        print(f"running {name} ...", flush=True)
        payload = run_one(name, args.seed)
        out = RESULTS / f"{name}_seed{args.seed}.json"
        out.write_text(json.dumps(payload, indent=2))
        print(
            f"  agg={payload['charlie_axis']['aggregate']:.4f}  "
            f"e={payload['charlie_axis']['e']}  "
            f"qds={payload['layers']['qds']}  "
            f"qmeter={payload['layers']['monitor']}  "
            f"contract={payload['layers']['contract']}  "
            f"{payload['elapsed_s']:.2f}s"
        )
        index.append({"condition": name, "file": out.name, **payload["centrepiece"], "elapsed_s": payload["elapsed_s"]})
    (RESULTS / f"index_seed{args.seed}.json").write_text(json.dumps(index, indent=2))
    print("wrote", RESULTS)


if __name__ == "__main__":
    main()
