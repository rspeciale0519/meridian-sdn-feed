# meridian-sdn-feed

Unofficial daily extract of **digital currency addresses** published on the U.S. Treasury OFAC Specially Designated Nationals (SDN) list.

This repository is a convenience feed for [Meridian](https://workers.miodiollc.com). It is **not** an official Treasury product, **not** a sanctions screening program, and **not** legal advice.

- **Official source of truth:** [OFAC Sanctions List Service](https://sanctionslist.ofac.treas.gov/Home/SdnList) / [OFAC SDN list](https://ofac.treasury.gov/). Always confirm matches against Treasury’s own files before acting.
- **No warranty.** Data may be late, incomplete, or wrong. GitHub-hosted Actions schedules can drift by hours and go idle after 60 days without a commit.
- **Operator:** MioDio LLC — `corp@miodiollc.com`

Consumers should fetch:

`https://raw.githubusercontent.com/rspeciale0519/meridian-sdn-feed/main/data/sdn-addresses.json`

Integrity: `data/sdn-addresses.json.sha256` is the SHA-256 of the sorted `addresses` array (not the whole file).

## What it extracts

OFAC tags crypto identifiers as `Digital Currency Address - <CHAIN>` (see [FAQ 563](https://ofac.treasury.gov/faqs/563)). The extractor reads those identifiers from:

1. **Primary:** `SDN.XML` at `https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.XML`
2. **Same source, less structured:** `SDN.CSV` remarks, same host
3. **Fallback:** ITA [Consolidated Screening List](https://www.trade.gov/consolidated-screening-list) JSON at `https://data.trade.gov/downloadable_consolidated_screening_list/v1/consolidated.json`, filtered to OFAC SDN entries only

If every source is unreachable or malformed, the job **fails** and does **not** overwrite the last good `data/sdn-addresses.json`.

## JSON schema (`data/sdn-addresses.json`)

| Field | Type | Meaning |
|---|---|---|
| `schema_version` | string | Document shape. Current: `"1.0"` |
| `source` | string | Which parser won: `ofac_sdn_xml`, `ofac_sdn_csv`, or `ita_csl_json` |
| `source_urls` | string[] | Official URL(s) that were parsed |
| `ofac_publish_date` | string | OFAC `Publish_Date` from the XML header (e.g. `10/28/2026`), or CSL publication stamp on fallback |
| `ofac_list_version` | string | OFAC `List_Version` when present |
| `ofac_record_count` | string | OFAC `Record_Count` (SDN entities, not crypto rows) |
| `http_last_modified` | string | HTTP `Last-Modified` of the downloaded file |
| `fetched_at` | string | UTC timestamp of the extract that last changed this file (`YYYY-MM-DDTHH:MM:SSZ`) |
| `count` | number | Unique `(chain, address)` rows |
| `entry_count` | number | Raw identifier rows before dedup (OFAC sometimes repeats an address on more than one entity) |
| `unique_address_count` | number | Distinct address strings ignoring chain (same 0x on ETH and USDT counts once) |
| `payload_sha256` | string | SHA-256 hex of the canonical JSON `addresses` array |
| `addresses` | object[] | Sorted unique rows |

Each `addresses[]` object:

| Field | Type | Meaning |
|---|---|---|
| `address` | string | Identifier exactly as published |
| `chain` | string | OFAC currency/chain code (`XBT`, `ETH`, `TRX`, …) |
| `uid` | string | SDN entity uid / entity number when present |
| `name` | string | SDN primary name when present |

The `addresses` array is sorted by `chain`, then case-insensitive `address`, then `uid`, then `name`. Object keys are sorted. Unchanged OFAC data leaves this file byte-identical; `data/last-run.json` still updates so the public-repo schedule stays alive.

## Sanity guards

A successful run commits only after:

- unique `count` is at least **900**
- address strings look valid for the labeled chain (format check, not checksum / on-chain proof)
- unique count has not dropped more than **10%** versus the file already in the repo

Failures exit non-zero and leave the previous feed in place.

## Schedule

GitHub Actions (`ubuntu-latest`) runs daily at `30 10 * * *` (about 10:30 UTC, often later) and on `workflow_dispatch`. Only the built-in `GITHUB_TOKEN` is used, with `contents: write`. No third-party Actions except `actions/checkout`, pinned to a commit SHA.

## Local use

Python 3.10+ stdlib only. No packages to install.

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 scripts/extract_sdn.py --output-dir data
```

Tests use the fixtures under `tests/fixtures/` and do not touch the network.

## License / terms

Public U.S. government list data. This extract is provided as-is by MioDio LLC for Meridian. You are responsible for how you use it.
