"""Shared test paths and fake fetchers. Tests never open a network connection."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sdn_feed.models import AddressRecord, FetchResult  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def fake_fetch(mapping: dict[str, str | Exception]) -> callable:
    def _fetch(url: str) -> FetchResult:
        value = mapping.get(url)
        if value is None:
            raise RuntimeError(f"unexpected network URL in test: {url}")
        if isinstance(value, Exception):
            raise value
        return FetchResult(url=url, body=value, last_modified="Wed, 28 Oct 2026 14:03:02 GMT", status=200)

    return _fetch


def eth_record(index: int, uid: str = "", name: str = "ENTITY") -> AddressRecord:
    return AddressRecord(
        address=f"0x{index:040x}",
        chain="ETH",
        uid=uid or str(index),
        name=name,
    )
