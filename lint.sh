#!/usr/bin/env bash
# Local lint script. CI runs this exact script.
# CI green ↔ local green is a non-negotiable invariant.

set -euo pipefail

cd "$(dirname "$0")"

TARGETS=(custom_components tests)
[ -d tools ] && TARGETS+=(tools)

echo "==> ruff check"
ruff check "${TARGETS[@]}"

echo "==> pytest"
if compgen -G 'tests/test_*.py' > /dev/null; then
    pytest tests/ -q
else
    echo "    (no tests, skipping)"
fi

if [ -f tools/update_index.py ]; then
    echo "==> INDEX.md consistency"
    python tools/update_index.py --check
fi

echo
echo "All checks passed."
