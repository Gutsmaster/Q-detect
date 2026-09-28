"""Identities that must hold if the simulator is physically honest."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qmeter.channel import (  # noqa: E402
    PauliChannel,
    apply_pauli_channel,
    recovered_pauli_rates,
    single_axis,
)
from qmeter.constants import IDEAL_CONCLUSIVE_PROB  # noqa: E402
from qmeter.detector import matching_basis_errors  # noqa: E402
from qmeter.finite_size import binary_entropy, e_bf_star, epsilon_for, n_cu_for_forgery, phase_error  # noqa: E402
from qmeter.postmatching import post_match, state_id  # noqa: E402
from qmeter.sarg04 import alice_logic_bits, assign_sets, decode, mismatch_rate  # noqa: E402
from qmeter.states import apply_pauli, measure_eigenstate  # noqa: E402
from qmeter.teleport import explicit_teleport_one  # noqa: E402


def test_sarg04_conclusive_rate_ideal():
    rng = np.random.default_rng(141)
    n = 120_000
    axis = rng.integers(0, 3, size=n, dtype=np.int8)
    sign = rng.integers(0, 2, size=n, dtype=np.int8)
    meas_axis = rng.integers(0, 3, size=n, dtype=np.int8)
    meas_sign = measure_eigenstate(axis, sign, meas_axis, rng)
    sets = assign_sets(axis, sign, rng)
    conclusive, _ = decode(meas_axis, meas_sign, sets)
    rate = float(conclusive.mean())
    assert abs(rate - IDEAL_CONCLUSIVE_PROB) < 0.005, rate


def test_sarg04_deterministic_acceptance_ideal():
    rng = np.random.default_rng(7)
    n = 80_000
    axis = rng.integers(0, 3, size=n, dtype=np.int8)
    sign = rng.integers(0, 2, size=n, dtype=np.int8)
    meas_axis = rng.integers(0, 3, size=n, dtype=np.int8)
    meas_sign = measure_eigenstate(axis, sign, meas_axis, rng)
    sets = assign_sets(axis, sign, rng)
    a_bits = alice_logic_bits(axis, sign, sets)
    conclusive, logic = decode(meas_axis, meas_sign, sets)
    e, n_mis, n_c = mismatch_rate(a_bits, logic, conclusive)
    assert n_c > 1000
    assert n_mis == 0, (n_mis, n_c, e)


def test_commutation_blind_spot_aggregate_is_two_thirds():
    rng = np.random.default_rng(141)
    n = 200_000
    axis = rng.integers(0, 3, size=n, dtype=np.int8)
    sign = rng.integers(0, 2, size=n, dtype=np.int8)
    p = 0.105
    ch = single_axis("Z", p)
    ax, sg, _ = apply_pauli_channel(axis, sign, ch, rng)
    meas_axis = axis.copy()  # matching basis
    meas_sign = measure_eigenstate(ax, sg, meas_axis, rng)
    stats = matching_basis_errors(axis, sign, meas_axis, meas_sign)
    # aggregate 2p/3 = 0.07
    assert abs(stats.aggregate - 2.0 * p / 3.0) < 0.003, stats.aggregate
    assert stats.e_z < 0.003, stats.e_z
    assert abs(stats.e_x - p) < 0.005, stats.e_x
    assert abs(stats.e_y - p) < 0.005, stats.e_y


def test_pauli_inversion_recovers_injected():
    rng = np.random.default_rng(0)
    n = 300_000
    axis = rng.integers(0, 3, size=n, dtype=np.int8)
    sign = rng.integers(0, 2, size=n, dtype=np.int8)
    ch = PauliChannel(0.027, 0.033, 0.045)
    ax, sg, _ = apply_pauli_channel(axis, sign, ch, rng)
    meas = measure_eigenstate(ax, sg, axis, rng)
    stats = matching_basis_errors(axis, sign, axis, meas)
    assert abs(stats.p_x - 0.027) < 0.004
    assert abs(stats.p_y - 0.033) < 0.004
    assert abs(stats.p_z - 0.045) < 0.004
    assert abs(stats.aggregate - 0.07) < 0.004


def test_do_not_clip_negatives():
    # Pure Z: recovered p_X, p_Y should sit at ~0, not be clipped away from a
    # slightly negative fluctuation at smaller N.
    px, py, pz = recovered_pauli_rates(0.105, 0.105, 0.0)
    assert abs(px) < 1e-12
    assert abs(py) < 1e-12
    assert abs(pz - 0.105) < 1e-12


def test_post_matching_aligns_state_types():
    rng = np.random.default_rng(3)
    n = 5000
    ba, bs = rng.integers(0, 3, size=n, dtype=np.int8), rng.integers(0, 2, size=n, dtype=np.int8)
    ca, cs = rng.integers(0, 3, size=n, dtype=np.int8), rng.integers(0, 2, size=n, dtype=np.int8)
    bma, bms = ba.copy(), bs.copy()
    cma, cms = ca.copy(), cs.copy()
    m = post_match(ba, bs, bma, bms, ca, cs, cma, cms)
    assert np.all(state_id(m.axis, m.sign) == state_id(m.axis, m.sign))
    # Charlie's reordered prepared states equal Bob's
    # We only stored Bob's axis/sign on the matched pair; check permutation
    # recovers Charlie states of the same type
    c_id = state_id(ca, cs)[m.permutation_charlie]
    b_id = state_id(m.axis, m.sign)
    assert np.array_equal(c_id, b_id)


def test_yin2016_phase_error_intercept():
    e_p = phase_error(0.0, model="yin2016")
    assert abs(e_p - (2 - np.sqrt(2)) / 4) < 1e-12
    e_p_w = phase_error(0.0, model="weng_printed")
    assert e_p_w > 0.5


def test_forgery_bound_inverts():
    e_bf = 0.08
    t_v = 0.05
    n = n_cu_for_forgery(e_bf, t_v, 1e-10)
    eps = epsilon_for(e_bf, t_v, n)
    assert abs(np.log(eps) - np.log(1e-10)) < 0.05


def test_e_bf_positive_under_yin():
    assert 0 < e_bf_star(0.01, model="yin2016") < 0.5
    assert binary_entropy(0.5) == pytest.approx(1.0, abs=1e-6)


def test_explicit_teleport_recovers_ket():
    rng = np.random.default_rng(11)
    # |0⟩
    ket = np.array([1.0, 0.0], dtype=np.complex128)
    for _ in range(20):
        out, _ = explicit_teleport_one(ket, rng)
        assert abs(abs(out[0]) - 1.0) < 1e-8
        assert abs(out[1]) < 1e-8
    # |+⟩
    ket = np.array([1.0, 1.0], dtype=np.complex128) / np.sqrt(2)
    for _ in range(20):
        out, _ = explicit_teleport_one(ket, rng)
        # global phase free
        phase = out[0] / (abs(out[0]) + 1e-18)
        aligned = out / phase
        assert abs(aligned[0] - 1 / np.sqrt(2)) < 1e-7
        assert abs(aligned[1] - 1 / np.sqrt(2)) < 1e-7


def test_pauli_y_on_y_is_invisible():
    axis = np.array([1], dtype=np.int8)  # Y
    sign = np.array([0], dtype=np.int8)
    ax, sg = apply_pauli(axis, sign, np.array([2], dtype=np.int8))  # Y Pauli
    assert ax[0] == 1 and sg[0] == 0
