"""Attack library: pluggable perturbation modules with tunable intensity.

Each attack is a distinct mechanism, not a relabelled copy of another.
"""

from __future__ import annotations

from dataclasses import dataclass

from qmeter.channel import PauliChannel, honest_channel, mix_toward_single_axis, scale_magnitude, single_axis


@dataclass
class AttackSpec:
    name: str
    title: str
    mechanism: str
    layer: str  # distribution / classical / credential / key-tracking


ATTACKS: dict[str, AttackSpec] = {
    "none": AttackSpec("none", "Honest", "Calibrated anisotropic fibre", "none"),
    "honest_drift": AttackSpec(
        "honest_drift",
        "Honest drift",
        "Same aggregate error, shape still in the calibrated family",
        "distribution",
    ),
    "z_bias": AttackSpec(
        "z_bias",
        "Axis-biased channel (Z)",
        "Pure-Z Pauli of the same aggregate 7%. Invisible on Z-prepared elements; aggregate 2p/3.",
        "distribution",
    ),
    "x_bias": AttackSpec("x_bias", "Axis-biased channel (X)", "Pure-X Pauli, matched aggregate.", "distribution"),
    "y_bias": AttackSpec("y_bias", "Axis-biased channel (Y)", "Pure-Y Pauli, matched aggregate.", "distribution"),
    "shape_preserving": AttackSpec(
        "shape_preserving",
        "Shape-preserving magnitude scale",
        "Honest direction, larger magnitude. Aggregate detector can beat Q-METER here.",
        "distribution",
    ),
    "nonunital": AttackSpec(
        "nonunital",
        "Non-unital relaxation",
        "Amplitude damping. Pauli inversion is not valid; negatives are the honest failure.",
        "distribution",
    ),
    "correction_bits": AttackSpec(
        "correction_bits",
        "Correction-bit tampering",
        "Flip the two classical teleportation bits. Recipient applies the wrong Pauli. Quantum measurements look ordinary if the MAC is off.",
        "classical",
    ),
    "forgery": AttackSpec(
        "forgery",
        "Forgery",
        "Bob replaces Alice's untested key with a guess and forwards it to Charlie.",
        "classical",
    ),
    "replay": AttackSpec(
        "replay",
        "Replay",
        "Reuse a consumed one-time key. Caught by key-tracking, not by QBER.",
        "key-tracking",
    ),
    "impersonation": AttackSpec(
        "impersonation",
        "Impersonation",
        "A party who is not Alice offers a signature. No distribution-chain credential.",
        "credential",
    ),
    "unauthorized": AttackSpec(
        "unauthorized",
        "Unauthorized verification",
        "Verifier was never issued key material.",
        "credential",
    ),
    "repudiation": AttackSpec(
        "repudiation",
        "Alice repudiation (skip post-matching)",
        "Alice gives Bob good material and Charlie different material, then denies the signature. Post-matching is the countermeasure.",
        "distribution",
    ),
    "greedy": AttackSpec(
        "greedy",
        "Invited-but-greedy verifier",
        "Charlie was invited but exceeds his verification quota.",
        "credential",
    ),
}


def channels_for(attack: str, intensity: float = 1.0) -> tuple[PauliChannel, PauliChannel, dict]:
    """Return (bob_channel, charlie_channel, flags)."""
    h = honest_channel()
    mag = h.p_x + h.p_y + h.p_z
    flags: dict = {
        "skip_postmatch": False,
        "tamper_correction": False,
        "forge": False,
        "replay": False,
        "impersonation": False,
        "unauthorized": False,
        "greedy": False,
        "nonunital_gamma": None,
        "scale": intensity,
    }
    if attack in ("none", "honest_drift"):
        if attack == "honest_drift":
            # small shape wobble, same total magnitude
            drift = PauliChannel(0.030, 0.032, 0.043)
            return drift, drift, flags
        return h, h, flags
    if attack == "z_bias":
        ch = mix_toward_single_axis(h, "Z", float(intensity))
        return ch, ch, flags
    if attack == "x_bias":
        ch = mix_toward_single_axis(h, "X", float(intensity))
        return ch, ch, flags
    if attack == "y_bias":
        ch = mix_toward_single_axis(h, "Y", float(intensity))
        return ch, ch, flags
    if attack == "shape_preserving":
        # intensity=1 → aggregate ≈ 12% (brief severe-honest row)
        ch = scale_magnitude(h, 1.0 + 0.71 * float(intensity))
        return ch, ch, flags
    if attack == "nonunital":
        flags["nonunital_gamma"] = 0.12 * float(intensity)
        return h, h, flags
    if attack == "correction_bits":
        flags["tamper_correction"] = True
        return h, h, flags
    if attack == "forgery":
        flags["forge"] = True
        return h, h, flags
    if attack == "replay":
        flags["replay"] = True
        return h, h, flags
    if attack == "impersonation":
        flags["impersonation"] = True
        return h, h, flags
    if attack == "unauthorized":
        flags["unauthorized"] = True
        return h, h, flags
    if attack == "greedy":
        flags["greedy"] = True
        return h, h, flags
    if attack == "repudiation":
        flags["skip_postmatch"] = True
        # Charlie's channel worse
        bad = scale_magnitude(h, 2.5)
        return h, bad, flags
    if attack == "pure_z_matched":
        # p such that 2p/3 = 0.07 → p = 0.105
        ch = single_axis("Z", 0.105 * float(intensity))
        return ch, ch, flags
    raise KeyError(attack)
