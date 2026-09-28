"""Six Pauli eigenstates and Pauli action on them.

A qubit is stored as (axis, sign) with axis in {0,1,2} = {X,Y,Z}
and sign in {0,1} = {+1, -1} eigenvalue. Every six-state qubit is an
eigenstate of exactly one Pauli, so a Pauli channel acts by:

- I, or the Pauli equal to the prepared axis: state unchanged (commutes)
- any other Pauli: eigenvalue flips, axis unchanged (anticommutes)

That is the commutation blind spot of §3.1 of the brief, and it is
exact for this state set.
"""

from __future__ import annotations

import numpy as np

from qmeter.constants import I_PAULI, X, Y, Z, X_PAULI, Y_PAULI, Z_PAULI

# Map Pauli index {I,X,Y,Z} = {0,1,2,3} onto axis {X,Y,Z} = {0,1,2} or None
_PAULI_TO_AXIS = {I_PAULI: None, X_PAULI: X, Y_PAULI: Y, Z_PAULI: Z}


def apply_pauli(axis: np.ndarray, sign: np.ndarray, pauli: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Apply a Pauli (0=I,1=X,2=Y,3=Z) to eigenstates. Vectorized."""
    axis = np.asarray(axis)
    sign = np.asarray(sign).copy()
    pauli = np.asarray(pauli)
    paxis = np.empty_like(pauli)
    paxis[pauli == I_PAULI] = -1
    paxis[pauli == X_PAULI] = X
    paxis[pauli == Y_PAULI] = Y
    paxis[pauli == Z_PAULI] = Z
    flip = (paxis >= 0) & (paxis != axis)
    sign[flip] ^= 1
    return axis, sign


def bloch_from_eigenstate(axis: np.ndarray, sign: np.ndarray) -> np.ndarray:
    """Return (N, 3) Bloch vectors for ±1 eigenstates of X/Y/Z."""
    axis = np.asarray(axis)
    sign = np.asarray(sign)
    r = np.zeros((axis.shape[0], 3), dtype=np.float64)
    val = 1.0 - 2.0 * sign.astype(np.float64)  # +1 or -1
    r[np.arange(axis.shape[0]), axis] = val
    return r


def measure_from_bloch(bloch: np.ndarray, meas_axis: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Projective measurement of a (possibly mixed, via Bloch) qubit.

    P(outcome = +1 along meas_axis) = (1 + r · n) / 2.
    Returns sign in {0,1}.
    """
    n = bloch.shape[0]
    r_along = bloch[np.arange(n), meas_axis]
    p_plus = 0.5 * (1.0 + np.clip(r_along, -1.0, 1.0))
    plus = rng.random(n) < p_plus
    return np.where(plus, 0, 1).astype(np.int8)


def measure_eigenstate(
    axis: np.ndarray,
    sign: np.ndarray,
    meas_axis: np.ndarray,
    rng: np.random.Generator,
) -> np.ndarray:
    """Projective measurement of a Pauli eigenstate in X, Y or Z.

    Matching basis: deterministic eigenvalue.
    Other basis: uniformly random (Pauli eigenstates of different axes).
    """
    axis = np.asarray(axis)
    sign = np.asarray(sign)
    meas_axis = np.asarray(meas_axis)
    n = axis.shape[0]
    out = np.empty(n, dtype=np.int8)
    match = axis == meas_axis
    out[match] = sign[match]
    n_mis = int((~match).sum())
    if n_mis:
        out[~match] = rng.integers(0, 2, size=n_mis, dtype=np.int8)
    return out
