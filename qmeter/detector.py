"""Baseline scalar detector and Q-METER basis-resolved monitor.

Detection is decoupled from accept/reject. Output is CONSISTENT / VIOLATION
(certifiability), never an override of Weng's T_a / T_v.

H0: observations explainable by the calibrated legitimate-channel family.
H1: not explainable within operating uncertainty. H1 ≠ Eve.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from qmeter.channel import recovered_pauli_rates
from qmeter.constants import CALIBRATION_WOBBLE, EPS_PE_DEFAULT, HONEST_P
from qmeter.finite_size import abruzzo_upper


@dataclass
class AxisStats:
    e_x: float
    e_y: float
    e_z: float
    n_x: int
    n_y: int
    n_z: int
    p_x: float
    p_y: float
    p_z: float
    aggregate: float
    n_match: int
    n_err: int
    e_x_upper: float
    e_y_upper: float
    e_z_upper: float


def matching_basis_errors(
    prep_axis: np.ndarray,
    prep_sign: np.ndarray,
    meas_axis: np.ndarray,
    meas_sign: np.ndarray,
    mask: np.ndarray | None = None,
) -> AxisStats:
    prep_axis = np.asarray(prep_axis)
    prep_sign = np.asarray(prep_sign)
    meas_axis = np.asarray(meas_axis)
    meas_sign = np.asarray(meas_sign)
    match = prep_axis == meas_axis
    if mask is not None:
        match = match & mask
    err = match & (prep_sign != meas_sign)
    n_axis = np.array([(match & (prep_axis == a)).sum() for a in range(3)], dtype=np.int64)
    n_err_a = np.array([(err & (prep_axis == a)).sum() for a in range(3)], dtype=np.int64)
    e = np.array(
        [float(n_err_a[a] / n_axis[a]) if n_axis[a] else float("nan") for a in range(3)],
        dtype=np.float64,
    )
    p = recovered_pauli_rates(e[0] if e[0] == e[0] else 0.0, e[1] if e[1] == e[1] else 0.0, e[2] if e[2] == e[2] else 0.0)
    n_match = int(match.sum())
    n_err = int(err.sum())
    agg = n_err / n_match if n_match else float("nan")
    return AxisStats(
        e_x=float(e[0]),
        e_y=float(e[1]),
        e_z=float(e[2]),
        n_x=int(n_axis[0]),
        n_y=int(n_axis[1]),
        n_z=int(n_axis[2]),
        p_x=p[0],
        p_y=p[1],
        p_z=p[2],
        aggregate=float(agg),
        n_match=n_match,
        n_err=n_err,
        e_x_upper=abruzzo_upper(e[0], int(n_axis[0])) if n_axis[0] else 1.0,
        e_y_upper=abruzzo_upper(e[1], int(n_axis[1])) if n_axis[1] else 1.0,
        e_z_upper=abruzzo_upper(e[2], int(n_axis[2])) if n_axis[2] else 1.0,
    )


@dataclass
class CalibratedFamily:
    mean: np.ndarray  # (3,)
    cov: np.ndarray  # (3, 3)
    inv_cov: np.ndarray
    threshold_99: float
    ensemble: np.ndarray  # (M, 3)


def _normalize_p(p: np.ndarray) -> np.ndarray:
    s = float(np.sum(np.abs(p)))
    if s < 1e-12:
        return np.array([1.0, 1.0, 1.0]) / 3.0
    return p / s


def calibrate_honest_family(
    rng: np.random.Generator,
    n_ensemble: int = 20000,
    n_per_axis: int = 16666,
    wobble: float = CALIBRATION_WOBBLE,
    honest_p: tuple[float, float, float] = HONEST_P,
) -> CalibratedFamily:
    """Calibrate on *shape* (normalized p), not magnitude.

    Magnitude is a contract-engine question (DEFER if the security margin is gone).
    Shape is the Q-METER question (VIOLATION if the axis pattern leaves the family).
    """
    p0 = np.array(honest_p, dtype=np.float64)
    samples = np.empty((n_ensemble, 3), dtype=np.float64)
    for i in range(n_ensemble):
        scale = 1.0 + wobble * rng.normal(size=3)
        p = np.clip(p0 * scale, 0.0, 0.49)
        e = np.array([p[1] + p[2], p[0] + p[2], p[0] + p[1]])
        e_hat = rng.binomial(n_per_axis, np.clip(e, 0.0, 1.0)) / n_per_axis
        samples[i] = _normalize_p(np.array(recovered_pauli_rates(e_hat[0], e_hat[1], e_hat[2])))
    mean = samples.mean(axis=0)
    cov = np.cov(samples, rowvar=False) + 1e-12 * np.eye(3)
    inv = np.linalg.pinv(cov)
    d2 = np.einsum("ni,ij,nj->n", samples - mean, inv, samples - mean)
    thr = float(np.quantile(d2, 0.99))
    return CalibratedFamily(mean=mean, cov=cov, inv_cov=inv, threshold_99=thr, ensemble=samples)


_FAMILY_CACHE: dict[tuple, CalibratedFamily] = {}  # cleared when shape calibration changes


def get_family(seed: int = 141, n_ensemble: int = 4000, n_per_axis: int = 4000) -> CalibratedFamily:
    key = (seed, n_ensemble, n_per_axis)
    if key not in _FAMILY_CACHE:
        rng = np.random.default_rng(seed)
        _FAMILY_CACHE[key] = calibrate_honest_family(rng, n_ensemble=n_ensemble, n_per_axis=n_per_axis)
    return _FAMILY_CACHE[key]


#: Below this many matching-basis samples on the *smallest* axis, the shape
#: estimate is too noisy for any fixed calibration to judge honestly. The
#: monitor abstains rather than guess. See ``qmeter_verdict`` docstring.
MIN_SAMPLES_PER_AXIS = 500

#: Calibration is looked up by n_per_axis in discrete steps rather than by
#: exact observed count, so a small run gets a small-sample calibration
#: instead of silently reusing the 4000-sample-per-axis default regardless
#: of how much data it actually has. Steps are cache keys for get_family();
#: choose_calibration_n rounds an observed count *up* to the first step that
#: covers it, so the null distribution is never narrower than what the live
#: run could plausibly produce.
CALIBRATION_N_STEPS: tuple[int, ...] = (500, 1000, 2000, 4000, 8000, 16666, 50000)


def choose_calibration_n(n_per_axis_observed: int) -> int:
    """Round an observed per-axis sample count up to a calibration step.

    Rounding up (not down, not nearest) means the calibration's assumed
    sample size is never smaller than what was actually observed, so the
    calibrated spread is never narrower than the live run's true noise.
    Narrower-than-true spread is what silently inflates the false-alarm
    rate; wider-than-true spread only costs detection power, which is the
    safe direction to err in for a monitor that must not cry wolf.
    """
    for step in CALIBRATION_N_STEPS:
        if n_per_axis_observed <= step:
            return step
    return CALIBRATION_N_STEPS[-1]


@dataclass
class MonitorVerdict:
    mahalanobis: float
    threshold: float
    consistent: bool
    label: str  # CONSISTENT / VIOLATION / INSUFFICIENT_DATA
    p_hat: tuple[float, float, float]
    aggregate: float
    aggregate_alarm: bool
    aggregate_threshold: float
    n_per_axis_observed: int
    n_per_axis_calibrated: int


def qmeter_verdict(stats: AxisStats, family: CalibratedFamily | None = None, aggregate_threshold: float = 0.10) -> MonitorVerdict:
    """Certifiability verdict: CONSISTENT / VIOLATION / INSUFFICIENT_DATA.

    ``family`` is deprecated: passing one explicitly bypasses the automatic
    sample-size matching below and is kept only so existing call sites and
    tests do not break. New code should omit it and let this function pick
    a calibration sized to what was actually observed.

    Without automatic matching, a fixed default-size calibration (n=4000)
    judges runs of *any* observed size against noise expected at n=4000.
    A run with fewer matching-basis samples per axis than that has more
    binomial scatter in its recovered shape than the calibration expects,
    so honest links get flagged as VIOLATION purely from small-sample
    noise, at a rate far above the nominal 1%. This is not a tuning
    problem; it is a mismatched null distribution, and it gets worse, not
    better, at small N.

    Two things fix it. First, calibrate at a sample size matched to what
    this run actually has (see ``choose_calibration_n``), so the expected
    scatter is realistic instead of borrowed from a larger, quieter run.
    Second, below ``MIN_SAMPLES_PER_AXIS`` even a matched calibration is
    unreliable — three-way-binned counts that small make the recovered
    shape itself unstable, not just its comparison to a baseline — so the
    monitor returns INSUFFICIENT_DATA instead of a forced guess. This is
    the same fail-closed posture as the credential and L_min layers: state
    "not enough evidence to certify" rather than certify on evidence too
    thin to trust either way.
    """
    n_obs = int(min(stats.n_x, stats.n_y, stats.n_z))

    if n_obs < MIN_SAMPLES_PER_AXIS:
        return MonitorVerdict(
            mahalanobis=float("nan"),
            threshold=float("nan"),
            consistent=False,
            label="INSUFFICIENT_DATA",
            p_hat=(stats.p_x, stats.p_y, stats.p_z),
            aggregate=stats.aggregate,
            aggregate_alarm=False,
            aggregate_threshold=aggregate_threshold,
            n_per_axis_observed=n_obs,
            n_per_axis_calibrated=0,
        )

    if family is None:
        n_cal = choose_calibration_n(n_obs)
        family = get_family(n_per_axis=n_cal)
    else:
        # Caller supplied a specific family (e.g. a test pinning an exact
        # calibration): trust it as-is and don't second-guess its size.
        n_cal = -1

    p = np.array([stats.p_x, stats.p_y, stats.p_z], dtype=np.float64)
    shape = _normalize_p(p)
    diff = shape - family.mean
    d2 = float(diff @ family.inv_cov @ diff)
    consistent = d2 <= family.threshold_99
    agg_alarm = (stats.aggregate == stats.aggregate) and (stats.aggregate > aggregate_threshold)
    return MonitorVerdict(
        mahalanobis=d2,
        threshold=family.threshold_99,
        consistent=consistent,
        label="CONSISTENT" if consistent else "VIOLATION",
        p_hat=(stats.p_x, stats.p_y, stats.p_z),
        aggregate=stats.aggregate,
        aggregate_alarm=agg_alarm,
        aggregate_threshold=aggregate_threshold,
        n_per_axis_observed=n_obs,
        n_per_axis_calibrated=n_cal,
    )


def certified_early_reject(n_seen: int, n_mis: int, n_total: int, threshold: float) -> bool:
    """If remaining positions cannot bring the mismatch rate under T, reject now.

    Deterministic arithmetic. Not a sequential confidence bound.
    Remaining all-correct still leaves n_mis / n_total > T.
    """
    if n_total <= 0:
        return False
    return (n_mis / n_total) > threshold
