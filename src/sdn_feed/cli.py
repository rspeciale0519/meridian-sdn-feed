"""CLI: OFAC XML → ITA CSL. Sanity per source; fail closed."""

from __future__ import annotations

import argparse
import sys
import traceback
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Callable

from sdn_feed.constants import ADDRESSES_FILENAME, CSL_JSON_URL, OFAC_SDN_XML_URL
from sdn_feed.emit import utc_now, write_feed
from sdn_feed.fetch import FetchError, fetch_url
from sdn_feed.models import ExtractResult, FetchResult, SanityFailure
from sdn_feed.parse_csl import parse_csl_json
from sdn_feed.parse_ofac import parse_sdn_xml
from sdn_feed.validate import assert_sane, load_previous_pairs, result_pairs

Fetcher = Callable[[str], FetchResult]
PARSE_ERRORS = (FetchError, ValueError, OSError, ET.ParseError)


def _try_ofac_xml(fetcher: Fetcher) -> ExtractResult:
    fetched = fetcher(OFAC_SDN_XML_URL)
    result = parse_sdn_xml(fetched.body, source_url=OFAC_SDN_XML_URL)
    result.http_last_modified = fetched.last_modified
    result.source_urls = [OFAC_SDN_XML_URL]
    return result


def _try_csl(fetcher: Fetcher) -> ExtractResult:
    fetched = fetcher(CSL_JSON_URL)
    result = parse_csl_json(fetched.body, source_url=CSL_JSON_URL)
    result.http_last_modified = fetched.last_modified
    result.source_urls = [CSL_JSON_URL]
    return result


def _parse_one(label: str, fn: Callable[[Fetcher], ExtractResult], fetcher: Fetcher) -> ExtractResult | None:
    try:
        result = fn(fetcher)
        print(
            f"parsed {label} unique={result.unique_count} entries={result.entry_count}",
            file=sys.stderr,
        )
        return result
    except PARSE_ERRORS as exc:
        print(f"WARN {label} failed: {exc}", file=sys.stderr)
        return None


def cross_check(xml_result: ExtractResult, csl_result: ExtractResult) -> dict[str, Any]:
    xml_pairs = result_pairs(xml_result)
    csl_pairs = result_pairs(csl_result)
    xml_only = len(xml_pairs - csl_pairs)
    csl_only = len(csl_pairs - xml_pairs)
    mismatches = xml_only + csl_only
    print(
        f"csl_cross_check xml={len(xml_pairs)} csl={len(csl_pairs)} "
        f"xml_only={xml_only} csl_only={csl_only} mismatches={mismatches}",
        file=sys.stderr,
    )
    return {
        "compared": True,
        "xml_count": len(xml_pairs),
        "csl_count": len(csl_pairs),
        "xml_only": xml_only,
        "csl_only": csl_only,
        "mismatches": mismatches,
    }


def parse_sources(fetcher: Fetcher = fetch_url) -> tuple[ExtractResult | None, ExtractResult | None]:
    return _parse_one("OFAC SDN.XML", _try_ofac_xml, fetcher), _parse_one(
        "ITA CSL JSON", _try_csl, fetcher
    )


def extract(fetcher: Fetcher = fetch_url) -> ExtractResult:
    """Parse-only fallback (XML then CSL). Used by tests; run() also applies sanity."""
    xml_result, csl_result = parse_sources(fetcher)
    for result in (xml_result, csl_result):
        if result is not None:
            return result
    raise FetchError("ALL SOURCES FAILED; last good file left untouched. OFAC SDN.XML and ITA CSL JSON failed")


def pick_sane(
    candidates: list[ExtractResult],
    previous_pairs: set[tuple[str, str]] | None,
) -> ExtractResult:
    errors: list[str] = []
    for result in candidates:
        try:
            assert_sane(result, previous_pairs)
            print(f"source={result.source} passed sanity unique={result.unique_count}", file=sys.stderr)
            return result
        except SanityFailure as exc:
            errors.append(f"{result.source}: {exc}")
            print(f"WARN {result.source} failed sanity: {exc}", file=sys.stderr)
    raise SanityFailure(" | ".join(errors) or "no candidate passed sanity")


def run(output_dir: Path, fetcher: Fetcher = fetch_url) -> int:
    previous_path = output_dir / ADDRESSES_FILENAME
    try:
        previous_pairs = load_previous_pairs(previous_path)
    except SanityFailure as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 3

    xml_result, csl_result = parse_sources(fetcher)
    check: dict[str, Any]
    if xml_result is not None and csl_result is not None:
        check = cross_check(xml_result, csl_result)
    elif xml_result is None and csl_result is None:
        print("ERROR ALL SOURCES FAILED; last good file left untouched.", file=sys.stderr)
        return 2
    else:
        missing = "ITA CSL JSON" if csl_result is None else "OFAC SDN.XML"
        check = {"compared": False, "reason": f"{missing} unavailable"}

    try:
        chosen = pick_sane([r for r in (xml_result, csl_result) if r is not None], previous_pairs)
    except SanityFailure as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 3

    written = write_feed(output_dir, chosen, utc_now(), cross_check=check)
    doc = written["document"]
    print(
        f"ok source={doc.get('source')} count={doc.get('count')} "
        f"sha256={doc.get('payload_sha256')} wrote={written['wrote_addresses']}",
        file=sys.stderr,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract OFAC SDN digital currency addresses into a public JSON feed."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data"),
        help="Directory for sdn-addresses.json and last-run.json (default: data)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args.output_dir)
    except Exception:  # noqa: BLE001 — fail the job loudly with a traceback
        traceback.print_exc()
        return 1
