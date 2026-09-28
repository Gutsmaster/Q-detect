"""Authenticated classical correction bits.

Wegman–Carter (polynomial hash over GF(2^128) + one-time pad of the tag)
is information-theoretic for a bounded number of messages. HMAC-SHA256
is computational; if it is used, the ITS claim is withdrawn at this plane.

WC tag length scales as ~ log(1/ε) + log(message length), not linearly
in the number of correction bits. Authenticating 20,000 bits does not
cost 20,000 key bits.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass, field

from qmeter.constants import WC_TAG_BITS


def _gf_mul(a: int, b: int) -> int:
    """Multiply in GF(2^128) with Rijndael polynomial x^128+x^7+x^2+x+1.

    `MOD & ((1 << 128) - 1)` already strips the leading x^128 term off the
    modulus, leaving exactly x^7+x^2+x+1 (0x87) — the reduction to XOR in
    when a left-shift carries a 1 out of bit 127. That single XOR is the
    complete reduction step.

    A previous version of this function XORed in an *extra* trailing `^ 1`
    after that reduction, which changes the effective modulus to x^7+x^2+x
    (0x86) = x(x^6+x+1) — reducible, not the irreducible Rijndael
    polynomial, so multiplication over that "field" is not associative in
    general and the almost-XOR-universal collision bound for Wegman–Carter
    does not hold. Verified against a reference implementation: with the
    extra XOR, all products beyond the first shift-with-carry mismatched a
    correct GF(2^128) multiply; small inputs that reduce zero or one time
    can still look right, which is why a spot check does not catch it. The
    extra XOR is removed here; do not reintroduce it.
    """
    MOD = (1 << 128) | (1 << 7) | (1 << 2) | (1 << 1) | 1
    p = 0
    for _ in range(128):
        if b & 1:
            p ^= a
        b >>= 1
        carry = a & (1 << 127)
        a = (a << 1) & ((1 << 128) - 1)
        if carry:
            a ^= MOD & ((1 << 128) - 1)
    return p


def poly_hash(key: int, blocks: list[int]) -> int:
    """Horner polynomial hash Σ m_i k^i over GF(2^128)."""
    h = 0
    for m in blocks:
        h = _gf_mul(h, key) ^ (m & ((1 << 128) - 1))
    return h


def _bytes_to_blocks(data: bytes) -> list[int]:
    if not data:
        return [0]
    pad = (-len(data)) % 16
    data = data + b"\x00" * pad
    return [int.from_bytes(data[i : i + 16], "big") for i in range(0, len(data), 16)]


@dataclass
class WegmanCarter:
    """One hash key (reuseable, almost-XOR-universal) + one-time pad of the tag."""

    hash_key: int
    pad_pool: bytearray
    pad_used: int = 0
    tag_bits: int = WC_TAG_BITS
    messages_authed: int = 0

    @classmethod
    def fresh(cls, pad_bytes: int = 1 << 16, tag_bits: int = WC_TAG_BITS) -> "WegmanCarter":
        hk = int.from_bytes(os.urandom(16), "big")
        return cls(hash_key=hk, pad_pool=bytearray(os.urandom(pad_bytes)), tag_bits=tag_bits)

    @property
    def tag_bytes(self) -> int:
        return (self.tag_bits + 7) // 8

    def tag(self, data: bytes) -> bytes:
        blocks = _bytes_to_blocks(data)
        h = poly_hash(self.hash_key, blocks)
        tb = self.tag_bytes
        h_bytes = h.to_bytes(16, "big")[-tb:]
        if self.pad_used + tb > len(self.pad_pool):
            raise RuntimeError("Wegman–Carter one-time pad exhausted")
        pad = bytes(self.pad_pool[self.pad_used : self.pad_used + tb])
        self.pad_used += tb
        self.messages_authed += 1
        return bytes(a ^ b for a, b in zip(h_bytes, pad))

    def verify(self, data: bytes, tag: bytes, pad: bytes) -> bool:
        """Verify with the pad that was consumed for this message (kept by receiver)."""
        blocks = _bytes_to_blocks(data)
        h = poly_hash(self.hash_key, blocks)
        tb = self.tag_bytes
        h_bytes = h.to_bytes(16, "big")[-tb:]
        expect = bytes(a ^ b for a, b in zip(h_bytes, pad))
        return hmac.compare_digest(expect, tag)

    def key_bits_consumed(self) -> int:
        return self.pad_used * 8


@dataclass
class HMACAuth:
    """Computational MAC. ITS claim withdrawn at this plane."""

    key: bytes = field(default_factory=lambda: os.urandom(32))
    its_claimed: bool = False
    messages_authed: int = 0

    def tag(self, data: bytes) -> bytes:
        self.messages_authed += 1
        return hmac.new(self.key, data, hashlib.sha256).digest()[:16]

    def verify(self, data: bytes, tag: bytes) -> bool:
        return hmac.compare_digest(self.tag(data) if False else hmac.new(self.key, data, hashlib.sha256).digest()[:16], tag)
