"""Explicit database resource lifecycle; importing this module never connects.

The API will adopt this lifespan alongside the durable repository. Keeping that
cutover atomic avoids presenting an in-memory repository as durable storage.
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI
from google.cloud.sql.connector import create_async_connector

from .config import DatabaseMode, DatabaseSettings


class DatabaseStartupError(RuntimeError):
    """A safe public startup error, without driver messages or credentials."""


async def require_campaign_schema(pool: asyncpg.Pool) -> None:
    """Fail startup for databases that have not completed the required migrations."""
    try:
        async with pool.acquire() as connection:
            versions = await connection.fetch("SELECT version FROM schema_migrations ORDER BY version")
            if [row["version"] for row in versions] != [1, 2, 3, 4]:
                raise ValueError("Unexpected schema version")
            # Check critical columns/tables as well as the migration ledger.
            await connection.execute("""
                SELECT c.workspace_id, a.actor_firebase_uid, l.position
                FROM campaigns c
                LEFT JOIN approval_events a USING (campaign_id, workspace_id)
                LEFT JOIN legacy_approval_history l USING (campaign_id, workspace_id)
                LIMIT 0
            """)
            if not await connection.fetchval("""
                SELECT has_function_privilege(current_user,
                    'public.lock_workspace_membership(text,uuid)', 'EXECUTE')
            """):
                raise ValueError("Runtime authorization grants are missing")
    except Exception:
        raise DatabaseStartupError("Database schema is not ready; apply migrations 001 through 004") from None


@asynccontextmanager
async def database_pool(settings: DatabaseSettings) -> AsyncIterator[asyncpg.Pool]:
    connector = None
    pool = None
    try:
        try:
            kwargs = dict(
                min_size=settings.pool_min_size,
                max_size=settings.pool_max_size,
                timeout=settings.connect_timeout,
                command_timeout=settings.command_timeout,
            )
            if settings.mode == DatabaseMode.CLOUD_SQL:
                connector = await create_async_connector(
                    ip_type="PRIVATE", enable_iam_auth=True, refresh_strategy="LAZY",
                    timeout=settings.connect_timeout,
                )

                async def connect(instance, **driver_kwargs):
                    return await connector.connect_async(
                        instance, "asyncpg", user=settings.user, db=settings.name,
                        **driver_kwargs,
                    )

                pool = asyncpg.create_pool(settings.instance, connect=connect, **kwargs)
            else:
                pool = asyncpg.create_pool(settings.url.get_secret_value(), **kwargs)

            # Retain the Pool before awaiting initialization so partial failures
            # can terminate connections already opened by min_size > 1.
            await pool
            async with pool.acquire(timeout=settings.connect_timeout) as connection:
                await connection.fetchval("SELECT 1")
        except Exception:
            raise DatabaseStartupError(
                "Database startup failed; verify connection configuration and availability"
            ) from None
        yield pool
    finally:
        try:
            if pool is not None:
                try:
                    await asyncio.wait_for(pool.close(), timeout=settings.shutdown_timeout)
                except Exception:
                    pool.terminate()
        finally:
            if connector is not None:
                await connector.close_async()


def database_lifespan(settings_factory: Callable[[], DatabaseSettings] = DatabaseSettings):
    """FastAPI lifespan factory, with settings read only at application startup."""
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with database_pool(settings_factory()) as pool:
            app.state.database_pool = pool
            try:
                yield
            finally:
                del app.state.database_pool
    return lifespan
