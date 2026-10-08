"""Optional future adapter contract, not a Passive Authentication implementation."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ChipEvidence:
    sod_der: bytes
    dg1: bytes
    dg2: bytes
    trust_store_id: str


@dataclass(frozen=True)
class PassiveAuthenticationResult:
    signature_valid: bool | None
    trust_chain_valid: bool | None
    dg1_hash_valid: bool | None
    dg2_hash_valid: bool | None
    explanation: str


class PassiveAuthenticationProvider(Protocol):
    def verify(self, evidence: ChipEvidence) -> PassiveAuthenticationResult:
        """Implement signature, trust-chain and data-group verification together."""
        ...
