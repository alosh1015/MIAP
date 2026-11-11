"""Generate the PII envelope and blind-index keys.

    python scripts/gen_keys.py            # print the env lines
    python scripts/gen_keys.py --write-env  # append missing keys to backend/.env

The values are secrets. ``backend/.env`` is gitignored; never commit the output.
"""

from __future__ import annotations

import argparse
import base64
import os
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parents[1] / "backend" / ".env"
KEYS = ("MIAP_PII_KEY", "MIAP_PII_INDEX_KEY", "MIAP_PII_KEY_VERSION")


def _generate() -> dict[str, str]:
    return {
        "MIAP_PII_KEY": base64.b64encode(os.urandom(32)).decode("ascii"),
        "MIAP_PII_INDEX_KEY": base64.b64encode(os.urandom(32)).decode("ascii"),
        "MIAP_PII_KEY_VERSION": "1",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate MIAP PII keys")
    parser.add_argument("--write-env", action="store_true", help="append missing keys to backend/.env")
    parser.add_argument("--force", action="store_true", help="replace keys already present")
    args = parser.parse_args()

    generated = _generate()
    if not args.write_env:
        for name, value in generated.items():
            print(f"{name}={value}")
        return 0

    existing = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    present = {line.split("=", 1)[0] for line in existing if "=" in line and not line.startswith("#")}
    appended: list[str] = []
    for name, value in generated.items():
        if name in present and not args.force:
            continue
        if args.force:
            existing = [line for line in existing if not line.startswith(f"{name}=")]
        appended.append(f"{name}={value}")
    if appended:
        ENV_PATH.write_text("\n".join(existing + appended) + "\n", encoding="utf-8")
        print(f"appended {len(appended)} setting(s) to {ENV_PATH}")
    else:
        print(f"{ENV_PATH} already has all PII settings; nothing written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
