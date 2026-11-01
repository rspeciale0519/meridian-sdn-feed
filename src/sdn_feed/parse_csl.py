"""Parse ITA Consolidated Screening List JSON for OFAC SDN crypto IDs."""

from __future__ import annotations

import json
from typing import Any

from sdn_feed.constants import CRYPTO_ID_PREFIX, SDN_SOURCE_MARKERS
from sdn_feed.models import AddressRecord, ExtractResult
from sdn_feed.parse_ofac import unique_records


def _is_sdn_source(source: str) -> bool:
    lowered = (source or "").strip().lower()
    if not lowered or "non-sdn" in lowered:
        return False
    if lowered == "sdn" or lowered.startswith("sdn ") or lowered.startswith("sdn-"):
        return True
    return any(marker in lowered for marker in SDN_SOURCE_MARKERS)


def _chain_from_type(id_type: str) -> str:
    rest = id_type[len(CRYPTO_ID_PREFIX) :].strip()
    if rest.startswith("-"):
        rest = rest[1:].strip()
    return rest.upper()


def _iter_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        for key in ("results", "data", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [r for r in value if isinstance(r, dict)]
        if "ids" in payload or "identifiers" in payload:
            return [payload]
        return []
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    return []


def _id_pairs(record: dict[str, Any]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    ids = record.get("ids") or record.get("identifiers") or []
    if isinstance(ids, str):
        # Older flat "Digital Currency Address - XBT, 1abc; ..." column.
        for part in ids.split(";"):
            part = part.strip()
            if CRYPTO_ID_PREFIX not in part:
                continue
            if "," in part:
                typ, num = part.split(",", 1)
            else:
                bits = part.rsplit(" ", 1)
                if len(bits) != 2:
                    continue
                typ, num = bits
            pairs.append((typ.strip(), num.strip()))
        return pairs

    if not isinstance(ids, list):
        return pairs
    for item in ids:
        if not isinstance(item, dict):
            continue
        typ = str(item.get("type") or item.get("scheme") or "").strip()
        num = str(item.get("number") or item.get("value") or "").strip()
        if typ.startswith(CRYPTO_ID_PREFIX) and num:
            pairs.append((typ, num))
    return pairs


def parse_csl_json(text: str, *, source_url: str = "") -> ExtractResult:
    if not text or not text.strip():
        raise ValueError("ITA CSL JSON body is empty")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"ITA CSL JSON is malformed: {exc}") from exc

    records = _iter_records(payload)
    if not records:
        raise ValueError("ITA CSL JSON has no result records")

    entries: list[AddressRecord] = []
    for record in records:
        source = str(record.get("source") or record.get("source_name") or "")
        if not _is_sdn_source(source):
            continue
        uid = str(
            record.get("entity_number")
            or record.get("id")
            or record.get("_id")
            or ""
        ).strip()
        name = str(record.get("name") or record.get("primary_name") or "").strip()
        for typ, number in _id_pairs(record):
            entries.append(
                AddressRecord(
                    address=number,
                    chain=_chain_from_type(typ),
                    uid=uid,
                    name=name,
                )
            )

    if not entries:
        raise ValueError("ITA CSL JSON contained no OFAC SDN digital currency addresses")

    return ExtractResult(
        source="ita_csl_json",
        source_urls=[source_url] if source_url else [],
        ofac_publish_date=str(
            payload.get("published_at")
            or payload.get("publication_date")
            or payload.get("as_of")
            or ""
        )
        if isinstance(payload, dict)
        else "",
        entries=entries,
        unique=unique_records(entries),
    )
