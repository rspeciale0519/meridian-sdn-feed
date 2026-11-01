from __future__ import annotations

import io
import unittest
from email.message import EmailMessage

from sdn_feed.fetch import FetchError, assert_allowed_url, host_allowed, read_capped


class _FakeResponse:
    def __init__(self, body: bytes, content_length: str | None = None) -> None:
        self._buf = io.BytesIO(body)
        self.headers = EmailMessage()
        if content_length is not None:
            self.headers["Content-Length"] = content_length

    def read(self, n: int = -1) -> bytes:
        return self._buf.read(n)


class FetchGuardTests(unittest.TestCase):
    def test_https_allowlist(self) -> None:
        assert_allowed_url(
            "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.XML"
        )
        assert_allowed_url(
            "https://wc2h-sls-prod-public-published.s3.us-gov-west-1.amazonaws.com/SDN.XML"
        )
        assert_allowed_url(
            "https://data.trade.gov/downloadable_consolidated_screening_list/v1/consolidated.json"
        )
        self.assertTrue(host_allowed("api.trade.gov"))
        with self.assertRaises(FetchError):
            assert_allowed_url("http://sanctionslistservice.ofac.treas.gov/SDN.XML")
        with self.assertRaises(FetchError):
            assert_allowed_url("https://evil.example/SDN.XML")
        with self.assertRaises(FetchError):
            assert_allowed_url("https://attacker.s3.us-gov-west-1.amazonaws.com/x")
        # Same bucket name in commercial / other regions must not match.
        with self.assertRaises(FetchError):
            assert_allowed_url(
                "https://wc2h-sls-prod-public-published.s3.amazonaws.com/SDN.XML"
            )
        with self.assertRaises(FetchError):
            assert_allowed_url(
                "https://wc2h-sls-prod-public-published.s3.us-east-1.amazonaws.com/SDN.XML"
            )
        self.assertFalse(
            host_allowed("wc2h-sls-prod-public-published.s3.us-west-2.amazonaws.com")
        )

    def test_size_cap(self) -> None:
        raw = read_capped(_FakeResponse(b"abc"), limit=10)
        self.assertEqual(raw, b"abc")
        with self.assertRaises(FetchError):
            read_capped(_FakeResponse(b"abcdefghijk"), limit=10)
        with self.assertRaises(FetchError):
            read_capped(_FakeResponse(b"abc", content_length="99999"), limit=10)


if __name__ == "__main__":
    unittest.main()
