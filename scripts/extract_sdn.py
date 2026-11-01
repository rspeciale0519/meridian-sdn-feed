#!/usr/bin/env python3
"""Entry point used by GitHub Actions and local runs."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sdn_feed.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
