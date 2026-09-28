#!/usr/bin/env python3
"""Q-METER dashboard. Run from the project root:

    python dashboard/app.py
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

import numpy as np
from flask import Flask, jsonify, request, send_from_directory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qmeter.attacks import ATTACKS
from qmeter.simulator import POOL, SimulationConfig, reset_session, run_pipeline

STATIC = Path(__file__).resolve().parent / "static"
RESULTS = ROOT / "experiments" / "results"

app = Flask(__name__, static_folder=str(STATIC), static_url_path="/static")


def json_safe(obj):
    """Browsers reject NaN / Infinity. Map those to null."""
    if isinstance(obj, dict):
        return {k: json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(v) for v in obj]
    if isinstance(obj, (np.floating, np.integer)):
        obj = obj.item()
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    return obj


@app.get("/")
def index():
    return send_from_directory(STATIC, "index.html")


@app.get("/api/meta")
def meta():
    return jsonify(
        {
            "attacks": {k: {"title": v.title, "mechanism": v.mechanism, "layer": v.layer} for k, v in ATTACKS.items()},
            "pool": {"generated": POOL.pairs_generated, "consumed": POOL.pairs_consumed, "remaining": POOL.remaining},
            "assumptions": [
                "Teleportation ≡ intended six-state qubit after the public Pauli correction is an assumption, not a theorem. No published reduction exists.",
                "Q-METER domain: Pauli-twirled effective channels. Twirling is an operation, not a free consequence of teleporting.",
                "Detection is decoupled from accept/reject. Weng's T_a / T_v own this signature; the monitor owns the next one.",
                "Q-METER is not information-theoretic security. Weng's protocol is, under its model.",
                "Adaptive eavesdroppers who randomize their basis erase the axis signature. This detector targets channel manipulation.",
            ],
            "citations": {
                "protocol": "Weng et al., Opt. Express 29, 27661 (2021), arXiv:2104.12059",
                "detector": "Abruzzo et al., arXiv:1111.2798 (2011)",
                "ep": "Yin, Fu, Chen, Phys. Rev. A 93, 032316 (2016) — the source Weng cites for e_p(e_b)",
            },
        }
    )


@app.post("/api/run")
def api_run():
    body = request.get_json(force=True, silent=True) or {}
    try:
        length_km = float(body.get("length_km", 0.0))
        if "force_click" in body:
            force_click = bool(body.get("force_click"))
        else:
            # Lab mode (0 km) keeps every pulse. A real fibre length must actually lose photons.
            force_click = length_km <= 0.0
        cfg = SimulationConfig(
            n_pulses=int(body.get("n_pulses", 12000)),
            seed=int(body.get("seed", 141)),
            attack=str(body.get("attack", "none")),
            intensity=float(body.get("intensity", 1.0)),
            length_km=length_km,
            message=int(body.get("message", 0)),
            force_click=force_click,
            operating_point=str(body.get("operating_point", "detector_demo")),
            key_id=str(body.get("key_id", f"live-{body.get('attack','none')}-{body.get('seed',141)}")),
        )
        result = run_pipeline(cfg)
        return jsonify(json_safe(result.public_dict()))
    except Exception as exc:
        return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 500


@app.post("/api/reset")
def api_reset():
    reset_session()
    return jsonify({"ok": True, "remaining": POOL.remaining})


@app.get("/api/experiments")
def experiments():
    idx = RESULTS / "index_seed141.json"
    if not idx.exists():
        return jsonify([])
    return jsonify(json.loads(idx.read_text()))


@app.get("/api/experiment/<name>")
def experiment(name: str):
    path = RESULTS / f"{name}_seed141.json"
    if not path.exists():
        return jsonify({"error": "missing; run generate_experiment.py"}), 404
    return jsonify(json.loads(path.read_text()))


def main() -> None:
    host = os.environ.get("QMETER_HOST", "127.0.0.1")
    port = int(os.environ.get("QMETER_PORT", "5055"))
    print(f"Q-METER dashboard  http://{host}:{port}")
    print("Stop: press Ctrl+C in this terminal.")
    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
