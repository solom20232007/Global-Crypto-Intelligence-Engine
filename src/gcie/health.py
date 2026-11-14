"""Dependency-free health check for local runs and future worker probes."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from gcie import __version__


def health_status() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "global-crypto-intelligence-engine",
        "version": __version__,
        "timestamp": datetime.now(UTC).isoformat(),
    }


def main() -> None:
    print(json.dumps(health_status(), sort_keys=True))


if __name__ == "__main__":
    main()
