import asyncio
import os
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from campaign.config import DatabaseSettings
from campaign.database import DatabaseStartupError, database_lifespan, database_pool


class FakePool:
    def __init__(self, *, startup_error=None, probe_error=None):
        self.startup_error = startup_error
        self.connection = Mock(fetchval=AsyncMock(return_value=1, side_effect=probe_error))
        self.close = AsyncMock()
        self.terminate = Mock()

    def __await__(self):
        async def initialize():
            if self.startup_error:
                raise self.startup_error
            return self
        return initialize().__await__()

    def acquire(self, **kwargs):
        context = Mock()
        context.__aenter__ = AsyncMock(return_value=self.connection)
        context.__aexit__ = AsyncMock(return_value=False)
        return context


@pytest.fixture(autouse=True)
def clean_environment():
    with patch.dict(os.environ, {}, clear=True):
        yield


def local_settings(**overrides):
    return DatabaseSettings(
        url="postgresql://user:private-password@localhost/test", _env_file=None,
        **overrides,
    )


def cloud_settings(**overrides):
    return DatabaseSettings(
        mode="cloud_sql", instance="project:region:instance", name="campaigns",
        user="runtime@example.iam", _env_file=None, **overrides,
    )


def test_settings_require_explicit_database_and_hide_secrets():
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        DatabaseSettings(_env_file=None)
    assert "private-password" not in repr(local_settings())
    assert "private-password" not in local_settings().model_dump_json()
    with pytest.raises(ValidationError) as error:
        local_settings(pool_max_size=0)
    assert "private-password" not in str(error.value)


@pytest.mark.parametrize("overrides", [
    {"pool_min_size": 3, "pool_max_size": 2},
    {"connect_timeout": 0}, {"shutdown_timeout": -1},
    {"mode": "unknown"}, {"instance": "unexpected"},
])
def test_rejects_invalid_settings(overrides):
    with pytest.raises(ValidationError):
        local_settings(**overrides)


def test_cloud_settings_reject_missing_fields_and_url():
    with pytest.raises(ValidationError):
        DatabaseSettings(mode="cloud_sql", _env_file=None)
    with pytest.raises(ValidationError):
        cloud_settings(url="postgresql://localhost/test")


def test_database_environment_is_typed():
    with patch.dict(os.environ, {
        "DATABASE_URL": "postgresql://localhost/test", "DATABASE_POOL_MAX_SIZE": "4",
        "DATABASE_CONNECT_TIMEOUT": "2.5",
    }):
        settings = DatabaseSettings(_env_file=None)
    assert settings.pool_max_size == 4
    assert settings.connect_timeout == 2.5


@pytest.mark.asyncio
async def test_local_pool_is_bounded_and_closed_on_application_failure():
    pool = FakePool()
    with patch("campaign.database.asyncpg.create_pool", return_value=pool) as create:
        with pytest.raises(ValueError, match="application failed"):
            async with database_pool(local_settings(pool_max_size=4)) as opened:
                assert opened is pool
                raise ValueError("application failed")
    assert create.call_args.kwargs["max_size"] == 4
    assert create.call_args.kwargs["timeout"] == 10
    pool.close.assert_awaited_once()
    pool.terminate.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_stage", ["startup_error", "probe_error"])
async def test_startup_failure_cleans_up_and_redacts_driver_errors(failure_stage):
    pool = FakePool(**{failure_stage: RuntimeError("private-password")})
    with patch("campaign.database.asyncpg.create_pool", return_value=pool):
        with pytest.raises(DatabaseStartupError) as error:
            async with database_pool(local_settings()):
                pytest.fail("Startup failure must not yield a pool")
    assert "private-password" not in str(error.value)
    assert error.value.__suppress_context__
    pool.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_cloud_pool_uses_private_iam_connections_and_closes_connector():
    pool = FakePool()
    connector = Mock(connect_async=AsyncMock(), close_async=AsyncMock())
    with patch("campaign.database.create_async_connector", AsyncMock(return_value=connector)) as factory:
        with patch("campaign.database.asyncpg.create_pool", return_value=pool) as create:
            async with database_pool(cloud_settings()):
                await create.call_args.kwargs["connect"]("project:region:instance", timeout=10)
    factory.assert_awaited_once_with(
        ip_type="PRIVATE", enable_iam_auth=True, refresh_strategy="LAZY", timeout=10,
    )
    connector.connect_async.assert_awaited_once_with(
        "project:region:instance", "asyncpg", user="runtime@example.iam", db="campaigns", timeout=10,
    )
    pool.close.assert_awaited_once()
    connector.close_async.assert_awaited_once()


@pytest.mark.asyncio
async def test_cloud_connector_is_closed_if_pool_creation_fails():
    connector = Mock(close_async=AsyncMock())
    with patch("campaign.database.create_async_connector", AsyncMock(return_value=connector)):
        with patch("campaign.database.asyncpg.create_pool", side_effect=RuntimeError("secret")):
            with pytest.raises(DatabaseStartupError):
                async with database_pool(cloud_settings()):
                    pytest.fail("Must fail closed")
    connector.close_async.assert_awaited_once()


@pytest.mark.asyncio
async def test_shutdown_timeout_terminates_checked_out_connections():
    pool = FakePool()

    async def hang():
        await asyncio.Event().wait()

    pool.close.side_effect = hang
    with patch("campaign.database.asyncpg.create_pool", return_value=pool):
        async with database_pool(local_settings(shutdown_timeout=0.01)):
            pass
    pool.terminate.assert_called_once()


@pytest.mark.asyncio
async def test_lifespan_reads_settings_at_startup_and_removes_closed_pool():
    pool = FakePool()
    settings_factory = Mock(return_value=local_settings())
    app = FastAPI(lifespan=database_lifespan(settings_factory))
    settings_factory.assert_not_called()
    with patch("campaign.database.asyncpg.create_pool", return_value=pool):
        async with app.router.lifespan_context(app):
            assert app.state.database_pool is pool
    assert not hasattr(app.state, "database_pool")
    settings_factory.assert_called_once()
    pool.close.assert_awaited_once()
