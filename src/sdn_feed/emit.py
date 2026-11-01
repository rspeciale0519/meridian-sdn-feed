"""Deterministic JSON + sha256 sidecar + schedule-keeping heartbeat."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sdn_feed.constants import (
    ADDRESSES_FILENAME,
    HEARTBEAT_FILENAME,
    SCHEMA_VERSION,
    SHA256_FILENAME,
)
from sdn_feed.models import AddressRecord, ExtractResult, record_sort_key

JSON_SEP = (",", ":")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def payload_records(records: list[AddressRecord]) -> list[dict[str, str]]:
    return [r.as_payload() for r in sorted(records, key=record_sort_key)]


def payload_sha256(records: list[AddressRecord]) -> str:
    blob = json.dumps(
        payload_records(records),
        ensure_ascii=False,
        separators=JSON_SEP,
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def build_document(result: ExtractResult, fetched_at: str) -> dict[str, Any]:
    unique = payload_records(result.unique)
    return {
        "schema_version": SCHEMA_VERSION,
        "source": result.source,
        "source_urls": list(result.source_urls),
        "ofac_publish_date": result.ofac_publish_date,
        "ofac_list_version": result.ofac_list_version,
        "ofac_record_count": result.ofac_record_count,
        "http_last_modified": result.http_last_modified,
        "fetched_at": fetched_at,
        "count": len(unique),
        "entry_count": result.entry_count,
        "unique_address_count": len({row["address"] for row in unique}),
        "payload_sha256": payload_sha256(result.unique),
        "addresses": unique,
    }


def dump_json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _identity_fields(doc: dict[str, Any]) -> tuple[Any, ...]:
    # http_last_modified and fetched_at are excluded so a quiet OFAC week
    # leaves sdn-addresses.json byte-identical. Freshness lives in last-run.json.
    return (
        doc.get("payload_sha256"),
        doc.get("source"),
        tuple(doc.get("source_urls") or []),
        doc.get("ofac_publish_date"),
        doc.get("ofac_list_version"),
        doc.get("ofac_record_count"),
        doc.get("count"),
        doc.get("unique_address_count"),
    )


def write_feed(
    output_dir: Path,
    result: ExtractResult,
    checked_at: str,
    *,
    cross_check: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write addresses JSON only when OFAC payload identity changes.

    last-run.json is always rewritten on a successful call so consumers can
    see checked_at even when the address list did not change.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    addresses_path = output_dir / ADDRESSES_FILENAME
    sha_path = output_dir / SHA256_FILENAME
    heartbeat_path = output_dir / HEARTBEAT_FILENAME

    document = build_document(result, checked_at)
    previous: dict[str, Any] | None = None
    if addresses_path.is_file():
        try:
            previous = json.loads(addresses_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            previous = None

    wrote_addresses = True
    if previous is not None and _identity_fields(previous) == _identity_fields(document):
        document = previous
        wrote_addresses = False
    else:
        text = dump_json(document)
        addresses_path.write_text(text, encoding="utf-8")
        sha_path.write_text(document["payload_sha256"] + "\n", encoding="utf-8")

    heartbeat = {
        "checked_at": checked_at,
        "status": "ok" if wrote_addresses else "unchanged",
        "source": result.source,
        "payload_sha256": document.get("payload_sha256"),
        "count": document.get("count"),
        "ofac_publish_date": document.get("ofac_publish_date"),
        "addresses_written": wrote_addresses,
        "csl_cross_check": cross_check or {"compared": False, "reason": "not attempted"},
    }
    heartbeat_path.write_text(dump_json(heartbeat), encoding="utf-8")
    return {"document": document, "wrote_addresses": wrote_addresses, "heartbeat": heartbeat}
