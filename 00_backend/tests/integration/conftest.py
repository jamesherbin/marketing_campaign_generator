"""Isolated databases on the explicitly selected disposable local test server."""
import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio

from campaign.config import DatabaseSettings
from campaign.database import database_pool

DATABASE = Path(__file__).resolve().parents[3] / "database"


@pytest_asyncio.fixture
async def isolated_database_url():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.fail("TEST_DATABASE_URL is required; see database/README.md for the test service")
    parsed = urlsplit(url)
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"} or parsed.path != "/campaign_test":
        pytest.fail("Integration tests require the local disposable campaign_test database")
    try:
        admin = await asyncpg.connect(url, timeout=5)
    except Exception:
        pytest.fail("Cannot connect to disposable PostgreSQL; start the test service", pytrace=False)
    name = "campaign_test_" + uuid4().hex
    created = False
    try:
        await admin.execute(f'CREATE DATABASE "{name}"')
        created = True
        yield urlunsplit(parsed._replace(path="/" + name))
    finally:
        try:
            if created:
                await admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
        finally:
            await admin.close()


@pytest_asyncio.fixture
async def migrated_pool(isolated_database_url):
    async with database_pool(DatabaseSettings(url=isolated_database_url, _env_file=None)) as pool:
        async with pool.acquire() as connection:
            for migration in sorted((DATABASE / "migrations").glob("*.sql")):
                await connection.execute(migration.read_text())
        yield pool


@pytest_asyncio.fixture
async def restricted_pools(migrated_pool, isolated_database_url):
    names = {kind: f"campaign_test_{kind}_{uuid4().hex}" for kind in ("runtime", "operator")}
    created = []
    pools = {}
    try:
        for name in names.values():
            await migrated_pool.execute(f'CREATE ROLE "{name}" NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT')
            created.append(name)
        grants = (DATABASE / "grants.sql").read_text()
        for kind, name in names.items():
            grants = grants.replace(f':"{kind}_role"', f'"{name}"')
        await migrated_pool.execute(grants)
        for kind, name in names.items():
            async def initialize(connection, role=name):
                await connection.execute(f'SET ROLE "{role}"')
            pools[kind] = await asyncpg.create_pool(
                isolated_database_url, min_size=1, max_size=3, init=initialize,
            )
        yield pools
    finally:
        for pool in pools.values():
            await pool.close()
        for name in reversed(created):
            await migrated_pool.execute(f'DROP OWNED BY "{name}"')
            await migrated_pool.execute(f'DROP ROLE "{name}"')
