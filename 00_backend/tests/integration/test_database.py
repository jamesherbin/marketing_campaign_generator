from pathlib import Path

import asyncpg
import pytest

from campaign.config import DatabaseSettings
from campaign.database import database_pool

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
MIGRATIONS = Path(__file__).resolve().parents[3] / "database" / "migrations"


async def test_pool_reopens_with_persisted_data(isolated_database_url):
    settings = DatabaseSettings(url=isolated_database_url, _env_file=None)
    async with database_pool(settings) as pool:
        await pool.execute("CREATE TABLE persistence_probe (value integer NOT NULL)")
        await pool.execute("INSERT INTO persistence_probe VALUES (42)")
    async with database_pool(settings) as pool:
        assert await pool.fetchval("SELECT value FROM persistence_probe") == 42


async def seed_member(connection, role):
    user = await connection.fetchval("""
        INSERT INTO users (firebase_uid, email) VALUES ('test-uid', 'test@example.com')
        RETURNING user_id
    """)
    workspace = await connection.fetchval("""
        INSERT INTO workspaces (name, slug, created_by_user_id) VALUES ('Test', 'test', $1)
        RETURNING workspace_id
    """, user)
    await connection.execute("""
        INSERT INTO workspace_members (workspace_id, user_id, role)
        VALUES ($1, $2, $3)
    """, workspace, user, role)


async def test_role_migration_preserves_members_and_enforces_roles(isolated_database_url):
    async with database_pool(DatabaseSettings(url=isolated_database_url, _env_file=None)) as pool:
        async with pool.acquire() as connection:
            await connection.execute((MIGRATIONS / "001_core_schema.sql").read_text())
            await seed_member(connection, "editor")
            await connection.execute((MIGRATIONS / "002_workspace_roles.sql").read_text())
            assert await connection.fetchval("SELECT role FROM workspace_members") == "editor"
            for role in ("viewer", "editor", "runner", "approver"):
                await connection.execute("UPDATE workspace_members SET role = $1", role)
            for role in ("owner", "admin", "unknown"):
                with pytest.raises(asyncpg.CheckViolationError):
                    await connection.execute("UPDATE workspace_members SET role = $1", role)


@pytest.mark.parametrize("legacy_role", ["owner", "admin"])
async def test_legacy_role_aborts_migration_without_changes(isolated_database_url, legacy_role):
    async with database_pool(DatabaseSettings(url=isolated_database_url, _env_file=None)) as pool:
        async with pool.acquire() as connection:
            await connection.execute((MIGRATIONS / "001_core_schema.sql").read_text())
            await seed_member(connection, legacy_role)
            with pytest.raises(asyncpg.RaiseError, match="explicit role reassignment"):
                await connection.execute((MIGRATIONS / "002_workspace_roles.sql").read_text())
            await connection.execute("ROLLBACK")
            assert await connection.fetchval("SELECT role FROM workspace_members") == legacy_role
            with pytest.raises(asyncpg.CheckViolationError):
                await connection.execute("UPDATE workspace_members SET role = 'runner'")
            await connection.execute("UPDATE workspace_members SET role = 'viewer'")
            await connection.execute((MIGRATIONS / "002_workspace_roles.sql").read_text())
            await connection.execute("UPDATE workspace_members SET role = 'runner'")
