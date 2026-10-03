"""004-R1: settings reach providers without live calls or shared secrets."""
import os
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest

from campaign.adk_provider import ConfiguredGemini
from campaign.config import RunnerMode, Settings
from campaign.runner_factory import build_phase_runners


@pytest.fixture(autouse=True)
def isolated_environment():
    with patch.dict(os.environ, {}, clear=True):
        yield


@pytest.mark.parametrize('values,expected', [
    ({'gemini_api_key': 'gemini-secret'}, {'vertexai': False, 'api_key': 'gemini-secret'}),
    ({'google_api_key': 'google-secret', 'gemini_api_key': 'gemini-secret'},
     {'vertexai': False, 'api_key': 'google-secret'}),
    ({'google_genai_use_vertexai': True, 'google_cloud_project': 'test-project',
      'google_cloud_location': 'europe-west1', 'google_api_key': 'ignored-secret'},
     {'vertexai': True, 'project': 'test-project', 'location': 'europe-west1'}),
    ({}, {}),
])
def test_provider_precedence_and_lazy_construction(values, expected):
    settings = Settings(_env_file=None, **values)
    with patch('campaign.adk_provider.Client') as client:
        model = ConfiguredGemini(model='gemini-2.5-flash', settings=settings)
        client.assert_not_called()
        assert model.api_client is client.return_value
        assert model.api_client is client.return_value
        client.assert_called_once()
        kwargs = dict(client.call_args.kwargs)
        assert kwargs.pop('http_options').headers
        assert kwargs == expected
        assert 'secret' not in repr(model)
        assert 'secret' not in model.model_dump_json()
        assert 'secret' not in repr(settings)


def test_dotenv_credentials_reach_all_agents_without_mutating_exports(tmp_path, caplog):
    env_file = tmp_path / '.env'
    env_file.write_text('CAMPAIGN_RUNNER_MODE=adk\nGEMINI_API_KEY=dotenv-secret\n')
    settings = Settings(_env_file=env_file)
    before = dict(os.environ)
    with patch('campaign.adk_provider.Client') as client:
        runners = build_phase_runners(settings.runner_mode, settings=settings)
        client.assert_not_called()
        from agents.planning_agent import root_agent
        assert isinstance(root_agent.sub_agents[0].model, str)
        for runner in runners.values():
            for agent in runner.runner.agent.sub_agents:
                assert isinstance(agent.model, ConfiguredGemini)
                assert agent.model.api_client is client.return_value
                assert client.call_args.kwargs['api_key'] == 'dotenv-secret'
                assert 'dotenv-secret' not in repr(agent)
        assert dict(os.environ) == before
        assert 'dotenv-secret' not in caplog.text


def test_separate_factories_keep_independent_credentials():
    with patch('campaign.adk_provider.Client') as client:
        first = build_phase_runners(RunnerMode.ADK, settings=Settings(google_api_key='first', _env_file=None))
        second = build_phase_runners(RunnerMode.ADK, settings=Settings(google_api_key='second', _env_file=None))
        for runners, key in [(first, 'first'), (second, 'second')]:
            for runner in runners.values():
                _ = runner.runner.agent.sub_agents[0].model.api_client
                assert client.call_args.kwargs['api_key'] == key


def test_deterministic_mode_never_constructs_provider():
    with patch('campaign.adk_provider.Client') as client:
        build_phase_runners(RunnerMode.DETERMINISTIC, settings=Settings(_env_file=None))
        client.assert_not_called()


@pytest.mark.asyncio
async def test_api_lifespan_passes_settings_to_factory():
    from main import create_app
    settings = Settings(campaign_runner_mode='adk', google_api_key='startup-secret', _env_file=None)

    @asynccontextmanager
    async def pool(_):
        yield object()

    app = create_app(database_settings_factory=lambda: object(), settings_factory=lambda: settings)
    with patch('main.database_pool', pool), patch('main.require_campaign_schema', AsyncMock()), patch('main.build_phase_runners', return_value={}) as factory:
        async with app.router.lifespan_context(app):
            factory.assert_called_once_with(RunnerMode.ADK, settings=settings)


def test_locked_sdk_vertex_uses_adc_path_even_with_environment_key():
    # Client initialization is local; explicit location suppresses SDK key fallback.
    with patch.dict(os.environ, {'GOOGLE_API_KEY': 'environment-secret'}), patch('google.auth.default', side_effect=AssertionError('ADC must remain lazy')):
        model = ConfiguredGemini(model='gemini-2.5-flash', settings=Settings(
            google_genai_use_vertexai=True, google_cloud_project='test-project',
            google_cloud_location='europe-west1', _env_file=None,
        ))
        client = model.api_client
        try:
            assert client.vertexai is True
            assert client._api_client.api_key is None
            assert client._api_client.project == 'test-project'
            assert client._api_client.location == 'europe-west1'
            assert 'environment-secret' not in model.model_dump_json()
        finally:
            client.close()
