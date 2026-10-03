"""004-R2/004-R5: cleanup preserves outcomes and finishes before cancellation exits."""
import asyncio
from unittest.mock import AsyncMock

import pytest

from campaign.adk_runner import AdkRunnerError
from campaign.models import Phase
from tests.test_adk_context import RecordingRunner, adapter, campaign


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome', ['success', 'invalid', 'provider', 'prompt'])
@pytest.mark.parametrize('cleanup_fails', [False, True])
async def test_cleanup_preserves_result_or_original_error(outcome, cleanup_fails, caplog):
    runner = RecordingRunner(Phase.PLANNING, fail_first=outcome == 'invalid')
    service = runner.session_service
    service.create_session = AsyncMock(wraps=service.create_session)
    original_delete = service.delete_session
    service.delete_session = AsyncMock(side_effect=RuntimeError('private cleanup secret') if cleanup_fails else original_delete)
    instance = adapter(Phase.PLANNING, runner)
    original_error = RuntimeError('private invocation secret')
    if outcome == 'provider':
        async def fail(**kwargs):
            raise original_error
            yield  # async generator interface
        runner.run_async = fail
    if outcome == 'prompt':
        def fail_prompt(_):
            raise original_error
        instance._build_prompt = fail_prompt
    if outcome == 'success':
        assert (await instance.run(campaign())).goals == ['planning-marker']
    else:
        with pytest.raises(AdkRunnerError if outcome == 'invalid' else RuntimeError) as error:
            await instance.run(campaign())
        if outcome in ('provider', 'prompt'):
            assert error.value is original_error
    service.delete_session.assert_awaited_once()
    kwargs = service.delete_session.call_args.kwargs
    assert kwargs['app_name'] == 'planning_agent'
    assert kwargs['user_id'] == service.create_session.call_args.kwargs['user_id']
    if not cleanup_fails:
        assert await service.get_session(**kwargs) is None
    else:
        assert 'ADK session cleanup failed for phase planning' in caplog.text
    assert 'private' not in caplog.text
    assert kwargs['session_id'] not in caplog.text


@pytest.mark.asyncio
async def test_creation_failure_does_not_attempt_deletion():
    runner = RecordingRunner(Phase.PLANNING)
    runner.session_service.create_session = AsyncMock(side_effect=RuntimeError('creation failed'))
    runner.session_service.delete_session = AsyncMock()
    with pytest.raises(RuntimeError, match='creation failed'):
        await adapter(Phase.PLANNING, runner).run(campaign())
    runner.session_service.delete_session.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('cancel_during_run', [False, True])
@pytest.mark.parametrize('cleanup_fails', [False, True])
async def test_cancellation_waits_for_cleanup_even_when_cancelled_again(cancel_during_run, cleanup_fails, caplog):
    runner = RecordingRunner(Phase.PLANNING)
    started, deleting, finish_delete = asyncio.Event(), asyncio.Event(), asyncio.Event()
    original_delete = runner.session_service.delete_session
    deleted = []

    async def delayed_delete(**kwargs):
        deleting.set()
        await finish_delete.wait()
        deleted.append(kwargs)
        if cleanup_fails:
            raise RuntimeError('private cleanup secret')
        await original_delete(**kwargs)

    runner.session_service.delete_session = delayed_delete
    if cancel_during_run:
        async def waiting_run(**kwargs):
            started.set()
            await asyncio.Event().wait()
            yield
        runner.run_async = waiting_run
    task = asyncio.create_task(adapter(Phase.PLANNING, runner).run(campaign()))
    try:
        if cancel_during_run:
            await asyncio.wait_for(started.wait(), 2)
            task.cancel()
        await asyncio.wait_for(deleting.wait(), 2)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        finish_delete.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 2)
        assert len(deleted) == 1
        if not cleanup_fails:
            assert await runner.session_service.get_session(**deleted[0]) is None
        assert 'private' not in caplog.text
    finally:
        finish_delete.set()
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
