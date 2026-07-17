#!/usr/bin/env bash
# oh-my-brain bootstrap: idempotent setup for the cognitive-debt harness.
# Run from anywhere inside the repo: bash scripts/bootstrap.sh
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

echo "[oh-my-brain] bootstrap starting in $ROOT"

# 1. state directories
mkdir -p logs kt/data kt/models learning

# 2. python deps (torch for KT; openai for persona simulation)
PY="${OMB_PYTHON:-python3}"
if ! "$PY" -c "import torch" 2>/dev/null; then
  echo "[oh-my-brain] WARNING: torch not importable via $PY."
  echo "               KT training will be unavailable until you install it:"
  echo "               $PY -m pip install torch numpy openai"
fi

# 2.5 seed the named KC catalog (idempotent)
"$PY" -c "import sys; sys.path.insert(0,'.'); from kt.kc_catalog import seed_store; print('[oh-my-brain] KC catalog:', seed_store('kt/data/kc.json'), 'concepts')" || true

# 3. hook self-test (same fail-open path codex will call)
echo '{"session_id":"bootstrap","cwd":"'"$ROOT"'","hook_event_name":"UserPromptSubmit","prompt":"bootstrap self-test because we verify the hook works"}' \
  | "$PY" .codex/hooks/on_user_prompt.py --log-dir logs >/dev/null
if [ -s logs/prompts.jsonl ]; then
  echo "[oh-my-brain] hook self-test OK (logs/prompts.jsonl written)"
else
  echo "[oh-my-brain] WARNING: hook self-test did not write a log record"
fi

# 4. trust reminder (codex loads repo hooks only for trusted projects)
cat <<'EOF'
[oh-my-brain] setup complete.

NOTE for codex users: repo-level hooks load only when this project is trusted.
If prompts are not being logged, mark the project trusted (codex will prompt
you, or see /hooks to review and trust the hook), then start a new session.
Skills under .agents/skills/ are auto-discovered; AGENTS.md applies as-is.
EOF
