# Contributing

## First-time setup

```bash
git clone https://github.com/karolperkowski/purelink_ha.git
cd purelink_ha
git config core.hooksPath .githooks
pip install -r requirements-dev.txt
```

The pre-commit hook regenerates `INDEX.md` and runs `lint.sh`. Don't skip it.

## Per-change workflow

1. **Edit** code locally.
2. **Run lint** before committing: `./lint.sh`. CI runs the same script — local green is CI green.
3. **Stage by explicit path**: `git add custom_components/purelink/select.py`. Never `git add -A` or `.`.
4. **Commit** with a conventional message (format below).
5. **Pull-rebase** before pushing: `git pull --rebase origin main`. Never merge.
6. **Push**: `git push origin main`.
7. **Watch CI**: `gh run list --branch main --limit 1` then `gh run watch <id> --exit-status`. CI green = done.

## Commit message format

```
<type>(<scope>): <short imperative summary, ≤72 chars, lowercase, no period>

<paragraph or bullets explaining WHY this change was made,
what edge cases it handles, what to watch for in review>
```

Types: `feat`, `fix`, `refactor`, `chore`, `docs`, `test`.

Scope is the subsystem you're touching: `client`, `config`, `coordinator`, `select`, `ci`, `tools`, etc. Use one. Multiple scopes mean the commit is doing too much.

For multi-line bodies in PowerShell, use bash heredoc (`git commit -m "..."` mangles newlines):

```bash
git commit -m "$(cat <<'EOF'
feat(client): retry heartbeat once on first connection failure

Some UX-series firmware drops the first command after a cold reconnect.
Retrying once with a 200ms delay matches the device's recovery window
observed in the protocol log.
EOF
)"
```

`<<'EOF'` (single-quoted) prevents shell expansion of `$` and backticks inside the message.

## Rebase + push protocol

| Situation | Action |
| --- | --- |
| Local `main` behind remote | `git pull --rebase origin main` |
| Push rejected (non-fast-forward) | Same as above |
| Conflicts during rebase | Resolve manually; `git rebase --continue`. Don't `--skip` unless you understand what you're dropping. |
| Bad commit, already pushed | Make a new commit. **Never `--amend`** to pushed history. |
| Feature work | `git push origin <branch>`; open a PR; CI gates merge. |

Force-pushing to `main` is forbidden. Even if you "really need to". Stop, pull, rebase, push normally.

## Releases

See `../AGENTS.md` § Release Process. Releases are tag-driven; the release workflow asserts the tag matches `manifest.json::version`.

```bash
# 1. Bump custom_components/purelink/manifest.json::version
# 2. Commit + push
# 3. Tag and push
git tag vX.Y.Z
git push --tags
```

## Branch protection

Configure on GitHub under Settings → Branches for `main`:

- Require status checks to pass before merging: `Lint + test`, `Hassfest`, `HACS validation`
- Require branches to be up to date before merging
- Forbid force-pushes
- Forbid deletion

These rules are how `RULES.md` becomes mechanically enforced rather than aspirational.

## When to update which doc

| You changed... | Update... |
| --- | --- |
| User-visible behavior | `README.md` |
| A non-obvious convention | `AGENTS.md` |
| A "don't do that" rule | `RULES.md` |
| File inventory | (nothing — `INDEX.md` regenerates) |
| Operator runbook | `docs/TROUBLESHOOTING.md` |
