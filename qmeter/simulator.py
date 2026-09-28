"""End-to-end pipeline: protocol → measurement → both detectors → contract.

Single engine. The baseline is a setting (`detector_mode`), not a second program.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from time import perf_counter

import numpy as np

from qmeter.attacks import ATTACKS, channels_for
from qmeter.constants import EPS_TOT_TARGET
from qmeter.contract import ContractDecision, KeyPool, decide
from qmeter.credentials import CredentialBook
from qmeter.detector import MonitorVerdict, qmeter_verdict
from qmeter.finite_size import SecurityReport, assemble, choose_thresholds, e_bf_star
from qmeter.mac import HMACAuth, WegmanCarter
from qmeter.protocol import SignatureOutcome, run_signature
from qmeter.teleport import pair_click_probability


@dataclass
class SimulationConfig:
    n_pulses: int = 12000
    seed: int = 141
    attack: str = "none"
    intensity: float = 1.0
    length_km: float = 0.0
    test_fraction: float = 0.3
    message: int = 0
    force_click: bool = True
    auth_plane: str = "wegman-carter"  # or "hmac"
    eps_requested: float = EPS_TOT_TARGET
    t_a: float | None = None
    t_v: float | None = None
    operating_point: str = "detector_demo"  # or "weng"
    verifier: str = "charlie"
    verifier_token: str | None = "charlie-token"
    key_id: str = "k0"


@dataclass
class PipelineResult:
    config: SimulationConfig
    outcome: SignatureOutcome
    bob_monitor: MonitorVerdict
    charlie_monitor: MonitorVerdict
    security: SecurityReport
    contract: ContractDecision
    credential_ok: bool
    credential_reason: str
    replay_caught: bool
    elapsed_s: float
    layers: dict
    notes: list[str]

    def public_dict(self) -> dict:
        o = self.outcome
        bs, cs = o.bob_stats, o.charlie_stats
        return {
            "elapsed_s": self.elapsed_s,
            "attack": self.config.attack,
            "attack_title": ATTACKS.get(self.config.attack, ATTACKS["none"]).title,
            "mechanism": ATTACKS.get(self.config.attack, ATTACKS["none"]).mechanism,
            "n_pulses": self.config.n_pulses,
            "length_km": self.config.length_km,
            "force_click": self.config.force_click,
            "click_probability": pair_click_probability(self.config.length_km)[0] if not self.config.force_click else 1.0,
            "message": o.message,
            "pairs_consumed": o.pairs_consumed,
            "n_dropped_match": o.n_dropped_match,
            "bob": {
                "e_cu": o.bob.e_cu,
                "n_cu": o.bob.n_cu,
                "p_c": o.bob.p_c,
                "e_ct": o.bob.e_ct,
                "threshold": o.bob.threshold,
                "accepted": o.bob.accepted,
                "early_reject": o.bob.early_reject,
            },
            "charlie": {
                "e_cu": o.charlie.e_cu,
                "n_cu": o.charlie.n_cu,
                "p_c": o.charlie.p_c,
                "e_ct": o.charlie.e_ct,
                "threshold": o.charlie.threshold,
                "accepted": o.charlie.accepted,
                "early_reject": o.charlie.early_reject,
            },
            "forwarded": o.forwarded,
            "signature_accepted": o.accepted,
            "bob_axis": {
                "e": [bs.e_x, bs.e_y, bs.e_z],
                "p": [bs.p_x, bs.p_y, bs.p_z],
                "n": [bs.n_x, bs.n_y, bs.n_z],
                "aggregate": bs.aggregate,
            },
            "charlie_axis": {
                "e": [cs.e_x, cs.e_y, cs.e_z],
                "p": [cs.p_x, cs.p_y, cs.p_z],
                "n": [cs.n_x, cs.n_y, cs.n_z],
                "aggregate": cs.aggregate,
            },
            "monitor_bob": {
                "label": self.bob_monitor.label,
                "mahalanobis": self.bob_monitor.mahalanobis,
                "threshold": self.bob_monitor.threshold,
                "aggregate_alarm": self.bob_monitor.aggregate_alarm,
            },
            "monitor_charlie": {
                "label": self.charlie_monitor.label,
                "mahalanobis": self.charlie_monitor.mahalanobis,
                "threshold": self.charlie_monitor.threshold,
                "aggregate_alarm": self.charlie_monitor.aggregate_alarm,
            },
            "security": {
                "e_b": self.security.e_b,
                "e_p": self.security.e_p,
                "e_bf": self.security.e_bf,
                "t_a": self.security.t_a,
                "t_v": self.security.t_v,
                "eps_for": self.security.eps_for,
                "eps_rep": self.security.eps_rep,
                "eps_rob": self.security.eps_rob,
                "eps_tot": self.security.eps_tot,
                "l_min": self.security.l_min if self.security.l_min is not None and np.isfinite(self.security.l_min) else None,
                "n_cu_for": self.security.n_cu_for if np.isfinite(self.security.n_cu_for) else None,
                "phase_error_model": self.security.phase_error_model,
                "notes": self.security.notes,
            },
            "contract": {
                "label": self.contract.label,
                "reason": self.contract.reason,
                "remaining": self.contract.remaining,
                "l_min": self.contract.l_min,
            },
            "credential_ok": self.credential_ok,
            "credential_reason": self.credential_reason,
            "replay_caught": self.replay_caught,
            "layers": self.layers,
            "notes": self.notes,
            "centrepiece": {
                "aggregate": cs.aggregate,
                "breakdown": [cs.e_x, cs.e_y, cs.e_z],
                "protocol": "ACCEPT" if o.accepted else "REJECT",
                "qmeter": self.charlie_monitor.label,
                "contract": self.contract.label,
            },
        }


# Session-level mutable store for the dashboard
POOL = KeyPool(pairs_generated=2_000_000)
BOOK = CredentialBook()
BOOK.invite("charlie", "charlie-token", quota=8)
BOOK.invite("bob", "bob-token", quota=8)
USED_KEYS: set[str] = set()
WC = WegmanCarter.fresh()
HMAC = HMACAuth()


def reset_session() -> None:
    global POOL, BOOK, USED_KEYS, WC, HMAC
    POOL = KeyPool(pairs_generated=2_000_000)
    BOOK = CredentialBook()
    BOOK.invite("charlie", "charlie-token", quota=8)
    BOOK.invite("bob", "bob-token", quota=8)
    USED_KEYS = set()
    WC = WegmanCarter.fresh()
    HMAC = HMACAuth()


def run_pipeline(cfg: SimulationConfig, pool: KeyPool | None = None) -> PipelineResult:
    t0 = perf_counter()
    rng = np.random.default_rng(cfg.seed)
    pool = pool if pool is not None else POOL
    notes: list[str] = []

    replay_caught = False
    if cfg.attack == "replay" or cfg.key_id in USED_KEYS:
        if cfg.key_id in USED_KEYS:
            replay_caught = True
            notes.append("Replay caught by one-time key tracking.")

    cred_ok, cred_reason = True, "ok"
    if cfg.attack == "unauthorized":
        cred_ok, cred_reason = BOOK.check("mallory", "nope")
    elif cfg.attack == "impersonation":
        cred_ok, cred_reason = False, "impersonation: signer is not Alice"
    elif cfg.attack == "greedy":
        # burn the quota
        for _ in range(BOOK.creds["charlie"].quota + 1):
            cred_ok, cred_reason = BOOK.check("charlie", cfg.verifier_token)
    else:
        cred_ok, cred_reason = BOOK.check(cfg.verifier, cfg.verifier_token)

    bob_ch, charlie_ch, flags = channels_for(cfg.attack, cfg.intensity)
    t_a, t_v = cfg.t_a, cfg.t_v
    if t_a is None or t_v is None:
        t_a, t_v = choose_thresholds(0.12, e_bf_star(0.12), operating_point=cfg.operating_point)

    outcome = run_signature(
        rng=rng,
        n_pulses=cfg.n_pulses,
        message=cfg.message,
        t_a=t_a,
        t_v=t_v,
        test_fraction=cfg.test_fraction,
        bob_channel=bob_ch,
        charlie_channel=charlie_ch,
        length_km=cfg.length_km,
        force_click=cfg.force_click,
        skip_postmatch=flags["skip_postmatch"],
        tamper_bob_correction=False,
        tamper_charlie_correction=flags["tamper_correction"],
        tamper_fraction=min(1.0, cfg.intensity),
        forge=flags["forge"],
        nonunital_gamma=flags["nonunital_gamma"],
        key_id=cfg.key_id,
    )

    # No fixed `family` passed here: qmeter_verdict picks a calibration
    # sized to each party's own observed matching-basis count (see its
    # docstring). Bob and Charlie generally see different counts, so each
    # gets its own matched calibration rather than sharing one built for
    # a hardcoded default.
    bob_mon = qmeter_verdict(outcome.bob_stats)
    charlie_mon = qmeter_verdict(outcome.charlie_stats)

    e_b = outcome.charlie.e_ct if outcome.charlie.n_ct else outcome.charlie.e_cu
    if e_b != e_b:
        e_b = 0.02
    sec = assemble(
        e_b=float(e_b),
        t_a=t_a,
        t_v=t_v,
        n_u=int((~outcome.charlie_rec.test_mask).sum()),
        n_cu=outcome.charlie.n_cu,
        n_t_c=outcome.charlie.n_ct,
        e_ct=float(outcome.charlie.e_ct if outcome.charlie.e_ct == outcome.charlie.e_ct else e_b),
        p_c=outcome.charlie.p_c,
    )

    pool.pairs_consumed += outcome.pairs_consumed
    pool.pairs_generated = max(pool.pairs_generated, pool.pairs_consumed)
    if cfg.auth_plane == "wegman-carter":
        payload = outcome.bob_rec.meas_axis.tobytes()  # stand-in for correction bits
        try:
            WC.tag(payload[: min(len(payload), 4096)])
            pool.wc_pad_bits_used = WC.key_bits_consumed()
        except RuntimeError:
            notes.append("Wegman–Carter pad exhausted.")
    else:
        HMAC.tag(b"correction-bits")
        notes.append("Auth plane is HMAC: ITS claim withdrawn at the classical-correction plane.")

    monitor_ok = charlie_mon.consistent and bob_mon.consistent
    contract = decide(
        pool=pool,
        e_b=float(e_b),
        n_u=sec.n_u,
        n_cu=sec.n_cu,
        n_t_c=outcome.charlie.n_ct,
        e_ct=sec.e_b,
        p_c=outcome.charlie.p_c or (1 / 6),
        eps_requested=cfg.eps_requested,
        t_a=t_a,
        t_v=t_v,
        monitor_consistent=monitor_ok,
    )

    # Protocol accept/reject is independent of the monitor. Credential / replay
    # can still abort the application-level signature.
    app_accept = outcome.accepted
    if replay_caught or not cred_ok:
        app_accept = False

    if app_accept:
        USED_KEYS.add(cfg.key_id)
        pool.signatures_issued += 1

    protocol_state = "ACCEPT" if app_accept else "REJECT"
    if not outcome.forwarded:
        protocol_state = "ABORT (Bob)"

    layers = {
        "qds": protocol_state,
        "monitor": charlie_mon.label,
        "contract": contract.label,
    }
    notes.extend(sec.notes)
    notes.append(
        "Detection does not override accept/reject. "
        "'This signature was valid. The link is no longer certifiable for the next one.' "
        if (outcome.accepted and not monitor_ok)
        else "Three decision layers kept separate."
    )
    if flags["nonunital_gamma"]:
        notes.append(
            "Non-unital channel: recovered (p_X, p_Y, p_Z) may be negative. "
            "That is the estimator failing honestly, not a detection."
        )

    elapsed = perf_counter() - t0
    # overwrite accepted flag for the public view
    outcome.accepted = app_accept
    return PipelineResult(
        config=cfg,
        outcome=outcome,
        bob_monitor=bob_mon,
        charlie_monitor=charlie_mon,
        security=sec,
        contract=contract,
        credential_ok=cred_ok,
        credential_reason=cred_reason,
        replay_caught=replay_caught,
        elapsed_s=elapsed,
        layers=layers,
        notes=notes,
    )
