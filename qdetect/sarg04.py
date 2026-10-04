"""Six-state SARG04 encoding, Weng et al. 2021 §II.

Twelve sets, axis-ordered:
  XY: first X (logic 0), second Y (logic 1)
  YZ: first Y, second Z
  ZX: first Z, second X

A state belongs to exactly four sets (Weng's |+x⟩ example).
Conclusive iff the measurement outcome is orthogonal to exactly one
state of the assigned set. Ideal P(conclusive) = 1/6.
"""

from __future__ import annotations

import numpy as np

from qdetect.constants import X, Y, Z

# Pair types: (axis0, axis1) with first = bit 0, second = bit 1
_PAIR_TYPES = ((X, Y), (Y, Z), (Z, X))


def assign_sets(axis: np.ndarray, sign: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """For each prepared state, pick one of the four containing sets uniformly.

    Returns an (N, 4) int8 array: (axis0, sign0, axis1, sign1).
    Alice's logic bit is 0 if (axis, sign) == (axis0, sign0), else 1.
    """
    axis = np.asarray(axis)
    sign = np.asarray(sign)
    n = axis.shape[0]
    choice = rng.integers(0, 4, size=n, dtype=np.int8)
    # choice 0,1: state is first of the pair type that starts with this axis
    #   other-axis sign = choice % 2, pair type identified by axis
    # choice 2,3: state is second of the pair type that ends with this axis
    a0 = np.empty(n, dtype=np.int8)
    s0 = np.empty(n, dtype=np.int8)
    a1 = np.empty(n, dtype=np.int8)
    s1 = np.empty(n, dtype=np.int8)

    as_first = choice < 2
    other_sign = choice % 2

    # as first: pair type starts with `axis`; other axis is (axis+1)%3
    a0[as_first] = axis[as_first]
    s0[as_first] = sign[as_first]
    a1[as_first] = (axis[as_first] + 1) % 3
    s1[as_first] = other_sign[as_first]

    # as second: pair type ends with `axis`; first axis is (axis+2)%3 = axis-1
    as_second = ~as_first
    a1[as_second] = axis[as_second]
    s1[as_second] = sign[as_second]
    a0[as_second] = (axis[as_second] + 2) % 3
    s0[as_second] = other_sign[as_second]

    return np.stack([a0, s0, a1, s1], axis=1)


def alice_logic_bits(axis: np.ndarray, sign: np.ndarray, sets: np.ndarray) -> np.ndarray:
    """Alice's SARG04 logic bit: 0 if she sent the first state of the set."""
    sent_first = (axis == sets[:, 0]) & (sign == sets[:, 1])
    return np.where(sent_first, 0, 1).astype(np.int8)


def decode(
    meas_axis: np.ndarray,
    meas_sign: np.ndarray,
    sets: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """SARG04 decode.

    Returns (conclusive, logic_bit). logic_bit is 0/1 only where conclusive;
    -1 elsewhere.

    Sentinel is -1, not 0xFF: np.full(..., 0xFF, dtype=np.int8) raises
    OverflowError on NumPy >= 2.0, since 255 does not fit in a signed
    int8's range (-128..127). -1 fits and bit-for-bit is the same pattern
    for an int8 anyway, so nothing downstream that compares against it
    changes behaviour.
    """
    meas_axis = np.asarray(meas_axis)
    meas_sign = np.asarray(meas_sign)
    a0, s0, a1, s1 = sets[:, 0], sets[:, 1], sets[:, 2], sets[:, 3]
    ortho_first = (meas_axis == a0) & (meas_sign != s0)
    ortho_second = (meas_axis == a1) & (meas_sign != s1)
    # Orthogonal to both cannot happen for a Pauli eigenstate vs two
    # different-axis states, but guard anyway.
    conclusive = ortho_first ^ ortho_second
    logic = np.full(meas_axis.shape[0], -1, dtype=np.int8)
    logic[ortho_first] = 1  # orthogonal to first ⇒ must have been second
    logic[ortho_second] = 0
    return conclusive, logic


def mismatch_rate(alice_bits: np.ndarray, recv_bits: np.ndarray, conclusive: np.ndarray) -> tuple[float, int, int]:
    """Mismatch rate of conclusive results. Returns (rate, n_mismatch, n_conclusive)."""
    n_c = int(conclusive.sum())
    if n_c == 0:
        return float("nan"), 0, 0
    n_mis = int(np.sum(conclusive & (alice_bits != recv_bits)))
    return n_mis / n_c, n_mis, n_c
