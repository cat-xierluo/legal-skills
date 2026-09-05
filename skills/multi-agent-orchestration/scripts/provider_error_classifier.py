#!/usr/bin/env python3
"""Classify provider errors without echoing the source text.

This module is the single classifier used by quota probes and Orca terminal
rate-limit recovery.  Authentication/configuration/network failures take
precedence over quota wording so mixed diagnostic output fails closed.
"""

from __future__ import annotations

import argparse
import re
import sys


AUTH_RE = re.compile(
    r"(^|[^0-9])(401|403)([^0-9]|$)|unauthori[sz]ed|forbidden|authentication|"
    r"invalid[\s_-]*(api[\s_-]*)?key|login\s+required|not\s+logged\s+in",
    re.IGNORECASE,
)
CONFIG_RE = re.compile(
    r"(^|[^0-9])400([^0-9]|$)|bad\s+request|invalid.*model|"
    r"model.*(not[\s_-]*found|does\s+not\s+exist|unsupported|unknown)|"
    r"modelcode|config(uration)?[\s_-]*error|unknown\s+option|usage:\s*claude",
    re.IGNORECASE,
)
NETWORK_RE = re.compile(
    r"network|connection|connect[\s_-]*(failed|refused|reset)|dns|econn|"
    r"enotfound|socket|tls|certificate|request\s+timed\s+out|temporary\s+failure",
    re.IGNORECASE,
)
QUOTA_RE = re.compile(
    r"(^|[^0-9])429([^0-9]|$)|rate[ _-]?limit|usage[ _-]?limit|"
    r"quota[\s_-]*(exceed|exhaust|deplet|limit|reset)|"
    r"credits?\s.*(exhaust|deplet)|hit\s+(your\s+)?limit|limit\s+resets?",
    re.IGNORECASE,
)


def classify_provider_error(text: str) -> str:
    """Return auth/config/network/quota/unknown with fail-closed precedence."""

    if AUTH_RE.search(text):
        return "auth"
    if CONFIG_RE.search(text):
        return "config"
    if NETWORK_RE.search(text):
        return "network"
    if QUOTA_RE.search(text):
        return "quota"
    return "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Classify provider error text from stdin")
    parser.add_argument("--max-bytes", type=int, default=1024 * 1024)
    args = parser.parse_args(argv)
    if args.max_bytes < 1 or args.max_bytes > 8 * 1024 * 1024:
        parser.error("--max-bytes must be between 1 and 8388608")
    payload = sys.stdin.buffer.read(args.max_bytes + 1)
    if len(payload) > args.max_bytes:
        print("unknown")
        return 65
    print(classify_provider_error(payload.decode("utf-8", errors="replace")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
