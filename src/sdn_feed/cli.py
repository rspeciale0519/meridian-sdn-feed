"""CLI: OFAC XML → OFAC CSV → ITA CSL. Fail closed; do not overwrite last good file."""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path
from typing import Callable

from sdn_feed.constants import (
    ADDRESSES_FILENAME,
    CSL_JSON_URL,
    OFAC_SDN_CSV_URL,
    OFAC_SDN_XML_URL,
)
from sdn_feed.emit import utc_now, write_feed
from sdn_feed.fetch import FetchError, fetch_url
from sdn_feed.models import FetchResult, SanityFailure
from sdn_feed.parse_csl import parse_csl_json
from sdn_feed.parse_ofac import parse_sdn_csv, parse_sdn_xml
from sdn_feed.validate import assert_sane, load_previous_count

Fetcher = Callable[[str], FetchResult]


def _try_ofac_xml(fetcher: Fetcher) -> ExtractResult:
    fetched = fetcher(OFAC_SDN_XML_URL)
    result = parse_sdn_xml(fetched.body, source_url=OFAC_SDN_XML_URL)
    result.http_last_modified = fetched.last_modified
    if OFAC_SDN_XML_URL not in result.source_urls:
        result.source_urls = [OFAC_SDN_XML_URL]
    return result


def _try_ofac_csv(fetcher: Fetcher) -> ExtractResult:
    fetched = fetcher(OFAC_SDN_CSV_URL)
    result = parse_sdn_csv(fetched.body, source_url=OFAC_SDN_CSV_URL)
    result.http_last_modified = fetched.last_modified
    if OFAC_SDN_CSV_URL not in result.source_urls:
        result.source_urls = [OFAC_SDN_CSV_URL]
    return result


def _try_csl(fetcher: Fetcher) -> ExtractResult:
    fetched = fetcher(CSL_JSON_URL)
    result = parse_csl_json(fetched.body, source_url=CSL_JSON_URL)
    result.http_last_modified = fetched.last_modified
    if CSL_JSON_URL not in result.source_urls:
        result.source_urls = [CSL_JSON_URL]
    return result


def extract(fetcher: Fetcher = fetch_url) -> ExtractResult:
    errors: list[str] = []
    attempts = (
        ("OFAC SDN.XML", _try_ofac_xml),
        ("OFAC SDN.CSV", _try_ofac_csv),
        ("ITA CSL JSON", _try_csl),
    )
    for label, fn in attempts:
        try:
            result = fn(fetcher)
            print(f"source={result.source} unique={result.unique_count} entries={result.entry_count}", file=sys.stderr)
            return result
        except (FetchError, ValueError, OSError) as exc:
            errors.append(f"{label}: {exc}")
            print(f"WARN {label} failed: {exc}", file=sys.stderr)
    joined = " | ".join(errors) or "all sources failed"
    raise FetchError(f"ALL SOURCES FAILED; last good file left untouched. {joined}")


def run(output_dir: Path, fetcher: Fetcher = fetch_url) -> int:
    previous_path = output_dir / ADDRESSES_FILENAME
    previous_count = load_previous_count(previous_path)
    try:
        result = extract(fetcher)
    except FetchError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 2

    try:
        assert_sane(result, previous_count)
    except SanityFailure as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 3

    written = write_feed(output_dir, result, utc_now())
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
