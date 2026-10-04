"""python -m qdetect  →  live pipeline CLI. Dashboard is dashboard/app.py."""

from __future__ import annotations

import argparse
import json

from qdetect.simulator import SimulationConfig, run_pipeline


def main() -> None:
    p = argparse.ArgumentParser(description="Q-DETECT live pipeline")
    p.add_argument("--attack", default="none")
    p.add_argument("--n", type=int, default=12000)
    p.add_argument("--seed", type=int, default=141)
    p.add_argument("--intensity", type=float, default=1.0)
    p.add_argument("--km", type=float, default=0.0)
    args = p.parse_args()
    cfg = SimulationConfig(
        n_pulses=args.n,
        seed=args.seed,
        attack=args.attack,
        intensity=args.intensity,
        length_km=args.km,
        force_click=args.km == 0.0,
    )
    print(json.dumps(run_pipeline(cfg).public_dict(), indent=2, default=str)[:4000])
    print("\nDashboard (from this folder):  python dashboard/app.py")


if __name__ == "__main__":
    main()
