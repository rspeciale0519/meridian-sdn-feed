"""HTTPS-only download with host allowlist and a response-size cap."""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

from sdn_feed.constants import (
    ALLOWED_FETCH_HOSTS,
    ALLOWED_S3_PREFIX,
    FETCH_RETRIES,
    FETCH_TIMEOUT_S,
    MAX_RESPONSE_BYTES,
    USER_AGENT,
)
from sdn_feed.models import FetchResult


class FetchError(RuntimeError):
    pass


def host_allowed(hostname: str | None) -> bool:
    if not hostname:
        return False
    host = hostname.lower().rstrip(".")
    if host in ALLOWED_FETCH_HOSTS:
        return True
    return host.startswith(ALLOWED_S3_PREFIX) and host.endswith(".amazonaws.com")


def assert_allowed_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise FetchError(f"refusing non-https URL: {url}")
    if not host_allowed(parsed.hostname):
        raise FetchError(f"refusing host not on allowlist: {parsed.hostname or url}")


class AllowlistRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        assert_allowed_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def read_capped(response, *, limit: int = MAX_RESPONSE_BYTES) -> bytes:
    content_length = response.headers.get("Content-Length")
    if content_length:
        try:
            declared = int(content_length)
        except ValueError:
            declared = 0
        if declared > limit:
            raise FetchError(f"response Content-Length {declared} exceeds cap {limit}")
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = response.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise FetchError(f"response exceeded size cap {limit} bytes")
        chunks.append(chunk)
    return b"".join(chunks)


def fetch_url(url: str, *, timeout: int = FETCH_TIMEOUT_S) -> FetchResult:
    assert_allowed_url(url)
    last_error: Exception | None = None
    opener = urllib.request.build_opener(AllowlistRedirectHandler)
    for attempt in range(1, FETCH_RETRIES + 1):
        request = urllib.request.Request(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
            method="GET",
        )
        try:
            with opener.open(request, timeout=timeout) as response:
                assert_allowed_url(response.geturl() or url)
                raw = read_capped(response)
                charset = response.headers.get_content_charset() or "utf-8"
                try:
                    body = raw.decode(charset)
                except UnicodeDecodeError:
                    body = raw.decode("utf-8", errors="replace")
                return FetchResult(
                    url=response.geturl() or url,
                    body=body,
                    last_modified=response.headers.get("Last-Modified") or "",
                    status=getattr(response, "status", 200) or 200,
                )
        except FetchError:
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt < FETCH_RETRIES:
                time.sleep(2 ** (attempt - 1))
    raise FetchError(f"failed to fetch {url} after {FETCH_RETRIES} attempts: {last_error}")
