# Rules

The non-negotiables for contributing to `purelink_ha`. Full context in [AGENTS.md](AGENTS.md); this file is the punchy "do / don't" summary.

## Code

1. **Python 3.12+ only.** Home Assistant's supported Python floor moves forward yearly — match HA core's minimum, not yours. Don't use features the current HA version doesn't ship with.
2. **`from __future__ import annotations` at the top of every module.** Lets type hints reference symbols before they're defined and avoids string-quoting for forward refs. Already the convention in every file under `custom_components/purelink/`.
3. **Async everywhere in the HA integration layer.** No `time.sleep`, no `requests`, no blocking file I/O on the event loop. HA's executor (`hass.async_add_executor_job`) is for unavoidable sync calls — TCP work goes through `asyncio.open_connection`, as in `purelink_client.py::connect`.
4. **No third-party runtime dependencies under `custom_components/purelink/`.** `manifest.json::requirements` stays `[]`. Stdlib only. Adding a dep means we need to justify it to HACS reviewers and explain it in `AGENTS.md`.
5. **Use `_LOGGER` from `logging.getLogger(__name__)`, never `print()`.** HA captures the logger; `print()` goes to a black hole under the supervised image.
6. **Constants live in `const.py`.** Magic strings, ports, timeouts, command templates, response markers — all in `const.py`, exported by name. No string literals scattered across modules.
7. **Type-hint every function**, including `-> None`. ruff's `ANN` rules aren't enabled yet, but a future PR will turn them on; write code that won't fail when they do.

## Home Assistant conventions

8. **`DataUpdateCoordinator` for polling.** One coordinator per config entry; entities subclass `CoordinatorEntity`. Don't write per-entity timers — they'll fight each other and triple your TCP traffic.
9. **Raise `ConfigEntryNotReady` from `async_setup_entry` on transient failures.** HA retries with exponential back-off. Raising a bare `Exception` aborts setup permanently.
10. **`_attr_has_entity_name = True` + `DeviceInfo` for every entity.** Gives HA the device-grouped naming model. Already wired in `select.py`; copy that shape for any new entity type.
11. **`unique_id` survives IP changes only if the device identity does.** Current scheme is `purelink_{host}_{switcher_id}_output_{n}`. If we add MAC-based discovery, change the prefix; the device's switcher ID alone is not unique across multiple PureLinks on a network.
12. **`manifest.json::version` must match the git tag** that triggers a release. The release workflow asserts this. Bump both in the same commit.

## Networking

13. **Every TCP send goes through `PureLinkClient._send_raw`.** It holds the per-instance lock so two coroutines can't interleave commands on the shared socket. Don't write directly to `self._writer` from other methods.
14. **All commands end with `!` and are read with `readuntil(b"!")`.** Don't switch to line-buffered reads — the device doesn't emit newlines reliably.
15. **Switcher ID, input, and output are zero-padded** via `{sid:03d}`, `{inp:02d}`, `{out:02d}` in `const.py`. The device parses positionally; `*255CI1O1!` is not valid.
16. **Reconnect on failure, don't crash.** `_ensure_connected` re-opens the socket if `is_closing()`. Coordinator updates surface failures as `UpdateFailed` so HA marks entities unavailable instead of unloading the entry.

## Tests

17. **Tests live in `tests/` and run via `pytest`.** Use `pytest-homeassistant-custom-component` fixtures; don't construct `HomeAssistant` by hand.
18. **`enable_custom_integrations` is autouse'd in `conftest.py`.** Every test gets it; new test files don't need to opt in.
19. **Mock the network at `asyncio.open_connection`, not at `PureLinkClient`.** Tests should exercise the client's parsing and reconnect logic — patching the client itself defeats the point.

## Git / CI

20. **Pre-commit hook regenerates `INDEX.md` in a loop** until `git diff INDEX.md` is empty (self-reference convergence). Don't disable the hook.
21. **`tools/update_index.py` excludes `.git/`, `.vscode/`, `.claude/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `*.pyc`.** Local-only paths must be filtered so local and CI inventories agree.
22. **`./lint.sh` must pass before every commit and is the same script CI runs.** If they diverge, fix `lint.sh` — don't paper over with branch-specific config.
23. **Stage files by explicit path**, never `git add -A` or `git add .`. Catches stray dump files, large binaries, secrets pasted "just for a sec".
24. **`git pull --rebase origin main` before pushing.** Never `merge`; never `--force` to `main`.
25. **Never skip the pre-commit hook** (`--no-verify`). If it fails, fix the cause.
26. **Check GitHub Actions after every push.** `gh run list --branch main --limit 1` then `gh run watch <id> --exit-status`. Local lint green is not "done"; CI green is "done".
27. **Releases are tag-driven.** `git tag vX.Y.Z && git push --tags` triggers the release workflow which asserts the tag matches `manifest.json::version`, zips `custom_components/purelink/`, and attaches it to a GitHub Release. HACS consumes the release. No manual zipping.

## Security

28. **No secrets in committed files.** Device IPs and switcher IDs are user input, not constants — they live in the config entry, not the source. Don't paste an IP into a test or example "for convenience".
29. **Diagnostic bundles redact sensitive fields.** `tools/collect_diagnostics.py` masks the host's last octet before writing. If you add a new field, redact at write time, not at upload time.

## Markdown

30. **All `.md` filenames at the repo root are uppercase** (`README.md`, `AGENTS.md`, `RULES.md`, `INDEX.md`). Files under `docs/` follow the same convention (`docs/CONTRIBUTING.md`, `docs/TROUBLESHOOTING.md`).
