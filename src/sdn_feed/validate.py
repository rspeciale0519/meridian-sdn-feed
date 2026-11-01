"""Address-shape and count sanity guards. Fail closed; never overwrite good data."""

from __future__ import annotations

import json
import re
from pathlib import Path

from sdn_feed.constants import MAX_DROP_RATIO, MAX_INVALID_RATIO, MIN_UNIQUE_COUNT
from sdn_feed.models import AddressRecord, ExtractResult, SanityFailure, pair_key

_B58 = r"[1-9A-HJ-NP-Za-km-z]"
_EVM = re.compile(r"^0x[0-9a-fA-F]{40}$")
_TRON = re.compile(rf"^T{_B58}{{33}}$")
_BTC = re.compile(rf"^(?:bc1[qpzry9x8gf2tvdw0s3jn54khce6mua7l]{{25,87}}|{_B58}{{25,35}})$")
_LTC = re.compile(rf"^(?:ltc1[qpzry9x8gf2tvdw0s3jn54khce6mua7l]{{25,87}}|{_B58}{{26,35}})$")
_XMR = re.compile(r"^[48][0-9A-Za-z]{94}$")
_XRP = re.compile(rf"^r{_B58}{{24,34}}$")
_DASH = re.compile(rf"^X{_B58}{{33}}$")
_ZEC = re.compile(rf"^(?:t[13]{_B58}{{32,90}}|zs{_B58}{{70,90}})$")
_SOL = re.compile(rf"^{_B58}{{32,44}}$")
_BCH = re.compile(
    rf"^(?:((bitcoincash|bchtest):)?[qp][a-z0-9]{{20,120}}|{_B58}{{25,35}})$",
    re.IGNORECASE,
)
_NEO = re.compile(rf"^A{_B58}{{33}}$")
_IOTA = re.compile(r"^[A-Z9]{20,90}$")
_BNB = re.compile(r"^bnb1[qpzry9x8gf2tvdw0s3jn54khce6mua7l]{38,80}$")
_DOGE = re.compile(rf"^D{_B58}{{25,34}}$")
_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")
_GENERIC = re.compile(
    r"^[1-9A-HJ-NP-Za-km-z]{16,128}$|^0x[0-9a-fA-F]{40,64}$|^[0-9a-fA-F]{64}$"
)

_CHAIN_RES: dict[str, tuple[re.Pattern[str], ...]] = {
    "XBT": (_BTC,),
    "BTC": (_BTC,),
    "BCH": (_BCH, _BTC),
    "BSV": (_BTC,),
    "BTG": (_BTC,),
    "ETH": (_EVM,),
    "ETC": (_EVM,),
    "ARB": (_EVM,),
    "BSC": (_EVM,),
    "BNB": (_BNB, _EVM),
    "USDT": (_EVM, _TRON, _SOL, _BTC),
    "USDC": (_EVM, _TRON, _SOL, _BTC),
    "TRX": (_TRON,),
    "LTC": (_LTC,),
    "XMR": (_XMR, _HEX64),
    "XRP": (_XRP,),
    "DASH": (_DASH,),
    "ZEC": (_ZEC,),
    "SOL": (_SOL,),
    "XVG": (_BTC,),
    "DOGE": (_DOGE, _BTC),
    "NEO": (_NEO,),
    "MIOTA": (_IOTA,),
}


def looks_valid(record: AddressRecord) -> bool:
    address = (record.address or "").strip()
    if not address or any(ch.isspace() for ch in address):
        return False
    patterns = _CHAIN_RES.get(record.chain.upper(), (_GENERIC,))
    return any(pat.fullmatch(address) for pat in patterns)


def invalid_records(records: list[AddressRecord]) -> list[AddressRecord]:
    return [r for r in records if not looks_valid(r)]


def result_pairs(result: ExtractResult) -> set[tuple[str, str]]:
    return {pair_key(r.chain, r.address) for r in result.unique}


def load_previous_pairs(path: Path) -> set[tuple[str, str]] | None:
    """Return previous (chain, address) pairs. Missing file → None. Corrupt → fail."""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SanityFailure(
            f"SANITY FAIL: previous feed is unreadable; refusing to skip drop guard ({exc})"
        ) from exc
    if not isinstance(data, dict):
        raise SanityFailure("SANITY FAIL: previous feed is corrupt (not an object)")
    addresses = data.get("addresses")
    if not isinstance(addresses, list):
        raise SanityFailure("SANITY FAIL: previous feed is corrupt (missing addresses array)")
    pairs: set[tuple[str, str]] = set()
    for row in addresses:
        if not isinstance(row, dict) or "address" not in row or "chain" not in row:
            raise SanityFailure("SANITY FAIL: previous feed is corrupt (bad address row)")
        pairs.add(pair_key(str(row["chain"]), str(row["address"])))
    return pairs


def assert_sane(result: ExtractResult, previous_pairs: set[tuple[str, str]] | None) -> None:
    """Raise SanityFailure if the extract is too small, malformed, or a sharp drop."""
    unique = result.unique
    count = len(unique)
    if count < MIN_UNIQUE_COUNT:
        raise SanityFailure(
            f"SANITY FAIL: unique address count {count} is below minimum {MIN_UNIQUE_COUNT}"
        )

    bad = invalid_records(unique)
    if bad and (len(bad) / count) > MAX_INVALID_RATIO:
        sample = ", ".join(f"{r.chain}:{r.address[:18]}" for r in bad[:5])
        raise SanityFailure(
            f"SANITY FAIL: {len(bad)}/{count} addresses fail format checks "
            f"(max {MAX_INVALID_RATIO:.0%}). sample={sample}"
        )

    if not previous_pairs:
        return

    prev_count = len(previous_pairs)
    floor = int(prev_count * (1.0 - MAX_DROP_RATIO))
    if count < floor:
        raise SanityFailure(
            f"SANITY FAIL: unique count dropped from {prev_count} to {count} "
            f"(more than {MAX_DROP_RATIO:.0%}); refusing to overwrite last good file"
        )

    new_pairs = result_pairs(result)
    removed = previous_pairs - new_pairs
    if prev_count and (len(removed) / prev_count) > MAX_DROP_RATIO:
        raise SanityFailure(
            f"SANITY FAIL: removed {len(removed)}/{prev_count} previous "
            f"(chain, address) pairs (more than {MAX_DROP_RATIO:.0%}); "
            "refusing to overwrite last good file"
        )
