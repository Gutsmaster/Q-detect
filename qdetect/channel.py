"""Effective channels on teleported six-state qubits.

Pauli-twirled channels are the detector's declared domain. A Pauli
channel on an eigenstate either is invisible (commutes) or flips the
eigenvalue (anticommutes). Loss is an erasure, not a qubit channel —
do not call amplitude damping "fibre photon loss".
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from qdetect.constants import HONEST_P, I_PAULI, X_PAULI, Y_PAULI, Z_PAULI
from qdetect.states import apply_pauli, bloch_from_eigenstate, measure_from_bloch


@dataclass(frozen=True)
class PauliChannel:
    """p = (p_X, p_Y, p_Z); p_I = 1 - sum."""

    p_x: float
    p_y: float
    p_z: float

    def probs(self) -> np.ndarray:
        s = self.p_x + self.p_y + self.p_z
        if s < 0 or s > 1 + 1e-12:
            raise ValueError(f"Pauli probabilities sum to {s}, not in [0, 1]")
        p_i = max(0.0, 1.0 - s)
        return np.array([p_i, self.p_x, self.p_y, self.p_z], dtype=np.float64)

    @property
    def aggregate_error(self) -> float:
        """Observed matching-basis error: each Pauli is invisible on 1/3 of axes."""
        return (2.0 / 3.0) * (self.p_x + self.p_y + self.p_z)

    def sample(self, n: int, rng: np.random.Generator) -> np.ndarray:
        return rng.choice(4, size=n, p=self.probs()).astype(np.int8)


def honest_channel() -> PauliChannel:
    return PauliChannel(*HONEST_P)


def isotropic(p_each: float) -> PauliChannel:
    return PauliChannel(p_each, p_each, p_each)


def single_axis(axis: str, p: float) -> PauliChannel:
    axis = axis.upper()
    if axis == "X":
        return PauliChannel(p, 0.0, 0.0)
    if axis == "Y":
        return PauliChannel(0.0, p, 0.0)
    if axis == "Z":
        return PauliChannel(0.0, 0.0, p)
    raise ValueError(axis)


def mix_toward_single_axis(honest: PauliChannel, axis: str, beta: float) -> PauliChannel:
    """Shape interpolation. β=0 honest, β=1 pure single-axis of the same total magnitude.

    Brief §3.8 definition of attack bias β.
    """
    mag = honest.p_x + honest.p_y + honest.p_z
    pure = single_axis(axis, mag)
    b = float(np.clip(beta, 0.0, 1.0))
    return PauliChannel(
        (1 - b) * honest.p_x + b * pure.p_x,
        (1 - b) * honest.p_y + b * pure.p_y,
        (1 - b) * honest.p_z + b * pure.p_z,
    )


def scale_magnitude(ch: PauliChannel, factor: float) -> PauliChannel:
    """Shape-preserving magnitude scale (brief §3.8 complementary test)."""
    return PauliChannel(ch.p_x * factor, ch.p_y * factor, ch.p_z * factor)


def apply_pauli_channel(
    axis: np.ndarray,
    sign: np.ndarray,
    channel: PauliChannel,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Returns (axis, sign, pauli_applied)."""
    pauli = channel.sample(axis.shape[0], rng)
    axis_out, sign_out = apply_pauli(axis, sign, pauli)
    return axis_out, sign_out, pauli


def apply_amplitude_damping(
    axis: np.ndarray,
    sign: np.ndarray,
    gamma: float,
    meas_axis: np.ndarray,
    rng: np.random.Generator,
) -> np.ndarray:
    """Non-unital relaxation. Returns measurement signs. Breaks Pauli inversion.

    Kraus: K0 = diag(1, sqrt(1-γ)), K1 = [[0, sqrt(γ)], [0, 0]].
    Photon loss is an erasure, not this map — named correctly on purpose.
    """
    r = bloch_from_eigenstate(axis, sign)  # (N, 3) as (x, y, z)
    g = float(gamma)
    sg = np.sqrt(max(0.0, 1.0 - g))
    # Bloch of amplitude damping: x' = x √(1-γ), y' = y √(1-γ), z' = γ + z(1-γ)
    r2 = np.empty_like(r)
    r2[:, 0] = r[:, 0] * sg
    r2[:, 1] = r[:, 1] * sg
    r2[:, 2] = g + r[:, 2] * (1.0 - g)
    return measure_from_bloch(r2, meas_axis, rng)


def recovered_pauli_rates(e_x: float, e_y: float, e_z: float) -> tuple[float, float, float]:
    """Closed-form inversion. Negative values are correct behaviour; do not clip."""
    p_x = (e_y + e_z - e_x) / 2.0
    p_y = (e_x + e_z - e_y) / 2.0
    p_z = (e_x + e_y - e_z) / 2.0
    return p_x, p_y, p_z
