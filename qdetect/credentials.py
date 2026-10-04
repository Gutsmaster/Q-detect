"""Verifier credentialing bound to the distribution chain.

Three cases (brief §Tier 2):
  never-invited          → credentialing catches it
  invited-but-greedy     → quota catches it
  invited-but-compromised credential used by someone else → currently uncovered
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Credential:
    party: str
    token: str
    invited: bool
    quota: int
    used: int = 0


@dataclass
class CredentialBook:
    creds: dict[str, Credential] = field(default_factory=dict)

    def invite(self, party: str, token: str, quota: int = 8) -> Credential:
        c = Credential(party=party, token=token, invited=True, quota=quota)
        self.creds[party] = c
        return c

    def check(self, party: str, token: str | None) -> tuple[bool, str]:
        if party not in self.creds or not self.creds[party].invited:
            return False, "never-invited"
        c = self.creds[party]
        if token != c.token:
            # invited-but-compromised is indistinguishable from a wrong token
            # with this design; flagged as known gap, not claimed caught.
            return False, "bad-token (invited-but-compromised is uncovered)"
        if c.used >= c.quota:
            return False, "invited-but-greedy"
        c.used += 1
        return True, "ok"
