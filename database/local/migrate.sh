#!/usr/bin/env bash
set -Eeuo pipefail

db_dir=/workspace/database
schema_table="$(psql --no-psqlrc --tuples-only --no-align --command \
  "SELECT to_regclass('public.schema_migrations')")"

if [[ "$schema_table" == "schema_migrations" ]]; then
  current_version="$(psql --no-psqlrc --tuples-only --no-align --command \
    'SELECT COALESCE(MAX(version), 0) FROM public.schema_migrations')"
  case "$current_version" in
    4)
      echo "Campaign schema is already at version 4."
      ;;
    3)
      echo "Applying campaign schema migration 004."
      psql --no-psqlrc --set ON_ERROR_STOP=1 --file "$db_dir/migrations/004_authorization_locks.sql"
      ;;
    *)
      echo "Unsupported schema_migrations state (maximum version: $current_version)." >&2
      exit 1
      ;;
  esac
else
  existing_users_table="$(psql --no-psqlrc --tuples-only --no-align --command \
    "SELECT to_regclass('public.users')")"
  if [[ -n "$existing_users_table" ]]; then
    echo "Database has partial or untracked campaign schema; refusing to replay migrations." >&2
    exit 1
  fi

  for migration in \
    001_core_schema.sql \
    002_workspace_roles.sql \
    003_durable_campaigns.sql \
    004_authorization_locks.sql; do
    echo "Applying campaign schema migration $migration."
    psql --no-psqlrc --set ON_ERROR_STOP=1 --file "$db_dir/migrations/$migration"
  done
fi

psql \
  --no-psqlrc \
  --set ON_ERROR_STOP=1 \
  --set runtime_role="$LOCAL_CAMPAIGN_RUNTIME_ROLE" \
  --set operator_role="$LOCAL_CAMPAIGN_OPERATOR_ROLE" \
  --file "$db_dir/grants.sql"

echo "Campaign schema and application grants are ready."
