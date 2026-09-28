"""Weng three-party QDS: keygen, estimate, sign, dual-threshold verify."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from qmeter.channel import PauliChannel, apply_amplitude_damping, apply_pauli_channel, honest_channel
from qmeter.constants import IDEAL_CONCLUSIVE_PROB, PC_ABORT_DEV
from qmeter.detector import AxisStats, certified_early_reject, matching_basis_errors
from qmeter.postmatching import post_match
from qmeter.sarg04 import alice_logic_bits, assign_sets, decode, mismatch_rate
from qmeter.teleport import teleport_and_measure


@dataclass
class PartyRecord:
    axis: np.ndarray
    sign: np.ndarray
    meas_axis: np.ndarray
    meas_sign: np.ndarray
    sets: np.ndarray
    alice_bits: np.ndarray
    conclusive: np.ndarray
    logic: np.ndarray
    test_mask: np.ndarray
    pairs_consumed: int


@dataclass
class VerifyResult:
    party: str
    e_cu: float
    n_cu: int
    n_mis: int
    p_c: float
    e_ct: float
    n_ct: int
    threshold: float
    accepted: bool
    early_reject: bool
    abort_p_c: bool


@dataclass
class SignatureOutcome:
    message: int
    bob: VerifyResult
    charlie: VerifyResult
    forwarded: bool
    accepted: bool  # both accepted
    alice_bits_u: np.ndarray
    bob_stats: AxisStats
    charlie_stats: AxisStats
    bob_rec: PartyRecord
    charlie_rec: PartyRecord
    n_dropped_match: int
    pairs_consumed: int
    one_time_key_id: str
    replayed: bool


def _prepare_sequence(n: int, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    axis = rng.integers(0, 3, size=n, dtype=np.int8)
    sign = rng.integers(0, 2, size=n, dtype=np.int8)
    return axis, sign


def distribute_to(
    axis: np.ndarray,
    sign: np.ndarray,
    channel: PauliChannel,
    rng: np.random.Generator,
    *,
    length_km: float,
    force_click: bool,
    tamper_correction: bool,
    tamper_fraction: float,
    nonunital_gamma: float | None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, int]:
    n = axis.shape[0]
    if nonunital_gamma is not None:
        meas_axis = rng.integers(0, 3, size=n, dtype=np.int8)
        meas_sign = apply_amplitude_damping(axis, sign, nonunital_gamma, meas_axis, rng)
        clicked = np.ones(n, dtype=bool)
        consumed = n
        return axis[clicked], sign[clicked], meas_axis[clicked], meas_sign[clicked], consumed

    _, _, pauli = apply_pauli_channel(axis, sign, channel, rng)
    rec = teleport_and_measure(
        axis,
        sign,
        rng=rng,
        pauli=pauli,
        length_km=length_km,
        tamper_correction=tamper_correction,
        tamper_fraction=tamper_fraction,
        force_click=force_click,
    )
    c = rec.clicked
    return rec.axis[c], rec.sign[c], rec.meas_axis[c], rec.meas_sign[c], rec.pairs_consumed


def encode_party(axis, sign, meas_axis, meas_sign, sets, test_fraction, rng) -> PartyRecord:
    a_bits = alice_logic_bits(axis, sign, sets)
    conclusive, logic = decode(meas_axis, meas_sign, sets)
    n = axis.shape[0]
    test_mask = np.zeros(n, dtype=bool)
    n_test = int(round(test_fraction * n))
    if n_test > 0:
        idx = rng.choice(n, size=n_test, replace=False)
        test_mask[idx] = True
    return PartyRecord(
        axis=axis,
        sign=sign,
        meas_axis=meas_axis,
        meas_sign=meas_sign,
        sets=sets,
        alice_bits=a_bits,
        conclusive=conclusive,
        logic=logic,
        test_mask=test_mask,
        pairs_consumed=n,
    )


def _verify(name: str, rec: PartyRecord, threshold: float, skip_early: bool = False) -> VerifyResult:
    untested = ~rec.test_mask
    cu = rec.conclusive & untested
    e_cu, n_mis, n_cu = mismatch_rate(rec.alice_bits, rec.logic, cu)
    ct = rec.conclusive & rec.test_mask
    e_ct, _, n_ct = mismatch_rate(rec.alice_bits, rec.logic, ct)
    n_all = rec.alice_bits.size
    p_c = float(rec.conclusive.mean()) if n_all else 0.0
    abort_pc = abs(p_c - IDEAL_CONCLUSIVE_PROB) > PC_ABORT_DEV
    # Early reject is for a partial scan: if n_mis already exceeds T * n_total
    # even if every remaining bit is correct. On a completed sample it coincides
    # with the ordinary threshold test; we still report it when that happens.
    early = False if skip_early else certified_early_reject(n_cu, n_mis, n_cu, threshold)
    accepted = (not abort_pc) and (n_cu > 0) and (e_cu == e_cu) and (e_cu <= threshold)
    return VerifyResult(
        party=name,
        e_cu=float(e_cu) if e_cu == e_cu else 1.0,
        n_cu=n_cu,
        n_mis=n_mis,
        p_c=p_c,
        e_ct=float(e_ct) if e_ct == e_ct else 1.0,
        n_ct=n_ct,
        threshold=threshold,
        accepted=accepted,
        early_reject=early,
        abort_p_c=abort_pc,
    )


def run_signature(
    *,
    rng: np.random.Generator,
    n_pulses: int,
    message: int,
    t_a: float,
    t_v: float,
    test_fraction: float = 0.3,
    bob_channel: PauliChannel | None = None,
    charlie_channel: PauliChannel | None = None,
    length_km: float = 0.0,
    force_click: bool = True,
    skip_postmatch: bool = False,
    tamper_bob_correction: bool = False,
    tamper_charlie_correction: bool = False,
    tamper_fraction: float = 1.0,
    forge: bool = False,
    nonunital_gamma: float | None = None,
    key_id: str = "k0",
) -> SignatureOutcome:
    if bob_channel is None:
        bob_channel = honest_channel()
    if charlie_channel is None:
        charlie_channel = honest_channel()

    # Independent sequences to Bob and Charlie (parallel distribution).
    b_axis, b_sign = _prepare_sequence(n_pulses, rng)
    c_axis, c_sign = _prepare_sequence(n_pulses, rng)

    b_ax, b_sg, b_ma, b_ms, b_cons = distribute_to(
        b_axis, b_sign, bob_channel, rng,
        length_km=length_km, force_click=force_click,
        tamper_correction=tamper_bob_correction, tamper_fraction=tamper_fraction,
        nonunital_gamma=nonunital_gamma,
    )
    c_ax, c_sg, c_ma, c_ms, c_cons = distribute_to(
        c_axis, c_sign, charlie_channel, rng,
        length_km=length_km, force_click=force_click,
        tamper_correction=tamper_charlie_correction, tamper_fraction=tamper_fraction,
        nonunital_gamma=nonunital_gamma,
    )

    if skip_postmatch:
        n = int(min(b_ax.size, c_ax.size))
        b_ax, b_sg, b_ma, b_ms = b_ax[:n], b_sg[:n], b_ma[:n], b_ms[:n]
        c_ax, c_sg, c_ma, c_ms = c_ax[:n], c_sg[:n], c_ma[:n], c_ms[:n]
        # Charlie keeps HIS own states — Alice did not reorder. Repudiation demo.
        axis, sign = b_ax, b_sg
        n_drop = 0
        # Charlie's prepared states stay unmatched; encode against Charlie's actual states
        # but Alice will announce Bob's encoding. That is the cheating: different material.
        sets_b = assign_sets(b_ax, b_sg, rng)
        sets_c = assign_sets(c_ax, c_sg, rng)
        # Alice publishes one string (Bob's). Charlie checks against his own encoding of
        # a different sequence — mismatch inflates.
        bob_rec = encode_party(b_ax, b_sg, b_ma, b_ms, sets_b, test_fraction, rng)
        charlie_rec = encode_party(c_ax, c_sg, c_ma, c_ms, sets_c, test_fraction, rng)
        # Force Alice's published bits onto Charlie's record so he compares against Bob's key
        charlie_rec.alice_bits = bob_rec.alice_bits.copy()
        if charlie_rec.alice_bits.size != bob_rec.alice_bits.size:
            pass
    else:
        matched = post_match(b_ax, b_sg, b_ma, b_ms, c_ax, c_sg, c_ma, c_ms)
        axis, sign = matched.axis, matched.sign
        sets = assign_sets(axis, sign, rng)
        bob_rec = encode_party(axis, sign, matched.bob_meas_axis, matched.bob_meas_sign, sets, test_fraction, rng)
        charlie_rec = encode_party(
            axis, sign, matched.charlie_meas_axis, matched.charlie_meas_sign, sets, test_fraction, rng
        )
        n_drop = matched.n_dropped

    if forge:
        # Bob authenticates the real signature, then forwards a guessed string.
        # Only Charlie's copy of K_A^u is replaced.
        u = ~charlie_rec.test_mask
        guess = rng.integers(0, 2, size=int(u.sum()), dtype=np.int8)
        charlie_rec.alice_bits = charlie_rec.alice_bits.copy()
        charlie_rec.alice_bits[u] = guess

    bob_v = _verify("Bob", bob_rec, t_a)
    forwarded = bob_v.accepted
    if forwarded:
        charlie_v = _verify("Charlie", charlie_rec, t_v)
    else:
        charlie_v = _verify("Charlie", charlie_rec, t_v)
        charlie_v = VerifyResult(
            party="Charlie",
            e_cu=charlie_v.e_cu,
            n_cu=charlie_v.n_cu,
            n_mis=charlie_v.n_mis,
            p_c=charlie_v.p_c,
            e_ct=charlie_v.e_ct,
            n_ct=charlie_v.n_ct,
            threshold=t_v,
            accepted=False,
            early_reject=False,
            abort_p_c=charlie_v.abort_p_c,
        )

    bob_stats = matching_basis_errors(bob_rec.axis, bob_rec.sign, bob_rec.meas_axis, bob_rec.meas_sign)
    charlie_stats = matching_basis_errors(
        charlie_rec.axis, charlie_rec.sign, charlie_rec.meas_axis, charlie_rec.meas_sign
    )

    return SignatureOutcome(
        message=int(message),
        bob=bob_v,
        charlie=charlie_v,
        forwarded=forwarded,
        accepted=bool(forwarded and charlie_v.accepted),
        alice_bits_u=bob_rec.alice_bits[~bob_rec.test_mask],
        bob_stats=bob_stats,
        charlie_stats=charlie_stats,
        bob_rec=bob_rec,
        charlie_rec=charlie_rec,
        n_dropped_match=n_drop,
        pairs_consumed=b_cons + c_cons,
        one_time_key_id=key_id,
        replayed=False,
    )
