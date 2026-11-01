from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from helpers import eth_record
from sdn_feed.models import AddressRecord, ExtractResult, SanityFailure, pair_key
from sdn_feed.validate import assert_sane, load_previous_pairs, looks_valid


def _result(records: list[AddressRecord]) -> ExtractResult:
    return ExtractResult(source="ofac_sdn_xml", source_urls=[], entries=records, unique=records)


def _pairs(records: list[AddressRecord]) -> set[tuple[str, str]]:
    return {pair_key(r.chain, r.address) for r in records}


class FormatTests(unittest.TestCase):
    def test_known_chain_shapes(self) -> None:
        self.assertTrue(looks_valid(AddressRecord("1BoatSLRHtKNngkdXEeobR76b53LETtpyT", "XBT")))
        self.assertTrue(looks_valid(AddressRecord("0x000000000000000000000000000000000000dEaD", "ETH")))
        self.assertTrue(looks_valid(AddressRecord("TXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx1", "TRX")))
        self.assertTrue(looks_valid(AddressRecord("rPEPPER7kfTD9w2To4CQk6UCfuHM9c6GDY", "XRP")))
        self.assertTrue(looks_valid(AddressRecord("bnb136ns6lfw4zs5hg4n85vdthaad7hq5m4gtkgf23", "BNB")))
        self.assertTrue(
            looks_valid(
                AddressRecord(
                    "5be5543ff73456ab9f2d207887e2af87322c651ea1a873c5b25b7ffae456c320",
                    "XMR",
                )
            )
        )
        self.assertFalse(looks_valid(AddressRecord("not-an-address", "ETH")))
        self.assertFalse(looks_valid(AddressRecord("0xdead", "ETH")))
        self.assertFalse(looks_valid(AddressRecord("1Boat with space", "XBT")))


class SanityTests(unittest.TestCase):
    def test_rejects_low_count(self) -> None:
        with self.assertRaises(SanityFailure) as ctx:
            assert_sane(_result([eth_record(i) for i in range(10)]), None)
        self.assertIn("below minimum", str(ctx.exception))

    def test_rejects_invalid_ratio(self) -> None:
        records = [eth_record(i) for i in range(920)]
        records[0] = AddressRecord("!!!", "ETH", uid="0", name="bad")
        records[1] = AddressRecord("???", "ETH", uid="1", name="bad")
        records[2] = AddressRecord("###", "ETH", uid="2", name="bad")
        for i in range(3, 30):
            records[i] = AddressRecord(f"bad{i}", "ETH", uid=str(i), name="bad")
        with self.assertRaises(SanityFailure) as ctx:
            assert_sane(_result(records), None)
        self.assertIn("fail format", str(ctx.exception))

    def test_rejects_sharp_count_drop(self) -> None:
        records = [eth_record(i) for i in range(910)]
        previous = _pairs([eth_record(i) for i in range(1100)])
        with self.assertRaises(SanityFailure) as ctx:
            assert_sane(_result(records), previous)
        self.assertIn("dropped", str(ctx.exception))

    def test_rejects_set_removals_even_when_count_holds(self) -> None:
        previous = [eth_record(i) for i in range(1000)]
        replacement = [eth_record(i) for i in range(200, 1200)]
        with self.assertRaises(SanityFailure) as ctx:
            assert_sane(_result(replacement), _pairs(previous))
        self.assertIn("removed", str(ctx.exception))

    def test_accepts_healthy_extract(self) -> None:
        records = [eth_record(i) for i in range(950)]
        previous = _pairs([eth_record(i) for i in range(1000)])
        assert_sane(_result(records), previous)

    def test_missing_previous_is_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sdn-addresses.json"
            self.assertIsNone(load_previous_pairs(path))

    def test_corrupt_previous_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sdn-addresses.json"
            path.write_text("{bad", encoding="utf-8")
            with self.assertRaises(SanityFailure) as ctx:
                load_previous_pairs(path)
            self.assertIn("unreadable", str(ctx.exception))
            path.write_text(json.dumps({"count": 1058, "addresses": ["keep-me"]}), encoding="utf-8")
            with self.assertRaises(SanityFailure) as ctx:
                load_previous_pairs(path)
            self.assertIn("corrupt", str(ctx.exception))

    def test_loads_previous_pairs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sdn-addresses.json"
            rows = [eth_record(i).as_payload() for i in range(3)]
            path.write_text(json.dumps({"count": 3, "addresses": rows}), encoding="utf-8")
            pairs = load_previous_pairs(path)
            self.assertEqual(len(pairs or []), 3)


if __name__ == "__main__":
    unittest.main()
