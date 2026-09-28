from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qmeter.contract import KeyPool  # noqa: E402
from qmeter.simulator import SimulationConfig, run_pipeline  # noqa: E402


def test_honest_signature_accepts():
    from qmeter.simulator import reset_session

    reset_session()
    pool = KeyPool(pairs_generated=5_000_000)
    r = run_pipeline(
        SimulationConfig(n_pulses=8000, seed=141, attack="none", force_click=True),
        pool=pool,
    )
    d = r.public_dict()
    assert d["bob"]["accepted"], d["bob"]
    assert d["charlie"]["accepted"], d["charlie"]
    assert d["signature_accepted"]
    assert abs(d["charlie"]["p_c"] - 1 / 6) < 0.03
    assert d["monitor_charlie"]["label"] == "CONSISTENT"


def test_z_bias_accepts_but_not_certifiable():
    from qmeter.simulator import reset_session

    reset_session()
    pool = KeyPool(pairs_generated=5_000_000)
    r = run_pipeline(
        SimulationConfig(n_pulses=30000, seed=141, attack="z_bias", intensity=1.0, force_click=True),
        pool=pool,
    )
    d = r.public_dict()
    assert d["signature_accepted"] is True, d["charlie"]
    assert d["charlie_axis"]["aggregate"] < 0.12
    assert d["monitor_charlie"]["label"] == "VIOLATION", d["charlie_axis"]
    assert d["contract"]["label"] == "DEFER"


def test_forgery_charlie_rejects():
    from qmeter.simulator import reset_session

    reset_session()
    pool = KeyPool(pairs_generated=5_000_000)
    r = run_pipeline(
        SimulationConfig(n_pulses=8000, seed=2, attack="forgery", force_click=True),
        pool=pool,
    )
    d = r.public_dict()
    assert d["charlie"]["accepted"] is False or d["signature_accepted"] is False


def test_replay_caught():
    pool = KeyPool(pairs_generated=5_000_000)
    cfg = SimulationConfig(n_pulses=4000, seed=3, attack="none", key_id="same", force_click=True)
    r1 = run_pipeline(cfg, pool=pool)
    from qmeter import simulator as sim

    sim.USED_KEYS.add("same")
    r2 = run_pipeline(
        SimulationConfig(n_pulses=4000, seed=4, attack="replay", key_id="same", force_click=True),
        pool=pool,
    )
    assert r2.replay_caught
    assert r2.public_dict()["signature_accepted"] is False
    _ = r1
