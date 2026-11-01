"""Small typed records used across parse, validate, and emit."""

from __future__ import annotations

from dataclasses import dataclass, field


def pair_key(chain: str, address: str) -> tuple[str, str]:
    """Identity for sort, dedup, and set-diff. EVM hex is case-insensitive."""
    chain_u = (chain or "").upper()
    addr = address or ""
    if addr.startswith(("0x", "0X")):
        return (chain_u, addr.lower())
    return (chain_u, addr)


def record_sort_key(record: "AddressRecord") -> tuple:
    uid = record.uid
    uid_key = (0, int(uid), uid) if uid.isdigit() else (1, 0, uid)
    return (*pair_key(record.chain, record.address), uid_key, record.name)


@dataclass(frozen=True)
class AddressRecord:
    address: str
    chain: str
    uid: str = ""
    name: str = ""

    def as_payload(self) -> dict[str, str]:
        return {
            "address": self.address,
            "chain": self.chain,
            "uid": self.uid,
            "name": self.name,
        }


@dataclass
class ExtractResult:
    source: str
    source_urls: list[str]
    ofac_publish_date: str = ""
    ofac_list_version: str = ""
    ofac_record_count: str = ""
    http_last_modified: str = ""
    entries: list[AddressRecord] = field(default_factory=list)
    unique: list[AddressRecord] = field(default_factory=list)
    skipped_blank: int = 0

    @property
    def entry_count(self) -> int:
        return len(self.entries)

    @property
    def unique_count(self) -> int:
        return len(self.unique)


@dataclass
class FetchResult:
    url: str
    body: str
    last_modified: str = ""
    status: int = 0


@dataclass
class SanityFailure(Exception):
    message: str

    def __str__(self) -> str:
        return self.message
