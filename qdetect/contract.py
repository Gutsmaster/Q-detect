"""Contract engine: ε_requested → L_min → unused key → {ADMIT, DEFER}.

Fail closed: if requested security is unreachable, DEFER. Do not silently
issue a weaker signature that still passes verification.

Three budgets, not one scalar. Assembled into Weng's ε_tot.
The ε's may not move monotonically with L; L_min may not be unique.
We derive the forgery budget in closed form and the repudiation budget
numerically, and display only what is derived.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from qdetect.finite_size import SecurityReport, assemble, choose_thresholds, e_bf_star


@dataclass
class KeyPool:
    pairs_generated: int = 0
    pairs_consumed: int = 0
    signatures_issued: int = 0
    wc_pad_bits_used: int = 0
    used_key_ids: set[str] = field(default_factory=set)

    @property
    def remaining(self) -> int:
        return max(0, self.pairs_generated - self.pairs_consumed)


@dataclass
class ContractDecision:
    admit: bool
    label: str  # ADMIT / DEFER
    reason: str
    l_min: float | None
    remaining: int
    eps_requested: float
    security: SecurityReport | None


def decide(
    *,
    pool: KeyPool,
    e_b: float,
    n_u: int,
    n_cu: int,
    n_t_c: int,
    e_ct: float,
    p_c: float,
    eps_requested: float,
    t_a: float | None = None,
    t_v: float | None = None,
    monitor_consistent: bool = True,
) -> ContractDecision:
    e_bf = e_bf_star(e_b)
    if t_a is None or t_v is None:
        t_a, t_v = choose_thresholds(e_b, e_bf)
    sec = assemble(
        e_b=e_b,
        t_a=t_a,
        t_v=t_v,
        n_u=n_u,
        n_cu=n_cu,
        n_t_c=n_t_c,
        e_ct=e_ct,
        p_c=p_c,
    )
    if not monitor_consistent:
        return ContractDecision(
            admit=False,
            label="DEFER",
            reason="Link is not certifiable (Q-DETECT VIOLATION). This signature's validity is unchanged; the next one is not admitted.",
            l_min=sec.l_min,
            remaining=pool.remaining,
            eps_requested=eps_requested,
            security=sec,
        )
    # Magnitude too high: shape may still be honest, but the security margin is gone.
    # Fail closed rather than issue a weaker signature that still passes T_v.
    if e_b > 0.16:
        return ContractDecision(
            admit=False,
            label="DEFER",
            reason="Honest-shaped channel but conclusive mismatch is too high for the requested contract. Fail closed.",
            l_min=sec.l_min,
            remaining=pool.remaining,
            eps_requested=eps_requested,
            security=sec,
        )
    pulses_needed = n_u + n_cu  # another signature of this size
    if pool.remaining < pulses_needed:
        return ContractDecision(
            admit=False,
            label="DEFER",
            reason=f"Need ~{pulses_needed} unused pairs for another signature; {pool.remaining} remain. Fail closed.",
            l_min=sec.l_min,
            remaining=pool.remaining,
            eps_requested=eps_requested,
            security=sec,
        )
    # Forgery-budget gate only when E_BF actually sits above T_v (Weng operating point).
    # At the 7% detector-demo fibre that gap is empty and must not silently DEFER an honest link.
    if (
        sec.e_bf > sec.t_v
        and sec.l_min is not None
        and np.isfinite(sec.l_min)
        and n_cu < sec.l_min
    ):
        return ContractDecision(
            admit=False,
            label="DEFER",
            reason=f"Forgery budget L_min={sec.l_min:.0f} not met at n_cu={n_cu}.",
            l_min=sec.l_min,
            remaining=pool.remaining,
            eps_requested=eps_requested,
            security=sec,
        )
    reason = "Monitor CONSISTENT and remaining material covers another signature of this size."
    if sec.e_bf <= sec.t_v:
        reason += " Weng ε_for is not advertised at this noise (E_BF does not sit above T_v); switch operating_point to 'weng' for that budget."
    return ContractDecision(
        admit=True,
        label="ADMIT",
        reason=reason,
        l_min=sec.l_min,
        remaining=pool.remaining,
        eps_requested=eps_requested,
        security=sec,
    )
