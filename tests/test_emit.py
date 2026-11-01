from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from helpers import read_fixture
from sdn_feed.emit import build_document, payload_sha256, write_feed
from sdn_feed.parse_ofac import parse_sdn_xml


class EmitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.result = parse_sdn_xml(read_fixture("sdn_sample.xml"), source_url="https://example.test/SDN.XML")
        self.result.http_last_modified = "Wed, 28 Oct 2026 14:03:02 GMT"

    def test_deterministic_payload_hash(self) -> None:
        first = payload_sha256(self.result.unique)
        shuffled = list(reversed(self.result.unique))
        self.assertEqual(first, payload_sha256(shuffled))

    def test_document_fields(self) -> None:
        doc = build_document(self.result, "2026-11-01T03:50:00Z")
        self.assertEqual(doc["schema_version"], "1.0")
        self.assertEqual(doc["source"], "ofac_sdn_xml")
        self.assertEqual(doc["ofac_publish_date"], "10/28/2026")
        self.assertEqual(doc["count"], 3)
        self.assertEqual(doc["entry_count"], 4)
        self.assertEqual(doc["unique_address_count"], 3)
        self.assertEqual(doc["payload_sha256"], payload_sha256(self.result.unique))
        chains = [row["chain"] for row in doc["addresses"]]
        self.assertEqual(chains, sorted(chains))

    def test_unchanged_data_keeps_identical_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            first = write_feed(out, self.result, "2026-11-01T00:00:00Z")
            text_a = (out / "sdn-addresses.json").read_text(encoding="utf-8")
            self.result.http_last_modified = "Thu, 29 Oct 2026 00:00:00 GMT"
            second = write_feed(out, self.result, "2026-11-01T12:00:00Z")
            text_b = (out / "sdn-addresses.json").read_text(encoding="utf-8")
            self.assertTrue(first["wrote_addresses"])
            self.assertFalse(second["wrote_addresses"])
            self.assertEqual(text_a, text_b)
            heartbeat = json.loads((out / "last-run.json").read_text(encoding="utf-8"))
            self.assertEqual(heartbeat["status"], "unchanged")
            self.assertEqual(heartbeat["checked_at"], "2026-11-01T12:00:00Z")
            self.assertEqual(heartbeat["source"], "ofac_sdn_xml")
            self.assertEqual(heartbeat["payload_sha256"], first["document"]["payload_sha256"])
            sha = (out / "sdn-addresses.json.sha256").read_text(encoding="utf-8").strip()
            self.assertEqual(sha, first["document"]["payload_sha256"])


if __name__ == "__main__":
    unittest.main()
