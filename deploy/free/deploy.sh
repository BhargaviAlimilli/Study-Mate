#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_dir="$(cd -- "$script_dir/../.." && pwd)"
cd "$project_dir"

python3 "$script_dir/prepare_env.py" --check
docker compose version >/dev/null
compose=(docker compose --env-file "$script_dir/.env" -f "$script_dir/compose.yml")
# Do not print a resolved Compose configuration: it contains credentials.
"${compose[@]}" config --quiet
"${compose[@]}" build api frontend
"${compose[@]}" stop edge frontend api rq-worker
"${compose[@]}" up -d --wait postgres qdrant redis
# Apply migrations once before allowing API and worker traffic. Re-run for updates.
"${compose[@]}" up --no-deps --force-recreate --abort-on-container-exit --exit-code-from migrate migrate
"${compose[@]}" up -d --no-deps --wait api rq-worker
"${compose[@]}" up -d --no-deps --wait frontend
"${compose[@]}" up -d --no-deps edge
"${compose[@]}" ps
printf '\nStarted. Allow time for the first TLS certificate and embedding-model download.\n'
printf 'Create your private learner account using the command in deploy/free/README.md.\n'
