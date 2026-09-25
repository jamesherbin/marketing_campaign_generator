from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest

from campaign.config import DatabaseSettings
from campaign.database import DatabaseStartupError, database_pool, require_campaign_schema

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
MIGRATIONS = Path(__file__).resolve().parents[3] / "database" / "migrations"


async def seed_audit(connection):
    user = await connection.fetchval("""
        INSERT INTO users (firebase_uid, email) VALUES ('original-uid', 'original@example.com')
        RETURNING user_id
    """)
    workspace = await connection.fetchval("""
        INSERT INTO workspaces (name, slug, created_by_user_id)
        VALUES ('Original', 'original', $1) RETURNING workspace_id
    """, user)
    campaign = await connection.fetchval("""
        INSERT INTO campaigns (workspace_id, created_by_user_id) VALUES ($1, $2) RETURNING campaign_id
    """, workspace, user)
    event = await connection.fetchval("""
        INSERT INTO approval_events
        (campaign_id, workspace_id, actor_user_id, actor, phase, decision, campaign_version)
        VALUES ($1, $2, $3, 'Original display', 'execution', 'approved', 1)
        RETURNING approval_event_id
    """, campaign, workspace, user)
    return user, workspace, campaign, event


async def test_upgrade_backfills_verified_identity_and_restores_immutability(isolated_database_url):
    async with database_pool(DatabaseSettings(url=isolated_database_url, _env_file=None)) as pool:
        async with pool.acquire() as connection:
            for filename in ("001_core_schema.sql", "002_workspace_roles.sql"):
                await connection.execute((MIGRATIONS / filename).read_text())
            user, _, _, event = await seed_audit(connection)
            await connection.execute((MIGRATIONS / "003_durable_campaigns.sql").read_text())
            await connection.execute((MIGRATIONS / "004_authorization_locks.sql").read_text())
            await require_campaign_schema(pool)
            assert await connection.fetchval(
                "SELECT actor_firebase_uid FROM approval_events WHERE approval_event_id = $1", event,
            ) == "original-uid"
            await connection.execute("UPDATE users SET display_name = 'New display', email = NULL WHERE user_id = $1", user)
            for sql in ("UPDATE approval_events SET actor = 'forged'", "DELETE FROM approval_events"):
                with pytest.raises(asyncpg.RaiseError, match="immutable"):
                    await connection.execute(sql)
            with pytest.raises(asyncpg.RaiseError, match="immutable"):
                await connection.execute("UPDATE users SET firebase_uid = 'changed' WHERE user_id = $1", user)


async def test_migration_requires_role_migration_and_rolls_back(isolated_database_url):
    async with database_pool(DatabaseSettings(url=isolated_database_url, _env_file=None)) as pool:
        async with pool.acquire() as connection:
            await connection.execute((MIGRATIONS / "001_core_schema.sql").read_text())
            with pytest.raises(asyncpg.RaiseError, match="Migration 002"):
                await connection.execute((MIGRATIONS / "003_durable_campaigns.sql").read_text())
            await connection.execute("ROLLBACK")
            assert await connection.fetchval("SELECT to_regclass('schema_migrations')") is None
            assert await connection.fetchval("""
                SELECT is_nullable FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = 'email'
            """) == "NO"


async def test_identity_email_and_audit_constraints(migrated_pool):
    async with migrated_pool.acquire() as connection:
        user, workspace, campaign, _ = await seed_audit(connection)
        for uid in ("no-email-a", "no-email-b"):
            await connection.execute("INSERT INTO users (firebase_uid) VALUES ($1)", uid)
        with pytest.raises(asyncpg.UniqueViolationError):
            await connection.execute("INSERT INTO users (firebase_uid, email) VALUES ('different', 'ORIGINAL@example.com')")
        with pytest.raises(asyncpg.UniqueViolationError):
            await connection.execute("INSERT INTO users (firebase_uid) VALUES ('original-uid')")
        with pytest.raises(asyncpg.RaiseError, match="does not match"):
            await connection.execute("""
                INSERT INTO approval_events (campaign_id, workspace_id, actor_user_id, actor,
                    actor_firebase_uid, phase, decision, campaign_version)
                VALUES ($1, $2, $3, 'Display', 'forged-uid', 'execution', 'approved', 2)
            """, campaign, workspace, user)
        await connection.execute("""
            INSERT INTO legacy_approval_history
            (campaign_id, workspace_id, position, phase, decision, actor, decided_at)
            VALUES ($1, $2, 0, 'execution', 'approved', 'Unknown reviewer', now())
        """, campaign, workspace)
        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await connection.execute("""
                INSERT INTO legacy_approval_history
                (campaign_id, workspace_id, position, phase, decision, actor, decided_at)
                VALUES ($1, $2, 1, 'execution', 'approved', 'Unknown reviewer', now())
            """, campaign, uuid4())
        await connection.execute("""
            INSERT INTO campaign_imports
            (import_id, export_sha256, workspace_id, owner_user_id, workspace_name, workspace_slug, campaign_count)
            VALUES ($1, $2, $3, $4, 'Original', 'original', 1)
        """, uuid4(), "a" * 64, workspace, user)
        for table in ("legacy_approval_history", "campaign_imports"):
            for sql in (f"DELETE FROM {table}",
                        f"UPDATE {table} SET workspace_id = workspace_id"):
                with pytest.raises(asyncpg.RaiseError, match="immutable"):
                    await connection.execute(sql)


async def test_schema_readiness_rejects_empty_and_incompatible_schema(isolated_database_url, migrated_pool):
    await require_campaign_schema(migrated_pool)
    await migrated_pool.execute("DELETE FROM schema_migrations WHERE version = 3")
    with pytest.raises(DatabaseStartupError, match="schema is not ready"):
        await require_campaign_schema(migrated_pool)
    await migrated_pool.execute("DROP TABLE schema_migrations")
    with pytest.raises(DatabaseStartupError):
        await require_campaign_schema(migrated_pool)


async def test_runtime_and_operator_privileges(restricted_pools, migrated_pool):
    runtime = restricted_pools["runtime"]
    operator = restricted_pools["operator"]
    user = await operator.fetchval("INSERT INTO users (firebase_uid) VALUES ('operator-provisioned') RETURNING user_id")
    workspace = await operator.fetchval("""
        INSERT INTO workspaces (name, slug, created_by_user_id)
        VALUES ('Managed', 'managed', $1) RETURNING workspace_id
    """, user)
    await operator.execute("""
        INSERT INTO workspace_members (workspace_id, user_id, role, status)
        VALUES ($1, $2, 'runner', 'active')
    """, workspace, user)
    assert await runtime.fetchval("SELECT role FROM workspace_members") == "runner"
    for sql in (
        "INSERT INTO users (firebase_uid) VALUES ('forged')",
        "UPDATE users SET status = 'disabled'",
        "UPDATE workspace_members SET role = 'approver'",
        "UPDATE workspaces SET name = 'forged'",
        "DELETE FROM approval_events", "UPDATE approval_events SET actor = 'forged'",
        "TRUNCATE approval_events", "TRUNCATE legacy_approval_history",
        "INSERT INTO legacy_approval_history DEFAULT VALUES",
        "INSERT INTO campaign_imports DEFAULT VALUES",
        "CREATE TABLE privilege_escape (id integer)",
    ):
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await runtime.execute(sql)
    for sql in ("UPDATE legacy_approval_history SET actor = 'forged'",
                "DELETE FROM campaign_imports", "TRUNCATE legacy_approval_history"):
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await operator.execute(sql)
