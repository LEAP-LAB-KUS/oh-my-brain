#!/usr/bin/env bash
# Install the oh-my-brain harness add-on INTO an existing user project.
# Usage: bash scripts/install-into.sh /path/to/your-project
set -euo pipefail

TARGET="${1:?usage: bash scripts/install-into.sh /path/to/your-project}"
SRC="$(cd "$(dirname "$0")/.." && pwd)"

if [ ! -d "$TARGET" ]; then
  echo "target directory does not exist: $TARGET" >&2
  exit 1
fi

echo "[oh-my-brain] installing add-on into $TARGET"

# harness runtime (never the user's project code)
mkdir -p "$TARGET/.codex/hooks" "$TARGET/.agents" "$TARGET/kt" "$TARGET/scripts"
cp -R "$SRC/.agents/skills" "$TARGET/.agents/"
cp "$SRC/.codex/hooks.json" "$TARGET/.codex/"
cp "$SRC/.codex/hooks/on_user_prompt.py" "$TARGET/.codex/hooks/"
cp -R "$SRC/harness" "$TARGET/"
cp "$SRC/kt/__init__.py" "$SRC/kt/akt.py" "$SRC/kt/train.py" "$TARGET/kt/"
cp "$SRC/scripts/bootstrap.sh" "$TARGET/scripts/"

# AGENTS.md: append to an existing one, never clobber
if [ -f "$TARGET/AGENTS.md" ]; then
  if ! grep -q "oh-my-brain" "$TARGET/AGENTS.md"; then
    printf '\n\n<!-- appended by oh-my-brain installer -->\n\n' >> "$TARGET/AGENTS.md"
    cat "$SRC/AGENTS.md" >> "$TARGET/AGENTS.md"
    echo "[oh-my-brain] appended harness policy to existing AGENTS.md"
  else
    echo "[oh-my-brain] AGENTS.md already contains harness policy; skipped"
  fi
else
  cp "$SRC/AGENTS.md" "$TARGET/AGENTS.md"
fi

cat <<'EOF'
[oh-my-brain] installed. Next steps:
  1. Open the project with codex and trust it when prompted (hooks need trust).
  2. Work on YOUR project as usual; the harness stays in the background.
  3. Dashboard anytime: python3 -m harness.dashboard  ->  learning/dashboard.html
EOF
