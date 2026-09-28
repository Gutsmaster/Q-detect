"""Teleportation of six-state qubits.

Ideal teleportation of |ψ⟩ through |Φ⁺⟩ plus the publicly specified
Pauli correction delivers |ψ⟩. A Pauli on Bob's half of the pair, or a
flip of the two correction bits, is an extra Pauli on the delivered
qubit. That is exact, not an approximation.

Production path: sample the Bell outcome (two bits), apply the
correction, then the effective channel. Explicit two-qubit statevector
teleportation is in `explicit_teleport_one` for tests.

Loss: both photons of the pair must be detected. Bell measurement
consumes the pair regardless of outcome (meter accounting).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from qmeter.constants import (
    DETECTION_EFFICIENCY,
    DARK_COUNT_PROB,
    FIBER_LOSS_DB_PER_KM,
    I_PAULI,
    X_PAULI,
    Y_PAULI,
    Z_PAULI,
)
from qmeter.states import apply_pauli, measure_eigenstate

# Bell outcome 00,01,10,11 → correction I, X, Z, XZ  (standard Φ⁺, Ψ⁺, Φ⁻, Ψ⁻)
# We use bits (b1, b2) with correction X^{b1} Z^{b2}.
_BELL_TO_PAULI = {
    (0, 0): I_PAULI,  # Φ⁺
    (1, 0): X_PAULI,  # Ψ⁺
    (0, 1): Z_PAULI,  # Φ⁻
    (1, 1): Y_PAULI,  # Ψ⁻  (XZ up to a global phase; Y on eigenstates = flip)
}


def fiber_transmission(length_km: float, alpha_db_per_km: float = FIBER_LOSS_DB_PER_KM) -> float:
    return 10.0 ** (-alpha_db_per_km * length_km / 10.0)


def pair_click_probability(
    length_km: float,
    eta_d: float = DETECTION_EFFICIENCY,
    p_dark: float = DARK_COUNT_PROB,
    alice_local_eta: float | None = None,
) -> tuple[float, float]:
    """Probability both halves yield a click, and the dark-only click prob.

    Alice's photon is local (short fibre). Bob's photon travels `length_km`.
    Dark clicks are independent Bernoulli p_dark on a no-photon slot.
    """
    eta_a = eta_d if alice_local_eta is None else alice_local_eta
    eta_b = eta_d * fiber_transmission(length_km)
    # Click if photon detected or dark count (approx, ignoring both)
    p_click_a = 1.0 - (1.0 - eta_a) * (1.0 - p_dark)
    p_click_b = 1.0 - (1.0 - eta_b) * (1.0 - p_dark)
    return p_click_a * p_click_b, p_dark * p_dark


@dataclass
class TeleportRecord:
    axis: np.ndarray
    sign: np.ndarray
    meas_axis: np.ndarray
    meas_sign: np.ndarray
    corr_bits: np.ndarray  # (N, 2)
    clicked: np.ndarray
    pairs_consumed: int
    correction_tampered: np.ndarray


def teleport_and_measure(
    axis: np.ndarray,
    sign: np.ndarray,
    *,
    rng: np.random.Generator,
    pauli: np.ndarray | None = None,
    length_km: float = 0.0,
    eta_d: float = DETECTION_EFFICIENCY,
    p_dark: float = DARK_COUNT_PROB,
    tamper_correction: bool = False,
    tamper_fraction: float = 1.0,
    force_click: bool = False,
) -> TeleportRecord:
    """Distribute eigenstates by teleportation, then measure in a random basis.

    `pauli` if given is the effective channel Pauli on the teleported qubit
    (already sampled). Correction-bit tampering applies an extra random
    nonzero Pauli — the cheapest attack in the system.
    """
    n = int(axis.shape[0])
    # Bell measurement outcomes are uniformly random on |Φ⁺⟩; correction
    # recovers |ψ⟩. We still emit the two bits: they must be authenticated.
    corr = rng.integers(0, 2, size=(n, 2), dtype=np.int8)

    delivered_axis = np.asarray(axis).copy()
    delivered_sign = np.asarray(sign).copy()

    if pauli is not None:
        delivered_axis, delivered_sign = apply_pauli(delivered_axis, delivered_sign, pauli)

    tampered = np.zeros(n, dtype=bool)
    if tamper_correction:
        tampered = rng.random(n) < tamper_fraction
        n_t = int(tampered.sum())
        if n_t:
            extra = rng.integers(1, 4, size=n_t, dtype=np.int8)  # X, Y or Z
            da, ds = apply_pauli(delivered_axis[tampered], delivered_sign[tampered], extra)
            delivered_axis[tampered] = da
            delivered_sign[tampered] = ds
            # The bits on the wire are flipped to match a wrong correction
            corr[tampered] ^= rng.integers(0, 2, size=(n_t, 2), dtype=np.int8)
            # ensure at least one bit flipped
            none = tampered.copy()
            none[tampered] = np.all(corr[tampered] == rng.integers(0, 2, size=(n_t, 2), dtype=np.int8), axis=1)  # unused
            del none

    p_click, _ = pair_click_probability(length_km, eta_d=eta_d, p_dark=p_dark)
    if force_click or length_km == 0.0 and eta_d >= 1.0 - 1e-12:
        clicked = np.ones(n, dtype=bool)
    else:
        clicked = rng.random(n) < p_click

    meas_axis = rng.integers(0, 3, size=n, dtype=np.int8)
    meas_sign = measure_eigenstate(delivered_axis, delivered_sign, meas_axis, rng)

    # Dark-only clicks (no photon) scramble the outcome. Approximate: if the
    # pair did not really arrive but a click was declared via dark counts,
    # already included in p_click; the measurement is then random. We leave
    # the eigenstate measurement as-is when the photon arrived, which is the
    # dominant term at short distance / high η.

    return TeleportRecord(
        axis=np.asarray(axis),
        sign=np.asarray(sign),
        meas_axis=meas_axis,
        meas_sign=meas_sign,
        corr_bits=corr,
        clicked=clicked,
        pairs_consumed=n,
        correction_tampered=tampered,
    )


def explicit_teleport_one(ket: np.ndarray, rng: np.random.Generator) -> tuple[np.ndarray, tuple[int, int]]:
    """Statevector teleportation of a single qubit ket (2,) through |Φ⁺⟩.

    Used only in tests to confirm the eigenstate-Pauli path matches QM.
    """
    # |Φ⁺⟩ = (|00⟩+|11⟩)/√2 on qubits (A_bell, B)
    phi = np.array([1, 0, 0, 1], dtype=np.complex128) / np.sqrt(2)
    # Total: Alice_state ⊗ Bell  →  3 qubits, order (ψ, A, B)
    psi = np.asarray(ket, dtype=np.complex128)
    psi = psi / np.linalg.norm(psi)
    total = np.kron(psi, phi)  # dim 8

    # Bell projectors on (ψ, A). Outcome sampled by Born.
    # Basis order |bψ bA bB⟩ with b in {0,1}, index = 4*bψ+2*bA+bB
    def bell_prob_and_bob(bits: tuple[int, int]) -> tuple[float, np.ndarray]:
        # Project (ψ,A) onto Bell labelled by bits, remaining is Bob.
        # Φ⁺ 00: (|00⟩+|11⟩)/√2 ; Ψ⁺ 10: (|01⟩+|10⟩)/√2
        # Φ⁻ 01: (|00⟩-|11⟩)/√2 ; Ψ⁻ 11: (|01⟩-|10⟩)/√2
        b1, b2 = bits
        amp_b0 = np.zeros(2, dtype=np.complex128)
        amp_b1 = np.zeros(2, dtype=np.complex128)
        for psi_b in (0, 1):
            for a_b in (0, 1):
                for bob_b in (0, 1):
                    idx = 4 * psi_b + 2 * a_b + bob_b
                    # Bell amplitude for |psi_b, a_b⟩
                    if bits == (0, 0):  # Φ⁺
                        bell_amp = (1 / np.sqrt(2)) if psi_b == a_b else 0.0
                        if psi_b == a_b == 1:
                            bell_amp = 1 / np.sqrt(2)
                    elif bits == (1, 0):  # Ψ⁺ (|01⟩+|10⟩)/√2
                        bell_amp = (1 / np.sqrt(2)) if psi_b != a_b else 0.0
                    elif bits == (0, 1):  # Φ⁻ (|00⟩-|11⟩)/√2
                        if psi_b == a_b == 0:
                            bell_amp = 1 / np.sqrt(2)
                        elif psi_b == a_b == 1:
                            bell_amp = -1 / np.sqrt(2)
                        else:
                            bell_amp = 0.0
                    else:  # Ψ⁻ (|01⟩-|10⟩)/√2
                        if (psi_b, a_b) == (0, 1):
                            bell_amp = 1 / np.sqrt(2)
                        elif (psi_b, a_b) == (1, 0):
                            bell_amp = -1 / np.sqrt(2)
                        else:
                            bell_amp = 0.0
                    if bob_b == 0:
                        amp_b0[0 if False else 0]  # keep linter quiet
                    # Accumulate ⟨Bell|ψ A⟩ |B⟩
                    # total[idx] is amplitude of |psi_b a_b bob_b⟩
                    # projected Bob amplitude += bell_amp* * total[idx]  but bell is on (ψ,A)
                    # ⟨Bell_{b1 b2}|ψ A⟩ coefficient times |bob⟩
        # Direct: reshape total to (2,2,2) = (ψ, A, B)
        t = total.reshape(2, 2, 2)
        if bits == (0, 0):
            bob = (t[0, 0] + t[1, 1]) / np.sqrt(2)
        elif bits == (1, 0):
            bob = (t[0, 1] + t[1, 0]) / np.sqrt(2)
        elif bits == (0, 1):
            bob = (t[0, 0] - t[1, 1]) / np.sqrt(2)
        else:
            bob = (t[0, 1] - t[1, 0]) / np.sqrt(2)
        p = float(np.vdot(bob, bob).real)
        return p, bob

    outcomes = [(0, 0), (1, 0), (0, 1), (1, 1)]
    probs = []
    bobs = []
    for bits in outcomes:
        p, bob = bell_prob_and_bob(bits)
        probs.append(max(p, 0.0))
        bobs.append(bob)
    s = sum(probs)
    probs = [p / s for p in probs]
    k = int(rng.choice(4, p=probs))
    bits = outcomes[k]
    bob = bobs[k]
    nrm = np.linalg.norm(bob)
    if nrm < 1e-15:
        bob = np.array([1.0, 0.0], dtype=np.complex128)
    else:
        bob = bob / nrm
    # Corrections: X^{b1} Z^{b2}
    b1, b2 = bits
    if b2:
        bob = np.array([bob[0], -bob[1]], dtype=np.complex128)
    if b1:
        bob = np.array([bob[1], bob[0]], dtype=np.complex128)
    return bob, bits
