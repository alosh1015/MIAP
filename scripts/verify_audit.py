"""Verify a MIAP audit export independently of the application.

Usage:
    python scripts/verify_audit.py data/audit-export.ndjson
    python scripts/verify_audit.py --from-api http://127.0.0.1:8000 --token <jwt>
    python scripts/verify_audit.py            # looks for data/audit-export.ndjson

The export is one JSON object per line. Each event's hash is SHA-256 over the
canonical JSON (sorted keys, no whitespace) of every field except ``seq`` and
``hash``, including ``prev_hash``. The first event links to 64 zeroes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

GENESIS_HASH = "0" * 64
FIELDS = (
    "event_id",
    "ts",
    "actor_id",
    "action",
    "resource_type",
    "resource_id",
    "detail",
    "prev_hash",
)


def canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(event: dict) -> str:
    return hashlib.sha256(canonical({name: event[name] for name in FIELDS}).encode("utf-8")).hexdigest()


def load_lines(path: Path) -> list[dict]:
    events = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path}:{number}: not valid JSON ({exc})")
    return events


def fetch(url: str, token: str) -> bytes:
    request = urllib.request.Request(
        url.rstrip("/") + "/api/v1/audit/export",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def verify(events: list[dict]) -> tuple[bool, int, int | None, str | None]:
    prev = GENESIS_HASH
    expected_seq = events[0].get("seq") if events else None
    for index, event in enumerate(events):
        seq = event.get("seq")
        if expected_seq is not None and seq != expected_seq + index:
            return False, index, seq, f"sequence gap: expected {expected_seq + index}, found {seq}"
        missing = [name for name in FIELDS if name not in event]
        if missing:
            return False, index, seq, f"missing fields: {', '.join(missing)}"
        if event["prev_hash"] != prev:
            return False, index, seq, "prev_hash does not match the previous event"
        if digest(event) != event.get("hash"):
            return False, index, seq, "hash does not match the canonical payload"
        prev = event["hash"]
    return True, len(events), None, None


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a MIAP audit chain.")
    parser.add_argument("path", nargs="?", help="NDJSON export (default: data/audit-export.ndjson)")
    parser.add_argument("--from-api", metavar="BASE_URL", help="Download the export before verifying")
    parser.add_argument("--token", help="JWT for --from-api")
    parser.add_argument("--json", action="store_true", help="Print the result as JSON")
    args = parser.parse_args()

    if args.from_api:
        if not args.token:
            parser.error("--from-api requires --token")
        payload = fetch(args.from_api, args.token)
        events = [json.loads(line) for line in payload.decode("utf-8").splitlines() if line.strip()]
    else:
        path = Path(args.path or "data/audit-export.ndjson")
        if not path.exists():
            parser.error(f"{path} does not exist; export it from the audit page or pass --from-api")
        events = load_lines(path)

    ok, checked, bad_seq, reason = verify(events)
    result = {"ok": ok, "checked": checked, "first_bad_seq": bad_seq, "reason": reason}
    if args.json:
        print(json.dumps(result))
    elif ok:
        print(f"OK: {checked} events, chain intact (genesis -> {events[-1]['hash'][:12]}...)")
    else:
        print(f"BROKEN at seq {bad_seq} (checked {checked}): {reason}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
