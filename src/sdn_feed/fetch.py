"""HTTP download via stdlib. OFAC SLS requires a User-Agent or it 403s."""

from __future__ import annotations

import time
import urllib.error
import urllib.request

from sdn_feed.constants import FETCH_RETRIES, FETCH_TIMEOUT_S, USER_AGENT
from sdn_feed.models import FetchResult


class FetchError(RuntimeError):
    pass


def fetch_url(url: str, *, timeout: int = FETCH_TIMEOUT_S) -> FetchResult:
    last_error: Exception | None = None
    for attempt in range(1, FETCH_RETRIES + 1):
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "*/*",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
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
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt < FETCH_RETRIES:
                time.sleep(2 ** (attempt - 1))
    raise FetchError(f"failed to fetch {url} after {FETCH_RETRIES} attempts: {last_error}")
