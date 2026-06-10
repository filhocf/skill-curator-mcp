#!/usr/bin/env bash
set -euo pipefail

EVAL_ID="${1:?Usage: run-eval.sh <eval-id> (e.g. 001-cosine-fix)}"
EVAL_DIR="$(cd "$(dirname "$0")" && pwd)/${EVAL_ID}"

if [[ ! -d "$EVAL_DIR" ]]; then
  echo "❌ Eval não encontrado: $EVAL_DIR"
  exit 1
fi

if [[ ! -f "$EVAL_DIR/ISSUE.md" ]]; then
  echo "❌ ISSUE.md não encontrado em $EVAL_DIR"
  exit 1
fi

echo "🚀 Executando eval: $EVAL_ID"
echo "📄 Issue: $EVAL_DIR/ISSUE.md"
echo ""
cat "$EVAL_DIR/ISSUE.md"
echo ""
echo "---"
echo "TODO: integrar com CAO/subagent para execução automática"
