import os
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from campaign.config import DatabaseSettings, Settings
from campaign.database import DatabaseStartupError
from main import create_app


@pytest.mark.asyncio
async def test_actual_api_rejects_missing_database_configuration():
    with patch.dict(os.environ, {}, clear=True):
        app = create_app(database_settings_factory=lambda: DatabaseSettings(_env_file=None), settings_factory=lambda: Settings(_env_file=None))
        with pytest.raises(ValidationError):
            async with app.router.lifespan_context(app):
                pytest.fail('Missing database accepted')
        assert not hasattr(app.state, 'database_pool')


@pytest.mark.asyncio
async def test_actual_api_rejects_database_connection_failure():
    app = create_app(database_settings_factory=lambda: DatabaseSettings(url='postgresql://test:secret@localhost/test', _env_file=None))
    with patch('campaign.database.asyncpg.create_pool', side_effect=OSError('secret')):
        with pytest.raises(DatabaseStartupError) as error:
            async with app.router.lifespan_context(app):
                pytest.fail('Unavailable database accepted')
    assert 'secret' not in str(error.value)
    assert not hasattr(app.state, 'database_pool')


@pytest.fixture
def fake_startup_database():
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    state = SimpleNamespace(opened=False, closed=False)

    @asynccontextmanager
    async def pool(_):
        state.opened = True
        try:
            yield object()
        finally:
            state.closed = True

    with patch('main.database_pool', pool), patch('main.require_campaign_schema', AsyncMock()):
        yield state


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', [None, 'adk'])
async def test_health_reports_configured_mode_without_provider_calls(fake_startup_database, mode):
    from httpx import ASGITransport, AsyncClient
    values = {} if mode is None else {'campaign_runner_mode': mode}
    with patch.dict(os.environ, {}, clear=True), patch('campaign.adk_provider.Client') as provider:
        app = create_app(database_settings_factory=lambda: object(),
                         settings_factory=lambda: Settings(_env_file=None, **values))
        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
                response = await client.get('/health')
            assert response.status_code == 200
            assert response.json() == {'status': 'ok', 'runner_mode': mode or 'deterministic'}
            assert len(app.state.runners) == 4
        provider.assert_not_called()
    assert fake_startup_database.closed
    for name in ('runners', 'database_pool', 'runner_mode'):
        assert not hasattr(app.state, name)


@pytest.mark.asyncio
async def test_invalid_runner_mode_fails_before_database_startup(fake_startup_database):
    with patch.dict(os.environ, {}, clear=True):
        app = create_app(database_settings_factory=lambda: object(),
                         settings_factory=lambda: Settings(campaign_runner_mode='unknown', _env_file=None))
        with pytest.raises(ValidationError):
            async with app.router.lifespan_context(app):
                pytest.fail('Invalid mode accepted')
    assert not fake_startup_database.opened
    assert not hasattr(app.state, 'runner_mode')


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['missing_package', 'construction'])
async def test_agent_startup_failure_does_not_fall_back_or_leave_state(fake_startup_database, failure):
    import builtins
    from campaign.runner_factory import RunnerConfigurationError

    original_import = builtins.__import__

    def unavailable(name, *args, **kwargs):
        if name == 'agents.development_agent':
            raise ImportError('agent package unavailable')
        return original_import(name, *args, **kwargs)

    fault = (patch('builtins.__import__', side_effect=unavailable) if failure == 'missing_package'
             else patch('campaign.runner_factory.configured_agent', side_effect=ValueError('invalid agent')))
    error = RunnerConfigurationError if failure == 'missing_package' else ValueError
    with patch.dict(os.environ, {}, clear=True), fault, patch('campaign.adk_provider.Client') as provider:
        app = create_app(database_settings_factory=lambda: object(),
                         settings_factory=lambda: Settings(campaign_runner_mode='adk', _env_file=None))
        with pytest.raises(error):
            async with app.router.lifespan_context(app):
                pytest.fail('Failed agents accepted')
        provider.assert_not_called()
    assert fake_startup_database.closed
    for name in ('runners', 'database_pool', 'runner_mode'):
        assert not hasattr(app.state, name)
