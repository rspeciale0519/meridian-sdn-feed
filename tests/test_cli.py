from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from helpers import eth_record, fake_fetch, read_fixture
from sdn_feed.cli import extract, run
from sdn_feed.constants import CSL_JSON_URL, OFAC_SDN_CSV_URL, OFAC_SDN_XML_URL
from sdn_feed.fetch import FetchError
from sdn_feed.models import ExtractResult
from sdn_feed.parse_ofac import unique_records


def _healthy_xml() -> str:
    """Fixture XML plus enough dummy ETH ids to clear the 900-address floor."""
    extra = []
    for i in range(1, 910):
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


class CliTests(unittest.TestCase):
    def test_falls_back_to_csl_when_ofac_fails(self) -> None:
        fetcher = fake_fetch(
            {
                OFAC_SDN_XML_URL: FetchError("xml down"),
                OFAC_SDN_CSV_URL: FetchError("csv down"),
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
                OFAC_SDN_CSV_URL: RuntimeError("csv should not be fetched"),
                CSL_JSON_URL: RuntimeError("csl should not be fetched"),
            }
        )
        result = extract(fetcher)
        self.assertEqual(result.source, "ofac_sdn_xml")

    def test_all_sources_fail_loudly(self) -> None:
        fetcher = fake_fetch(
            {
                OFAC_SDN_XML_URL: FetchError("xml"),
                OFAC_SDN_CSV_URL: FetchError("csv"),
                CSL_JSON_URL: FetchError("csl"),
            }
        )
        with self.assertRaises(FetchError) as ctx:
            extract(fetcher)
        self.assertIn("ALL SOURCES FAILED", str(ctx.exception))

    def test_failure_does_not_overwrite_last_good_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            good = out / "sdn-addresses.json"
            good.write_text('{"count": 1058, "addresses": ["keep-me"]}\n', encoding="utf-8")
            fetcher = fake_fetch(
                {
                    OFAC_SDN_XML_URL: FetchError("xml"),
                    OFAC_SDN_CSV_URL: FetchError("csv"),
                    CSL_JSON_URL: FetchError("csl"),
                }
            )
            code = run(out, fetcher=fetcher)
            self.assertEqual(code, 2)
            self.assertEqual(good.read_text(encoding="utf-8"), '{"count": 1058, "addresses": ["keep-me"]}\n')
            self.assertFalse((out / "last-run.json").exists())

    def test_sanity_drop_does_not_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            previous = [eth_record(i).as_payload() for i in range(1100)]
            (out / "sdn-addresses.json").write_text(
                json.dumps({"count": 1100, "addresses": previous}),
                encoding="utf-8",
            )
            before = (out / "sdn-addresses.json").read_text(encoding="utf-8")

            def _fetcher(_url: str):
                raise AssertionError("run() should not fetch after we stub extract")

            small = [eth_record(i) for i in range(910)]
            stub = ExtractResult(
                source="ofac_sdn_xml",
                source_urls=[OFAC_SDN_XML_URL],
                entries=small,
                unique=unique_records(small),
            )

            from sdn_feed import cli as cli_mod

            original = cli_mod.extract
            cli_mod.extract = lambda fetcher=None: stub  # type: ignore[assignment]
            try:
                code = run(out, fetcher=_fetcher)
            finally:
                cli_mod.extract = original
            self.assertEqual(code, 3)
            self.assertEqual((out / "sdn-addresses.json").read_text(encoding="utf-8"), before)

    def test_successful_run_writes_feed_and_heartbeat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            code = run(out, fetcher=fake_fetch({OFAC_SDN_XML_URL: _healthy_xml()}))
            self.assertEqual(code, 0)
            doc = json.loads((out / "sdn-addresses.json").read_text(encoding="utf-8"))
            self.assertGreaterEqual(doc["count"], 900)
            self.assertEqual(doc["source"], "ofac_sdn_xml")
            heartbeat = json.loads((out / "last-run.json").read_text(encoding="utf-8"))
            self.assertEqual(heartbeat["status"], "ok")
            self.assertTrue((out / "sdn-addresses.json.sha256").is_file())


if __name__ == "__main__":
    unittest.main()
