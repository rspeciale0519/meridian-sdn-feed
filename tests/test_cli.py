from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from helpers import eth_record, fake_fetch, read_fixture
from sdn_feed.cli import extract, run
from sdn_feed.constants import CSL_JSON_URL, OFAC_SDN_XML_URL
from sdn_feed.fetch import FetchError


def _xml_with_eth(count: int, start: int = 1) -> str:
    extra = []
    for i in range(start, start + count):
        extra.append(
            f"""
  <sdnEntry>
    <uid>{200000 + i}</uid>
    <lastName>PAD {i}</lastName>
    <idList>
      <id>
        <uid>{i}</uid>
        <idType>Digital Currency Address - ETH</idType>
        <idNumber>0x{i:040x}</idNumber>
      </id>
    </idList>
  </sdnEntry>"""
        )
    base = read_fixture("sdn_sample.xml")
    return base.replace("</sdnList>", "".join(extra) + "\n</sdnList>")


def _healthy_xml() -> str:
    return _xml_with_eth(910)


def _healthy_csl(count: int = 910, start: int = 1) -> str:
    results = []
    for i in range(start, start + count):
        results.append(
            {
                "id": str(i),
                "entity_number": str(i),
                "source": "Specially Designated Nationals (SDN) - Treasury Department",
                "name": f"PAD {i}",
                "ids": [
                    {
                        "type": "Digital Currency Address - ETH",
                        "number": f"0x{i:040x}",
                    }
                ],
            }
        )
    return json.dumps({"results": results})


def _previous_doc(count: int) -> dict:
    return {
        "count": count,
        "addresses": [eth_record(i).as_payload() for i in range(count)],
    }


class CliTests(unittest.TestCase):
    def test_falls_back_to_csl_when_xml_fails(self) -> None:
        fetcher = fake_fetch(
            {
                OFAC_SDN_XML_URL: FetchError("xml down"),
                CSL_JSON_URL: read_fixture("csl_sample.json"),
            }
        )
        result = extract(fetcher)
        self.assertEqual(result.source, "ita_csl_json")
        self.assertEqual(result.unique_count, 3)

    def test_prefers_ofac_xml(self) -> None:
        fetcher = fake_fetch(
            {
                OFAC_SDN_XML_URL: read_fixture("sdn_sample.xml"),
                CSL_JSON_URL: FetchError("csl unused for parse-only win"),
            }
        )
        result = extract(fetcher)
        self.assertEqual(result.source, "ofac_sdn_xml")

    def test_all_sources_fail_loudly(self) -> None:
        fetcher = fake_fetch(
            {
                OFAC_SDN_XML_URL: FetchError("xml"),
                CSL_JSON_URL: FetchError("csl"),
            }
        )
        with self.assertRaises(FetchError) as ctx:
            extract(fetcher)
        self.assertIn("ALL SOURCES FAILED", str(ctx.exception))

    def test_xml_parse_error_falls_to_csl(self) -> None:
        fetcher = fake_fetch(
            {
                OFAC_SDN_XML_URL: "<sdnList><sdnEntry><uid>1</uid>",
                CSL_JSON_URL: read_fixture("csl_sample.json"),
            }
        )
        result = extract(fetcher)
        self.assertEqual(result.source, "ita_csl_json")

    def test_failure_does_not_overwrite_last_good_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            good = out / "sdn-addresses.json"
            payload = json.dumps(_previous_doc(1058))
            good.write_text(payload, encoding="utf-8")
            fetcher = fake_fetch(
                {
                    OFAC_SDN_XML_URL: FetchError("xml"),
                    CSL_JSON_URL: FetchError("csl"),
                }
            )
            code = run(out, fetcher=fetcher)
            self.assertEqual(code, 2)
            self.assertEqual(good.read_text(encoding="utf-8"), payload)
            self.assertFalse((out / "last-run.json").exists())

    def test_corrupt_previous_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            good = out / "sdn-addresses.json"
            good.write_text("{not json", encoding="utf-8")
            code = run(
                out,
                fetcher=fake_fetch(
                    {
                        OFAC_SDN_XML_URL: _healthy_xml(),
                        CSL_JSON_URL: FetchError("csl"),
                    }
                ),
            )
            self.assertEqual(code, 3)
            self.assertEqual(good.read_text(encoding="utf-8"), "{not json")
            self.assertFalse((out / "last-run.json").exists())

    def test_small_xml_falls_through_to_csl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            code = run(
                out,
                fetcher=fake_fetch(
                    {
                        OFAC_SDN_XML_URL: read_fixture("sdn_sample.xml"),
                        CSL_JSON_URL: _healthy_csl(),
                    }
                ),
            )
            self.assertEqual(code, 0)
            doc = json.loads((out / "sdn-addresses.json").read_text(encoding="utf-8"))
            self.assertEqual(doc["source"], "ita_csl_json")
            self.assertGreaterEqual(doc["count"], 900)

    def test_sanity_drop_does_not_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            previous = _previous_doc(1100)
            (out / "sdn-addresses.json").write_text(json.dumps(previous), encoding="utf-8")
            before = (out / "sdn-addresses.json").read_text(encoding="utf-8")
            code = run(
                out,
                fetcher=fake_fetch(
                    {
                        OFAC_SDN_XML_URL: _xml_with_eth(910),
                        CSL_JSON_URL: FetchError("csl"),
                    }
                ),
            )
            self.assertEqual(code, 3)
            self.assertEqual((out / "sdn-addresses.json").read_text(encoding="utf-8"), before)

    def test_successful_run_writes_feed_and_heartbeat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            code = run(
                out,
                fetcher=fake_fetch(
                    {
                        OFAC_SDN_XML_URL: _healthy_xml(),
                        CSL_JSON_URL: FetchError("csl down"),
                    }
                ),
            )
            self.assertEqual(code, 0)
            doc = json.loads((out / "sdn-addresses.json").read_text(encoding="utf-8"))
            self.assertGreaterEqual(doc["count"], 900)
            self.assertEqual(doc["source"], "ofac_sdn_xml")
            heartbeat = json.loads((out / "last-run.json").read_text(encoding="utf-8"))
            self.assertEqual(heartbeat["status"], "ok")
            self.assertIn("checked_at", heartbeat)
            self.assertEqual(heartbeat["source"], "ofac_sdn_xml")
            self.assertEqual(heartbeat["payload_sha256"], doc["payload_sha256"])
            self.assertFalse(heartbeat["csl_cross_check"]["compared"])
            self.assertTrue((out / "sdn-addresses.json.sha256").is_file())

    def test_cross_check_recorded_when_both_parse(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            xml = _xml_with_eth(910)
            csl = _healthy_csl(910)
            code = run(
                out,
                fetcher=fake_fetch({OFAC_SDN_XML_URL: xml, CSL_JSON_URL: csl}),
            )
            self.assertEqual(code, 0)
            heartbeat = json.loads((out / "last-run.json").read_text(encoding="utf-8"))
            check = heartbeat["csl_cross_check"]
            self.assertTrue(check["compared"])
            self.assertGreaterEqual(check["xml_count"], 900)
            self.assertIn("mismatches", check)
            doc = json.loads((out / "sdn-addresses.json").read_text(encoding="utf-8"))
            self.assertEqual(doc["source"], "ofac_sdn_xml")


if __name__ == "__main__":
    unittest.main()
