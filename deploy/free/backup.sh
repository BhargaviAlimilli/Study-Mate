#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_dir="$(cd -- "$script_dir/../.." && pwd)"
destination="${1:-$HOME/study-mate-backups}"
mkdir -p -- "$destination"
destination="$(cd -- "$destination" && pwd)"
case "$destination/" in
  "$project_dir/"*) printf 'Backups contain user files; choose a directory outside the repository.\n' >&2; exit 1 ;;
esac
umask 077
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
compose=(docker compose --env-file "$script_dir/.env" -f "$script_dir/compose.yml")
output="$destination/postgres-$stamp.dump"
"${compose[@]}" exec -T postgres sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$output"
printf 'PostgreSQL backup written outside the repository: %s\n' "$output"
printf 'Qdrant/Redis/TLS volumes are not included. See README.md for a stopped-volume backup.\n'
