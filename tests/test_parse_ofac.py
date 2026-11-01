from __future__ import annotations

import unittest

from helpers import eth_record, read_fixture
from sdn_feed.parse_ofac import parse_sdn_csv, parse_sdn_xml, unique_records


class ParseSdnXmlTests(unittest.TestCase):
    def test_extracts_addresses_and_publish_date(self) -> None:
        result = parse_sdn_xml(read_fixture("sdn_sample.xml"), source_url="https://example.test/SDN.XML")
        self.assertEqual(result.source, "ofac_sdn_xml")
        self.assertEqual(result.ofac_publish_date, "10/28/2026")
        self.assertEqual(result.ofac_record_count, "4")
        self.assertEqual(result.ofac_list_version, "SDN")
        self.assertEqual(result.entry_count, 4)
        self.assertEqual(result.unique_count, 3)
        chains = {r.chain for r in result.entries}
        self.assertEqual(chains, {"XBT", "ETH", "TRX"})
        names = {r.uid: r.name for r in result.entries}
        self.assertEqual(names["999001"], "EXAMPLE CYBER ENTITY")
        self.assertEqual(names["999002"], "EXAMPLE PERSON, ALICE")

    def test_ignores_non_crypto_ids(self) -> None:
        result = parse_sdn_xml(read_fixture("sdn_sample.xml"))
        self.assertFalse(any(r.address == "AB1234567" for r in result.entries))
        self.assertFalse(any(r.uid == "999003" for r in result.entries))

    def test_rejects_empty_and_malformed(self) -> None:
        with self.assertRaises(ValueError):
            parse_sdn_xml("")
        with self.assertRaises(ValueError):
            parse_sdn_xml("<html>not sdn</html>")
        with self.assertRaises(ValueError):
            parse_sdn_xml("<sdnList><sdnEntry><uid>1</uid></sdnEntry></sdnList>")


class ParseSdnCsvTests(unittest.TestCase):
    def test_extracts_from_remarks(self) -> None:
        result = parse_sdn_csv(read_fixture("sdn_sample.csv"), source_url="https://example.test/SDN.CSV")
        self.assertEqual(result.source, "ofac_sdn_csv")
        self.assertEqual(result.entry_count, 3)
        self.assertEqual({r.chain for r in result.entries}, {"XBT", "ETH", "TRX"})
        self.assertEqual(result.unique[0].uid, "999001")

    def test_rejects_empty(self) -> None:
        with self.assertRaises(ValueError):
            parse_sdn_csv("ent_num,SDN_Name,Remarks\n1,FOO,no crypto here\n")


class UniqueTests(unittest.TestCase):
    def test_sorted_and_deduped(self) -> None:
        rows = [
            eth_record(2, uid="20", name="B"),
            eth_record(1, uid="10", name="A"),
            eth_record(2, uid="5", name="A"),
        ]
        unique = unique_records(rows)
        self.assertEqual([r.address for r in unique], [eth_record(1).address, eth_record(2).address])
        self.assertEqual(unique[1].uid, "5")


if __name__ == "__main__":
    unittest.main()
