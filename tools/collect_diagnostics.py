"""Collect a redacted diagnostics bundle for bug reports.

Writes a zip containing:
  - manifest.json (verbatim — no secrets in there)
  - environment.txt (Python version, OS)
  - config_entries.json (purelink entries only, host IP last-octet masked)
  - home-assistant.log.purelink.txt (last 500 matching lines, IPs masked)

Redaction is best-effort. Inspect the bundle before sharing.

Usage:
    python tools/collect_diagnostics.py --config-dir /config --output bundle.zip
"""

from __future__ import annotations

import argparse
import json
import platform
import re
import sys
import zipfile
from pathlib import Path

_IP_RE = re.compile(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.)(\d{1,3})")
_MAX_LOG_LINES = 500


def _redact_ip(text: str) -> str:
    return _IP_RE.sub(r"\1XXX", text)


def _grep_log(log_path: Path, needle: str = "purelink") -> list[str]:
    if not log_path.exists():
        return []
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    matched = [ln for ln in lines if needle.lower() in ln.lower()]
    return matched[-_MAX_LOG_LINES:]


def _config_entries(config_dir: Path) -> list[dict]:
    storage = config_dir / ".storage" / "core.config_entries"
    if not storage.exists():
        return []
    try:
        data = json.loads(storage.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    entries = data.get("data", {}).get("entries", [])
    return [e for e in entries if e.get("domain") == "purelink"]


def _sanitize_entry(entry: dict) -> dict:
    # Deep copy via json round-trip; entries are JSON-safe by construction.
    out = json.loads(json.dumps(entry))
    host = out.get("data", {}).get("host")
    if isinstance(host, str):
        out["data"]["host"] = _redact_ip(host)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config-dir", required=True, type=Path, help="HA config directory")
    parser.add_argument(
        "--output", default=Path("purelink-diagnostics.zip"), type=Path
    )
    args = parser.parse_args()

    if not args.config_dir.exists():
        print(f"config-dir not found: {args.config_dir}", file=sys.stderr)
        return 1

    bundle: dict[str, str] = {}

    manifest = (
        Path(__file__).resolve().parent.parent
        / "custom_components"
        / "purelink"
        / "manifest.json"
    )
    if manifest.exists():
        bundle["manifest.json"] = manifest.read_text(encoding="utf-8")

    bundle["environment.txt"] = "\n".join(
        [
            f"python={sys.version.split()[0]}",
            f"platform={platform.platform()}",
        ]
    )

    entries = [_sanitize_entry(e) for e in _config_entries(args.config_dir)]
    bundle["config_entries.json"] = json.dumps(entries, indent=2)

    log_lines = _grep_log(args.config_dir / "home-assistant.log")
    bundle["home-assistant.log.purelink.txt"] = _redact_ip("\n".join(log_lines))

    with zipfile.ZipFile(args.output, "w", zipfile.ZIP_DEFLATED) as z:
        for name, content in bundle.items():
            z.writestr(name, content)

    print(f"Wrote {args.output}  ({len(bundle)} files)")
    print("Inspect before sharing — redaction is best-effort, not exhaustive.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
