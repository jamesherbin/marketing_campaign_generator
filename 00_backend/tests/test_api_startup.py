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
