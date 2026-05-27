"""Operator diagnostics for the PureLink matrix switcher.

Pure stdlib so it runs anywhere Python 3.10+ does — same no-deps stance as
the integration. Mirrors the wire protocol implemented in
custom_components/purelink/purelink_client.py but is intentionally
standalone: when HA is broken, this still works.

Usage:
    python tools/diagnose.py --host 192.0.2.10 status
    python tools/diagnose.py --host 192.0.2.10 dump
    python tools/diagnose.py --host 192.0.2.10 probe --input 1 --output 1
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
import time

_STATUS_TOKEN_RE = re.compile(r"I(\d{2,})O(\d{2,})", re.IGNORECASE)
_DEFAULT_TIMEOUT = 5.0


async def _send(host: str, port: int, command: str, timeout: float = _DEFAULT_TIMEOUT) -> str:
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(host, port), timeout=timeout
    )
    try:
        writer.write((command + "\r\n").encode("ascii"))
        await writer.drain()
        data = await asyncio.wait_for(reader.readuntil(b"!"), timeout=timeout)
        return data.decode("ascii", errors="replace")
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except OSError:
            pass


def _parse_routing(raw: str) -> dict[int, int]:
    routing: dict[int, int] = {}
    inner = raw.strip().rstrip("!")
    idx = inner.upper().find("?C")
    payload = inner[idx + 2 :] if idx != -1 else inner
    for token in payload.split(","):
        m = _STATUS_TOKEN_RE.match(token.strip())
        if m:
            routing[int(m.group(2))] = int(m.group(1))
    return routing


async def cmd_status(args: argparse.Namespace) -> int:
    cmd = f"*{args.switcher_id:03d}H000!"
    t0 = time.perf_counter()
    try:
        raw = await _send(args.host, args.port, cmd)
    except (OSError, asyncio.TimeoutError) as err:
        print(f"DOWN  {args.host}:{args.port}  ({err.__class__.__name__}: {err})")
        return 1
    dt_ms = (time.perf_counter() - t0) * 1000
    print(f"UP    {args.host}:{args.port}  {dt_ms:.1f}ms  raw={raw.strip()!r}")
    return 0


async def cmd_dump(args: argparse.Namespace) -> int:
    raw = await _send(args.host, args.port, f"*{args.switcher_id:03d}?C!")
    routing = _parse_routing(raw)
    print(f"Routing on {args.host}:{args.port} (switcher_id={args.switcher_id}):")
    if not routing:
        print("  (no routes parsed)")
        print(f"  raw: {raw.strip()!r}")
        return 1
    for out in sorted(routing):
        inp = routing[out]
        label = "(disconnected)" if inp == 0 else f"Input {inp:2d}"
        print(f"  Output {out:2d}: {label}")
    return 0


async def cmd_probe(args: argparse.Namespace) -> int:
    print(f"Probing route Input {args.input} → Output {args.output}")

    pre_raw = await _send(args.host, args.port, f"*{args.switcher_id:03d}?C!")
    original = _parse_routing(pre_raw).get(args.output)
    print(f"  Original input on output {args.output}: {original}")

    set_cmd = f"*{args.switcher_id:03d}CI{args.input:02d}O{args.output:02d}!"
    set_raw = await _send(args.host, args.port, set_cmd)
    print(f"  Set: {set_raw.strip()!r}")

    post_raw = await _send(args.host, args.port, f"*{args.switcher_id:03d}?C!")
    verified = _parse_routing(post_raw).get(args.output)

    if verified == args.input:
        print(f"  Verified: output {args.output} now on input {args.input}")
    else:
        print(f"  FAIL: output {args.output} is on input {verified} (expected {args.input})")
        return 1

    if original is not None and original != args.input:
        if original == 0:
            restore_cmd = f"*{args.switcher_id:03d}CI00O{args.output:02d}!"
        else:
            restore_cmd = f"*{args.switcher_id:03d}CI{original:02d}O{args.output:02d}!"
        restore_raw = await _send(args.host, args.port, restore_cmd)
        print(f"  Restored to input {original}: {restore_raw.strip()!r}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Diagnostics for the PureLink matrix switcher (stdlib only).",
    )
    parser.add_argument("--host", required=True, help="device IP or hostname")
    parser.add_argument("--port", type=int, default=23)
    parser.add_argument("--switcher-id", type=int, default=255)
    sub = parser.add_subparsers(dest="action", required=True)

    sub.add_parser("status", help="heartbeat + latency")
    sub.add_parser("dump", help="pretty-print the routing matrix")

    probe = sub.add_parser("probe", help="route + verify + restore")
    probe.add_argument("--input", type=int, required=True)
    probe.add_argument("--output", type=int, required=True)

    args = parser.parse_args()
    handlers = {"status": cmd_status, "dump": cmd_dump, "probe": cmd_probe}
    return asyncio.run(handlers[args.action](args))


if __name__ == "__main__":
    sys.exit(main())
