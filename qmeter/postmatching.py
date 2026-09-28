"""Weng / Lu post-matching.

Alice reorders Charlie's kept sequence so the prepared-state types match
Bob's sequence. Charlie applies the same permutation to his measurement
outcomes. Independent sequences do not have identical multisets; we match
what we can by state type and drop the unmatched remainder.

This is the repudiation countermeasure. It is inherited, never claimed as ours.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class MatchedPair:
    axis: np.ndarray
    sign: np.ndarray
    bob_meas_axis: np.ndarray
    bob_meas_sign: np.ndarray
    charlie_meas_axis: np.ndarray
    charlie_meas_sign: np.ndarray
    n_dropped: int
    permutation_charlie: np.ndarray  # indices into Charlie's kept array


def state_id(axis: np.ndarray, sign: np.ndarray) -> np.ndarray:
    """Integer 0..5 labelling |±x⟩, |±y⟩, |±z⟩."""
    return (axis.astype(np.int16) * 2 + sign.astype(np.int16)).astype(np.int16)


def post_match(
    bob_axis: np.ndarray,
    bob_sign: np.ndarray,
    bob_meas_axis: np.ndarray,
    bob_meas_sign: np.ndarray,
    charlie_axis: np.ndarray,
    charlie_sign: np.ndarray,
    charlie_meas_axis: np.ndarray,
    charlie_meas_sign: np.ndarray,
) -> MatchedPair:
    """Match Charlie's prepared states onto Bob's order by type."""
    b_id = state_id(bob_axis, bob_sign)
    c_id = state_id(charlie_axis, charlie_sign)
    # queues of Charlie indices per type
    queues: list[list[int]] = [[] for _ in range(6)]
    for i, sid in enumerate(c_id.tolist()):
        queues[int(sid)].append(i)

    chosen_b: list[int] = []
    chosen_c: list[int] = []
    for j, sid in enumerate(b_id.tolist()):
        q = queues[int(sid)]
        if q:
            chosen_b.append(j)
            chosen_c.append(q.pop(0))

    if not chosen_b:
        empty = np.zeros(0, dtype=np.int8)
        return MatchedPair(empty, empty, empty, empty, empty, empty, int(b_id.size), np.zeros(0, dtype=np.int64))

    b_idx = np.array(chosen_b, dtype=np.int64)
    c_idx = np.array(chosen_c, dtype=np.int64)
    n_drop = int(b_id.size - b_idx.size)
    return MatchedPair(
        axis=bob_axis[b_idx],
        sign=bob_sign[b_idx],
        bob_meas_axis=bob_meas_axis[b_idx],
        bob_meas_sign=bob_meas_sign[b_idx],
        charlie_meas_axis=charlie_meas_axis[c_idx],
        charlie_meas_sign=charlie_meas_sign[c_idx],
        n_dropped=n_drop,
        permutation_charlie=c_idx,
    )
