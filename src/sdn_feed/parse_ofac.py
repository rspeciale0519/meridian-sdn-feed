"""Parse OFAC SDN.XML (preferred) and SDN.CSV digital-currency identifiers."""

from __future__ import annotations

import csv
import io
import re
import xml.etree.ElementTree as ET

from sdn_feed.constants import CRYPTO_ID_PREFIX
from sdn_feed.models import AddressRecord, ExtractResult

# Remarks in SDN.CSV look like: "Digital Currency Address - XBT 1abc...; ..."
CSV_ID_RE = re.compile(
    r"Digital Currency Address\s*-\s*([A-Z0-9]+)\s+([^\s;]+)",
    re.IGNORECASE,
)


def _entity_name(entry: ET.Element) -> str:
    last = (entry.findtext("{*}lastName") or "").strip()
    first = (entry.findtext("{*}firstName") or "").strip()
    if first and last:
        return f"{last}, {first}"
    return last or first


def _chain_from_id_type(id_type: str) -> str:
    rest = id_type[len(CRYPTO_ID_PREFIX) :].strip()
    if rest.startswith("-"):
        rest = rest[1:].strip()
    return rest.upper()


def parse_sdn_xml(xml_text: str, *, source_url: str = "") -> ExtractResult:
    """Extract Digital Currency Address identifiers from classic SDN.XML.

    Uses ElementPath (`iterfind`) so the default OFAC namespace is honoured.
    `Element.iter("{*}sdnEntry")` silently returns nothing on this export.
    """
    if not xml_text or not xml_text.strip():
        raise ValueError("OFAC SDN XML body is empty")
    if "<sdnEntry" not in xml_text:
        raise ValueError("OFAC SDN XML is malformed: no <sdnEntry> elements")

    root = ET.fromstring(xml_text)
    result = ExtractResult(
        source="ofac_sdn_xml",
        source_urls=[source_url] if source_url else [],
    )

    info = root.find("{*}publshInformation")
    if info is not None:
        result.ofac_publish_date = (info.findtext("{*}Publish_Date") or "").strip()
        result.ofac_record_count = (info.findtext("{*}Record_Count") or "").strip()
        result.ofac_list_version = (info.findtext("{*}List_Version") or "").strip()

    entries: list[AddressRecord] = []
    for sdn_entry in root.iterfind("{*}sdnEntry"):
        uid = (sdn_entry.findtext("{*}uid") or "").strip()
        name = _entity_name(sdn_entry)
        for id_el in sdn_entry.iterfind(".//{*}id"):
            id_type = (id_el.findtext("{*}idType") or "").strip()
            if not id_type.startswith(CRYPTO_ID_PREFIX):
                continue
            address = (id_el.findtext("{*}idNumber") or "").strip()
            if not address:
                result.skipped_blank += 1
                continue
            entries.append(
                AddressRecord(
                    address=address,
                    chain=_chain_from_id_type(id_type),
                    uid=uid,
                    name=name,
                )
            )

    if not entries:
        raise ValueError("OFAC SDN XML contained no digital currency addresses")

    result.entries = entries
    result.unique = unique_records(entries)
    return result


def parse_sdn_csv(csv_text: str, *, source_url: str = "") -> ExtractResult:
    """Best-effort extract from SDN.CSV remarks (less structured than XML)."""
    if not csv_text or not csv_text.strip():
        raise ValueError("OFAC SDN CSV body is empty")

    # Skip a leading header that is not the column row (some exports prepend notes).
    sample = csv_text.lstrip("\ufeff")
    reader = csv.reader(io.StringIO(sample))
    rows = list(reader)
    if not rows:
        raise ValueError("OFAC SDN CSV has no rows")

    header = [c.strip() for c in rows[0]]
    header_l = [c.lower() for c in header]
    try:
        remarks_i = header_l.index("remarks")
    except ValueError:
        remarks_i = len(header) - 1
    try:
        uid_i = next(i for i, c in enumerate(header_l) if c in {"ent_num", "uid", "entnum"})
    except StopIteration:
        uid_i = 0
    try:
        name_i = next(
            i for i, c in enumerate(header_l) if c in {"sdn_name", "name", "sdnname"}
        )
    except StopIteration:
        name_i = 1 if len(header) > 1 else 0

    entries: list[AddressRecord] = []
    for row in rows[1:]:
        if not row:
            continue
        remarks = row[remarks_i] if remarks_i < len(row) else " ".join(row)
        uid = row[uid_i].strip() if uid_i < len(row) else ""
        name = row[name_i].strip() if name_i < len(row) else ""
        for match in CSV_ID_RE.finditer(remarks):
            entries.append(
                AddressRecord(
                    address=match.group(2).strip(),
                    chain=match.group(1).strip().upper(),
                    uid=uid,
                    name=name,
                )
            )

    if not entries:
        raise ValueError("OFAC SDN CSV contained no digital currency addresses")

    return ExtractResult(
        source="ofac_sdn_csv",
        source_urls=[source_url] if source_url else [],
        entries=entries,
        unique=unique_records(entries),
    )


def _uid_sort_key(uid: str) -> tuple[int, int, str]:
    if uid.isdigit():
        return (0, int(uid), uid)
    return (1, 0, uid)


def unique_records(entries: list[AddressRecord]) -> list[AddressRecord]:
    """Dedup by (chain, address); keep the lowest uid then name for stability."""
    best: dict[tuple[str, str], AddressRecord] = {}
    for rec in entries:
        key = (rec.chain.upper(), rec.address)
        prev = best.get(key)
        if prev is None or (_uid_sort_key(rec.uid), rec.name) < (
            _uid_sort_key(prev.uid),
            prev.name,
        ):
            best[key] = rec
    return sorted(
        best.values(),
        key=lambda r: (r.chain.upper(), r.address.lower(), _uid_sort_key(r.uid), r.name),
    )
