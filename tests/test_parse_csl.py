from __future__ import annotations

import unittest

from helpers import read_fixture
from sdn_feed.parse_csl import parse_csl_json


class ParseCslTests(unittest.TestCase):
    def test_filters_to_ofac_sdn_only(self) -> None:
        result = parse_csl_json(read_fixture("csl_sample.json"), source_url="https://example.test/csl.json")
        self.assertEqual(result.source, "ita_csl_json")
        self.assertEqual(result.ofac_publish_date, "2026-10-28T14:03:02Z")
        addresses = {r.address for r in result.entries}
        self.assertIn("1BoatSLRHtKNngkdXEeobR76b53LETtpyT", addresses)
        self.assertIn("0x000000000000000000000000000000000000dEaD", addresses)
        self.assertIn("TXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx1", addresses)
        self.assertNotIn("0x1111111111111111111111111111111111111111", addresses)
        self.assertEqual(result.unique_count, 3)

    def test_accepts_flat_ids_string(self) -> None:
        text = """
        {"results": [{
          "source": "Specially Designated Nationals (SDN) - Treasury Department",
          "entity_number": "42",
          "name": "FLAT",
          "ids": "Digital Currency Address - XBT, 1BoatSLRHtKNngkdXEeobR76b53LETtpyT; Passport, 1"
        }]}
        """
        result = parse_csl_json(text)
        self.assertEqual(result.unique_count, 1)
        self.assertEqual(result.unique[0].chain, "XBT")

    def test_rejects_malformed_and_empty(self) -> None:
        with self.assertRaises(ValueError):
            parse_csl_json("{not json")
        with self.assertRaises(ValueError):
            parse_csl_json('{"results": []}')
        with self.assertRaises(ValueError):
            parse_csl_json(
                '{"results": [{"source": "Denied Persons List", "ids": '
                '[{"type": "Digital Currency Address - ETH", "number": "0xabc"}]}]}'
            )


if __name__ == "__main__":
    unittest.main()
