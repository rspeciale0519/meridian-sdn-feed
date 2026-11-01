"""Small typed records used across parse, validate, and emit."""

from __future__ import annotations

from dataclasses import dataclass, field


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
