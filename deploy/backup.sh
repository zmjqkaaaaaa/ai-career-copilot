#!/usr/bin/env bash
set -euo pipefail
umask 077

if (( $# < 2 )); then
  echo "Usage: bash deploy/backup.sh BACKUP_DIR [docker compose options]" >&2
  exit 2
fi

destination=$1
shift
compose=(docker compose "$@")
running=$("${compose[@]}" ps --status running --services)
if grep -Eq '^(frontend|api|worker|migrate)$' <<< "$running"; then
  echo "Stop the application and worker before exporting a consistent snapshot." >&2
  exit 1
fi

mkdir -p -- "$destination"
snapshot=$(mktemp -d "$destination/career-copilot-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")
"${compose[@]}" exec -T db sh -ec '
  MYSQL_PWD="$MYSQL_PASSWORD" exec mysqldump --single-transaction --quick --no-tablespaces +    --set-gtid-purged=OFF -u "$MYSQL_USER" "$MYSQL_DATABASE"
' > "$snapshot/database.sql"

"${compose[@]}" run --no-deps --rm -T --entrypoint tar api +  -czf - -C /data/resumes . > "$snapshot/resumes.tar.gz"

(
  cd "$snapshot"
  test -s database.sql
  tar -tzf resumes.tar.gz >/dev/null
  sha256sum database.sql resumes.tar.gz > SHA256SUMS
)
printf '%s\n' "$snapshot"
