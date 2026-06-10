#!/bin/bash
# Restore skill-curator DB from sync (startup)
# Se local ausente/vazio e sync existe, restaura.

DB_DIR="${SKILL_CURATOR_DB_DIR:-$HOME/.local/share/skill-curator}"
SYNC_DIR="${SKILL_CURATOR_SYNC_DIR:-$HOME/dtp/ai-configs/global}"
DB="$DB_DIR/curator.db"
HOT="$SYNC_DIR/skill-curator.hot.db"

mkdir -p "$DB_DIR"

if [ ! -f "$DB" ] || [ ! -s "$DB" ]; then
    if [ -f "$HOT" ] && [ -s "$HOT" ]; then
        cp "$HOT" "$DB"
        echo "Restored from sync: $HOT → $DB"
    fi
fi
