"""Weng finite-size security layer.

Every symbol is Weng's. The one documented deviation: default e_p(e_b)
uses Yin et al. 2016a (the paper Weng cites) rather than Weng's printed
intercept (4-√2)/4, which makes e_p > 1/2 for every e_b ≥ 0 and collapses
the forgery bound. Switch with phase_error_model='weng_printed'.

L_min from the forgery budget is a closed form. Repudiation and robustness
are solved numerically. The meter displays only derived values.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import brentq

from qdetect.constants import (
    EP_INTERCEPT_WENG_PRINTED,
    EP_INTERCEPT_YIN2016,
    EP_SLOPE_SIX_STATE,
    EPS_FOR_TARGET,
    EPS_PE_DEFAULT,
    EPS_REP_TARGET,
    EPS_ROB_TARGET,
    EPS_TOT_TARGET,
    IDEAL_CONCLUSIVE_PROB,
)


def binary_entropy(x: float) -> float:
    x = float(np.clip(x, 1e-16, 1.0 - 1e-16))
    return float(-x * np.log2(x) - (1.0 - x) * np.log2(1.0 - x))


def inv_binary_entropy(h: float) -> float:
    """Inverse of h_2 on [0, 1/2]."""
    h = float(h)
    if h <= 0.0:
        return 0.0
    if h >= 1.0:
        return 0.5
    lo, hi = 0.0, 0.5
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if binary_entropy(mid) < h:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def chernoff_upper(a: float, eps1: float) -> float:
    """Weng: ā* = a + β + √(2βa + β²), β = ln(1/ε₁)."""
    a = max(float(a), 0.0)
    beta = float(np.log(1.0 / eps1))
    return a + beta + np.sqrt(2.0 * beta * a + beta ** 2)


def chernoff_lower(a: float, eps1: float) -> float:
    """Weng: a̱* = a − β/2 − √(2βa + β²/4)."""
    a = max(float(a), 0.0)
    beta = float(np.log(1.0 / eps1))
    return a - 0.5 * beta - np.sqrt(2.0 * beta * a + 0.25 * beta ** 2)


def phase_error(e_b: float, model: str = "yin2016") -> float:
    """Weng Eq. (8) for M=3, with the intercept choice documented in PROTOCOL.md."""
    e_b = float(np.clip(e_b, 0.0, 1.0))
    if model == "weng_printed":
        intercept = EP_INTERCEPT_WENG_PRINTED
    elif model == "yin2016":
        intercept = EP_INTERCEPT_YIN2016
    else:
        raise ValueError(model)
    return float(np.clip(intercept + EP_SLOPE_SIX_STATE * e_b, 0.0, 1.0))


def e_bf_star(e_b: float, model: str = "yin2016") -> float:
    """Minimum expected forgery mismatch of conclusive k-photon results.

    H(E_BF*) = 1 − I_B, I_B = H(e_p | e_b). Conservative: I_B = h_2(e_p).
    """
    e_p = phase_error(e_b, model=model)
    i_b = binary_entropy(e_p)
    h_e = max(0.0, 1.0 - i_b)
    return inv_binary_entropy(h_e)


def epsilon_for(e_bf: float, t_v: float, n_cu: float, n_k_cu: float | None = None) -> float:
    """Weng Eq. (9)."""
    if n_k_cu is None:
        n_k_cu = n_cu
    if n_k_cu <= 0 or e_bf <= 0:
        return 1.0
    t_vk = t_v * n_cu / n_k_cu
    gap = e_bf - t_vk
    if gap <= 0:
        return 1.0
    return float(np.exp(-((gap ** 2) / (2.0 * e_bf)) * n_k_cu))


def n_cu_for_forgery(e_bf: float, t_v: float, eps_for: float = EPS_FOR_TARGET) -> float:
    """Closed-form forgery budget. Derived from Weng Eq. (9), single-qubit n_k = n_cu."""
    gap = e_bf - t_v
    if gap <= 0 or e_bf <= 0:
        return float("inf")
    return (2.0 * e_bf * np.log(1.0 / eps_for)) / (gap ** 2)


def sampling_delta(n: int, k: int, lam: float, eps: float) -> float:
    """Random-sampling-without-replacement deviation, Yin 2016 appendix g(·)."""
    n, k = max(int(n), 1), max(int(k), 1)
    lam = float(np.clip(lam, 1e-12, 1.0 - 1e-12))
    c = np.exp(
        1.0 / (8.0 * (n + k))
        + 1.0 / (12.0 * k)
        - 1.0 / (12.0 * k * lam + 1.0)
        - 1.0 / (12.0 * k * (1.0 - lam) + 1.0)
    )
    inside = np.log(np.sqrt(n + k) * c / (np.sqrt(2.0 * np.pi * n * k * lam * (1.0 - lam)) * eps))
    inside = max(inside, 0.0)
    return float(np.sqrt(2.0 * (n + k) * lam * (1.0 - lam) / (n * k)) * np.sqrt(inside))


def robustness_epsilon(n_u_c: int, n_t_c: int, e_ct: float, t_a: float) -> float:
    """Yin 2016 Eq. (6): Pr(honest reject) via sampling without replacement."""
    n, k = max(int(n_u_c), 1), max(int(n_t_c), 1)
    lam = float(np.clip(e_ct, 1e-12, 1.0 - 1e-12))
    t = t_a - e_ct
    if t <= 0:
        return 1.0
    c = np.exp(
        1.0 / (8.0 * (n + k))
        + 1.0 / (12.0 * k)
        - 1.0 / (12.0 * k * lam + 1.0)
        - 1.0 / (12.0 * k * (1.0 - lam) + 1.0)
    )
    num = np.exp(-(n * k * t ** 2) / (2.0 * (n + k) * lam * (1.0 - lam))) * c
    den = np.sqrt(2.0 * np.pi * n * k * lam * (1.0 - lam) / (n + k))
    return float(min(1.0, num / max(den, 1e-300)))


def _repudiation_lhs_rhs(a: float, p_b: float, p_c: float, t_a: float, t_v: float, delta_over_n: float):
    left = ((a - p_b * t_a) ** 2) / (2.0 * a)
    inner = delta_over_n + a / p_b
    right_num = (p_c * t_v - p_c * inner) ** 2
    right_den = 3.0 * p_c * inner
    if a <= 0 or inner <= 0 or right_den <= 0:
        return np.inf, 0.0
    return left, right_num / right_den


def epsilon_rep(
    p_b: float,
    p_c: float,
    t_a: float,
    t_v: float,
    n_u: int,
    delta_bar_cu: float,
    n_cu: int,
) -> tuple[float, float | None]:
    """Weng Eqs. (11–12). Returns (ε_rep, A) or (1.0, None) if no feasible A."""
    p_b = max(float(p_b), 1e-12)
    p_c = max(float(p_c), 1e-12)
    n_cu = max(int(n_cu), 1)
    delta_over_n = float(delta_bar_cu) / n_cu
    lo = p_b * t_a
    hi = p_b * (t_v - delta_over_n)
    if not (lo < hi):
        return 1.0, None

    def f(a: float) -> float:
        left, right = _repudiation_lhs_rhs(a, p_b, p_c, t_a, t_v, delta_over_n)
        return left - right

    grid = np.linspace(lo + 1e-12, hi - 1e-12, 40)
    vals = [f(float(x)) for x in grid]
    a_star = None
    for i in range(len(grid) - 1):
        if vals[i] == 0:
            a_star = float(grid[i])
            break
        if vals[i] * vals[i + 1] < 0:
            try:
                a_star = float(brentq(f, float(grid[i]), float(grid[i + 1])))
            except ValueError:
                continue
            break
    if a_star is None:
        # pick the A in (lo, hi) that equalises the two Chernoff exponents as well as possible
        a_star = float(grid[int(np.argmin(np.abs(vals)))])
    left, _ = _repudiation_lhs_rhs(a_star, p_b, p_c, t_a, t_v, delta_over_n)
    eps = float(np.exp(-left * n_u))
    return min(1.0, eps), a_star


def abruzzo_zeta(eps_pe: float, m: int) -> float:
    """Abruzzo et al. 2011 Eq. (3)."""
    m = max(int(m), 1)
    return float(np.sqrt((np.log(1.0 / eps_pe) + 2.0 * np.log(m + 1.0)) / (8.0 * m)))


def abruzzo_upper(e_meas: float, m: int, eps_pe: float = EPS_PE_DEFAULT) -> float:
    return float(e_meas + 2.0 * abruzzo_zeta(eps_pe, m))


@dataclass
class SecurityReport:
    e_b: float
    e_p: float
    e_bf: float
    t_a: float
    t_v: float
    n_u: int
    n_cu: int
    p_c: float
    eps1: float
    eps2: float
    eps_for: float
    eps_rep: float
    eps_rob: float
    eps_tot: float
    a_rep: float | None
    n_cu_for: float
    n_u_rep: float | None
    l_min: float | None
    phase_error_model: str
    notes: list[str]


def assemble(
    *,
    e_b: float,
    t_a: float,
    t_v: float,
    n_u: int,
    n_cu: int,
    n_t_c: int,
    e_ct: float,
    p_c: float | None = None,
    delta_bar_cu: float | None = None,
    eps1: float = (EPS_TOT_TARGET - 3e-10) / 12.0,
    phase_error_model: str = "yin2016",
) -> SecurityReport:
    """ε_tot = 11 ε₁ + ε₂ + ε_rob + ε_for + ε_rep  (Weng Eq. 14, M=3)."""
    notes: list[str] = []
    if phase_error_model == "yin2016":
        notes.append(
            "e_p intercept from Yin et al. PRA 93, 032316 (2016), the source Weng cites. "
            "Weng's printed (4−√2)/4 intercept is available as phase_error_model='weng_printed'."
        )
    p_c = IDEAL_CONCLUSIVE_PROB if p_c is None else float(p_c)
    e_p = phase_error(e_b, model=phase_error_model)
    e_bf = e_bf_star(e_b, model=phase_error_model)
    eps_for = epsilon_for(e_bf, t_v, n_cu)
    n_for = n_cu_for_forgery(e_bf, t_v, EPS_FOR_TARGET)

    if delta_bar_cu is None:
        # Honest independent measurements of matched states: Δ_t ≤ e_B^c + e_C^c,
        # then add sampling fluctuation. Conservative: 2 e_b * n_cu * P(both conclusive)
        # plus g(·). We use 2 e_b as Δ_t/n scale.
        n_both = max(int(p_c * n_cu), 1)
        n_t_both = max(int(p_c * n_t_c), 1)
        delta_t = min(1.0, 2.0 * e_b) * n_both
        delta_bar_cu = delta_t + sampling_delta(n_both, n_t_both, min(0.49, 2.0 * e_b), eps1) * n_both

    eps_rep, a_rep = epsilon_rep(p_c, p_c, t_a, t_v, n_u, delta_bar_cu, max(n_cu, 1))
    eps_rob = robustness_epsilon(max(n_cu, 1), max(n_t_c, 1), e_ct, t_a)
    eps2 = eps1
    eps_tot = 11.0 * eps1 + eps2 + eps_rob + eps_for + eps_rep

    n_u_rep = None
    if a_rep is not None and a_rep > p_c * t_a:
        # invert ε_rep = exp[-(A − P^c T_a)² / (2A) * n^u]
        gap = a_rep - p_c * t_a
        if gap > 0:
            n_u_rep = (2.0 * a_rep * np.log(1.0 / EPS_REP_TARGET)) / (gap ** 2)

    l_candidates = [n_for]
    if n_u_rep is not None:
        l_candidates.append(n_u_rep)
    finite = [c for c in l_candidates if np.isfinite(c)]
    l_min = float(max(finite)) if finite else None
    if l_min is None:
        notes.append("L_min not advertised: forgery gap E_BF − T_v is non-positive.")
        notes.append(
            "At the 7% detector-demo fibre this is expected: Weng's ε_for is derived "
            "for the low-noise operating point (e_d = 0.1%), not for the centrepiece channel. "
            "Charlie still rejects a random forgery because that mismatch is ~50%, above T_v."
        )
    else:
        notes.append("L_min is max of derived budgets (forgery closed-form; repudiation numerical).")

    return SecurityReport(
        e_b=e_b,
        e_p=e_p,
        e_bf=e_bf,
        t_a=t_a,
        t_v=t_v,
        n_u=n_u,
        n_cu=n_cu,
        p_c=p_c,
        eps1=eps1,
        eps2=eps2,
        eps_for=eps_for,
        eps_rep=eps_rep,
        eps_rob=eps_rob,
        eps_tot=eps_tot,
        a_rep=a_rep,
        n_cu_for=n_for,
        n_u_rep=n_u_rep,
        l_min=l_min,
        phase_error_model=phase_error_model,
        notes=notes,
    )


def choose_thresholds(e_honest: float, e_bf: float, operating_point: str = "detector_demo") -> tuple[float, float]:
    """Pick T_a < T_v. Signature structure requires the gap; the numbers depend
    on the operating point (see constants.TA_DEMO / TA_WENG).
    """
    from qdetect.constants import TA_DEMO, TA_WENG, TV_DEMO, TV_WENG

    if operating_point == "weng":
        return TA_WENG, TV_WENG
    if operating_point == "detector_demo":
        return TA_DEMO, TV_DEMO
    e_honest = float(e_honest)
    e_bf = float(e_bf)
    t_a = min(0.49, max(e_honest + 0.02, 1.2 * e_honest if e_honest > 0 else 0.015))
    t_v = min(0.49, max(t_a + 0.05, 0.5 * (t_a + max(e_bf, t_a + 0.08))))
    if t_v <= t_a:
        t_v = min(0.49, t_a + 0.05)
    return float(t_a), float(t_v)
