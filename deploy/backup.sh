#!/bin/sh
set -eu
stamp=$(date -u +%Y%m%dT%H%M%SZ)
exec .venv/bin/python scripts/backup_database.py "/var/lib/docify-backups/docify-$stamp.dump"
