#!/usr/bin/env bash
# ============================================================================
# migrate_to_pg.sh — Database migration bootstrap script
#
# Reads PG_URL from the environment and runs Alembic migrations against the
# PostgreSQL target.  If PG_URL is not set the script prints a helpful error
# and exits so you don't accidentally migrate your SQLite dev database in a
# way that makes a mess.
#
# Usage
# -----
#   export PG_URL="postgresql://user:pass@host:5432/chainkefull"
#   bash scripts/migrate_to_pg.sh          # normal run
#   bash scripts/migrate_to_pg.sh --dry     # preview only, no SQL applied
#   bash scripts/migrate_to_pg.sh up        # same as default (upgrade)
#   bash scripts/migrate_to_pg.sh down      # rollback one revision
#   bash scripts/migrate_to_pg.sh history   # show all migrations
#   bash scripts/migrate_to_pg.sh current   # show current revision
#   bash scripts/migrate_to_pg.sh check     # check if migrations are up-to-date
#   bash scripts/migrate_to_pg.sh gen "msg" # auto-generate a new migration
# ============================================================================

set -euo pipefail

# ── Resolve project root (parent of the scripts/ directory) ────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── Guard: PG_URL is mandatory for this script ─────────────────────────────
if [ -z "${PG_URL:-}" ]; then
    echo "[ERROR] PG_URL environment variable is not set." >&2
    echo "" >&2
    echo "  You are targeting PostgreSQL but no connection string was provided." >&2
    echo "" >&2
    echo "  Export it before running this script, e.g.:" >&2
    echo "" >&2
    echo '    export PG_URL="postgresql://user:password@localhost:5432/chainkefull"' >&2
    echo "    bash $0" >&2
    echo "" >&2
    echo "  Tip: you can also add PG_URL to your .env file and source it:" >&2
    echo "    set -a && source $PROJECT_ROOT/.env && set +a" >&2
    echo "    bash $0" >&2
    echo "" >&2
    exit 1
fi

# ── Detect Python ──────────────────────────────────────────────────────────
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PYTHON="$cmd"
        break
    fi
done
if [ -z "$PYTHON" ]; then
    echo "[ERROR] Python interpreter not found. Please install Python 3." >&2
    exit 1
fi

# ── Ensure Alembic is installed ────────────────────────────────────────────
if ! "$PYTHON" -c "import alembic" 2>/dev/null; then
    echo "[INFO] alembic not found — installing from project dependencies…"
    if [ -f "$PROJECT_ROOT/requirements.txt" ]; then
        "$PYTHON" -m pip install -r "$PROJECT_ROOT/requirements.txt" --quiet
    elif [ -f "$PROJECT_ROOT/pyproject.toml" ]; then
        "$PYTHON" -m pip install . --quiet
    else
        "$PYTHON" -m pip install alembic psycopg2-binary --quiet
    fi
    echo "[INFO] alembic installed."
fi

# ── Determine Alembic config path ──────────────────────────────────────────
ALEMBIC_CFG="$PROJECT_ROOT/alembic.ini"
if [ ! -f "$ALEMBIC_CFG" ]; then
    echo "[INFO] No alembic.ini found at $ALEMBIC_CFG — initialising Alembic…"
    cd "$PROJECT_ROOT"
    "$PYTHON" -m alembic init alembic
    echo "[INFO] Initialised Alembic in $PROJECT_ROOT/alembic/"
    # Patch the new alembic.ini to use our database config module
    if [ -f alembic.ini ]; then
        # Replace the default sqlalchemy.url placeholder with a comment
        # telling users to use the env var approach.
        sed -i 's/^sqlalchemy.url.*/sqlalchemy.url = %(PG_URL)s/' alembic.ini
        echo "[INFO] Updated alembic.ini to read PG_URL from env."
    fi
    ALEMBIC_CFG="$PROJECT_ROOT/alembic.ini"
fi

# ── Export PG_URL so Alembic can read it from env (env_template.py) ────────
export PG_URL

# ── Parse subcommand ───────────────────────────────────────────────────────
DRY_RUN=false
CMD=""

for arg in "$@"; do
    case "$arg" in
        --dry)    DRY_RUN=true ;;
        up|down|history|current|check|gen|stamp|merge|heads|list)
                  CMD="$arg" ;;
        *)        if [ -z "$CMD" ]; then CMD="$arg"; else MIGRATION_MSG="$arg"; fi ;;
    esac
done

# Default command = upgrade
if [ -z "$CMD" ]; then
    CMD="up"
fi

# ── Print banner ───────────────────────────────────────────────────────────
echo "═══════════════════════════════════════════════════════════════"
echo "  Chainkefull — Database Migration"
echo "  Target:      PostgreSQL ($PG_URL)"
echo "  Command:     $CMD${MIGRATION_MSG:+  \"$MIGRATION_MSG\"}"
echo "  Dry run:     $DRY_RUN"
echo "═══════════════════════════════════════════════════════════════"
echo ""

cd "$PROJECT_ROOT"

# ── Execute ────────────────────────────────────────────────────────────────
case "$CMD" in
    up|upgrade)
        echo ">>> Running 'alembic upgrade head' ..."
        if [ "$DRY_RUN" = true ]; then
            $PYTHON -m alembic upgrade head --sql
        else
            $PYTHON -m alembic upgrade head
        fi
        ;;
    down|downgrade)
        REV="${MIGRATION_MSG:--1}"
        echo ">>> Running 'alembic downgrade $REV' ..."
        if [ "$DRY_RUN" = true ]; then
            $PYTHON -m alembic downgrade "$REV" --sql
        else
            $PYTHON -m alembic downgrade "$REV"
        fi
        ;;
    history)
        $PYTHON -m alembic history
        ;;
    current)
        $PYTHON -m alembic current
        ;;
    check)
        $PYTHON -m alembic check
        ;;
    gen|generate|revision)
        MSG="${MIGRATION_MSG:-auto}"
        echo ">>> Generating new migration: \"$MSG\""
        $PYTHON -m alembic revision --autogenerate -m "$MSG"
        echo ""
        echo "  → Review the generated file in alembic/versions/"
        echo "  → Then run:  bash $SCRIPT_DIR/migrate_to_pg.sh up"
        ;;
    stamp)
        REV="${MIGRATION_MSG:-head}"
        echo ">>> Stamping database as revision: $REV"
        $PYTHON -m alembic stamp "$REV"
        ;;
    merge)
        $PYTHON -m alembic merge -m "${MIGRATION_MSG:-merge-heads}" heads
        ;;
    heads|list)
        $PYTHON -m alembic heads
        ;;
    *)
        echo "[ERROR] Unknown command: $CMD" >&2
        echo "  Valid: up, down, history, current, check, gen, stamp, merge, heads" >&2
        exit 1
        ;;
esac

EXIT_CODE=$?
echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo "[✔] Migration command '$CMD' completed successfully."
else
    echo "[✘] Migration command '$CMD' failed (exit code $EXIT_CODE)." >&2
fi
exit $EXIT_CODE
