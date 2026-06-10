#!/bin/bash
# Hot backup do skill-curator DB para sync multi-máquina
# Padrão: memory-service hot-backup.sh

DB_DIR="${SKILL_CURATOR_DB_DIR:-$HOME/.local/share/skill-curator}"
SYNC_DIR="${SKILL_CURATOR_SYNC_DIR:-$HOME/dtp/ai-configs/global}"
DB="$DB_DIR/curator.db"
HOT="$SYNC_DIR/skill-curator.hot.db"

if [ ! -f "$DB" ]; then
    echo "DB not found: $DB"
    exit 1
fi

# VACUUM INTO creates a consistent copy without WAL
sqlite3 "$DB" "VACUUM INTO '$HOT';"
echo "Hot backup: $HOT ($(du -h "$HOT" | cut -f1))"
