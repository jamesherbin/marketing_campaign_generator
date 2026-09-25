import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio

from campaign.config import DatabaseSettings
from campaign.database import database_pool, require_campaign_schema
from campaign.models import (
    ApprovalDecision, ApprovalRecord, CampaignBrief, CampaignState, ContentAsset,
    DevelopmentOutput, ExecutionOutput, MonitoringOutput, Phase, PhaseRun,
    PlanningOutput, ScheduledActivity,
)
from campaign.postgres_repository import PostgresCampaignRepository
from campaign.repository import CampaignConflictError, CampaignNotFoundError

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
STAMP = datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def complete_snapshot():
    return CampaignState(
        brief=CampaignBrief(brand="Example", campaign_goal="Grow", target_audience=["A", "B"],
                            duration_weeks=4, budget=123.45),
        metadata={"nested": {"list": [1, None, "value"]}},
        status="completed", current_phase="monitoring", version=8,
        created_at=STAMP, updated_at=STAMP,
        planning=PlanningOutput(
            goals=["Grow"], measurable_objectives=["Measure"], audience_segments=["A", "B"],
            positioning_statement="Position", value_proposition="Value", key_messages=["First", "Second"],
            recommended_channels=["email", "social"], budget_by_channel={"email": 100, "social": 23.45},
        ),
        development=DevelopmentOutput(
            creative_direction="Direction", media_plan={"weeks": [1, 2], "optional": None},
            assets=[ContentAsset(channel="email", format="text", headline="First", body="Body"),
                    ContentAsset(channel="social", format="image", headline="Second", body="Other")],
        ),
        execution=ExecutionOutput(publication_summary="Prepared", activities=[
            ScheduledActivity(channel="social", action="Second", scheduled_for=STAMP),
            ScheduledActivity(channel="email", action="First", scheduled_for=None),
        ]),
        monitoring=MonitoringOutput(kpis={"unknown": None, "zero": 0, "rate": 1.25, "label": "none"},
                                    analysis=["A"], recommendations=["B"], stakeholder_summary="C"),
        phase_runs={phase: PhaseRun(status="completed", started_at=STAMP, completed_at=STAMP)
                    for phase in Phase},
    )


@pytest_asyncio.fixture
async def identities(migrated_pool):
    user = await migrated_pool.fetchval("""
        INSERT INTO users (firebase_uid, email) VALUES ('verified-uid', NULL) RETURNING user_id
    """)
    workspaces = []
    for slug in ("first", "second"):
        workspaces.append(await migrated_pool.fetchval("""
            INSERT INTO workspaces (name, slug, created_by_user_id) VALUES ($1, $1, $2)
            RETURNING workspace_id
        """, slug, user))
    return user, workspaces


async def test_full_snapshot_survives_pool_restart(migrated_pool, isolated_database_url, identities):
    user, (workspace, _) = identities
    repository = PostgresCampaignRepository(migrated_pool, workspace)
    state = complete_snapshot()
    result = await repository.create(state, user)
    assert result.state == state
    async with database_pool(DatabaseSettings(url=isolated_database_url, _env_file=None)) as reopened:
        fresh = await PostgresCampaignRepository(reopened, workspace).get(state.campaign_id)
        assert fresh.state == state
        assert fresh.workspace_id == workspace
        assert fresh.created_by_user_id == user


async def test_draft_optional_outputs_and_workspace_isolation(migrated_pool, identities):
    user, (first, second) = identities
    a, b = (PostgresCampaignRepository(migrated_pool, workspace) for workspace in (first, second))
    state = CampaignState(brief=complete_snapshot().brief)
    assert (await a.create(state, user)).state == state
    assert [item.state.campaign_id for item in await a.list()] == [state.campaign_id]
    assert await b.list() == []
    for campaign_id in (state.campaign_id, uuid4()):
        with pytest.raises(CampaignNotFoundError):
            await b.get(campaign_id)
    with pytest.raises(CampaignNotFoundError):
        await b.save(state)
    assert (await a.get(state.campaign_id)).state == state


async def test_save_replaces_collections_preserves_ids_and_checks_versions(migrated_pool, identities):
    user, (workspace, _) = identities
    repo = PostgresCampaignRepository(migrated_pool, workspace)
    original = complete_snapshot()
    await repo.create(original, user)
    edited = original.model_copy(deep=True)
    edited.development.assets.reverse()
    edited.execution.activities.pop()
    edited.monitoring = None
    saved = (await repo.save(edited)).state
    assert saved.version == original.version + 1
    assert saved.created_at == original.created_at
    assert saved.updated_at > original.updated_at
    assert saved.development == edited.development
    assert saved.execution == edited.execution
    assert saved.monitoring is None
    assert original.version == 8  # Failed or successful saves don't mutate caller state.
    with pytest.raises(CampaignConflictError):
        await repo.save(original)
    assert (await repo.get(original.campaign_id)).state == saved


async def test_concurrent_saves_have_one_winner(migrated_pool, identities):
    user, (workspace, _) = identities
    repo = PostgresCampaignRepository(migrated_pool, workspace)
    state = complete_snapshot()
    await repo.create(state, user)
    results = await asyncio.gather(repo.save(state), repo.save(state), return_exceptions=True)
    assert sum(isinstance(result, CampaignConflictError) for result in results) == 1
    assert (await repo.get(state.campaign_id)).state.version == state.version + 1


async def test_child_constraint_failure_rolls_back_parent_and_children(migrated_pool, identities):
    user, (workspace, _) = identities
    repo = PostgresCampaignRepository(migrated_pool, workspace)
    state = complete_snapshot()
    await repo.create(state, user)
    invalid = state.model_copy(deep=True)
    invalid.metadata = {"changed": True}
    invalid.phase_runs[Phase.MONITORING].completed_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(asyncpg.CheckViolationError):
        await repo.save(invalid)
    assert (await repo.get(state.campaign_id)).state == state
    invalid.campaign_id = uuid4()
    for asset in invalid.development.assets:
        asset.asset_id = uuid4()
    with pytest.raises(asyncpg.CheckViolationError):
        await repo.create(invalid, user)
    with pytest.raises(CampaignNotFoundError):
        await repo.get(invalid.campaign_id)


async def test_asset_collision_cannot_modify_another_campaign(migrated_pool, identities):
    user, (first, second) = identities
    original = complete_snapshot()
    a = PostgresCampaignRepository(migrated_pool, first)
    b = PostgresCampaignRepository(migrated_pool, second)
    await a.create(original, user)
    duplicate = original.model_copy(deep=True)
    duplicate.campaign_id = uuid4()
    with pytest.raises(CampaignConflictError):
        await b.create(duplicate, user)
    assert await b.list() == []
    assert (await a.get(original.campaign_id)).state == original


async def test_approval_history_is_preserved_and_cannot_be_changed_by_save(migrated_pool, identities):
    user, (workspace, _) = identities
    repo = PostgresCampaignRepository(migrated_pool, workspace)
    state = complete_snapshot()
    await repo.create(state, user)
    await migrated_pool.execute("""
        INSERT INTO legacy_approval_history
        (campaign_id, workspace_id, position, phase, decision, actor, decided_at)
        VALUES ($1, $2, 0, 'execution', 'rejected', 'Historical reviewer', $3)
    """, state.campaign_id, workspace, STAMP)
    await migrated_pool.execute("""
        INSERT INTO approval_events
        (campaign_id, workspace_id, actor_user_id, actor, phase, decision, campaign_version)
        VALUES ($1, $2, $3, 'Current reviewer', 'execution', 'approved', 8)
    """, state.campaign_id, workspace, user)
    stored = await repo.get(state.campaign_id)
    assert [item.identity_source for item in stored.approval_history] == ["legacy_unverified", "firebase_verified"]
    assert [item.actor_firebase_uid for item in stored.approval_history] == [None, "verified-uid"]
    saved = await repo.save(stored.state)
    assert saved.approval_history == stored.approval_history
    saved.state.approvals.clear()
    with pytest.raises(ValueError, match="history"):
        await repo.save(saved.state)
    forged = complete_snapshot()
    forged.approvals.append(ApprovalRecord(phase=Phase.EXECUTION, decision=ApprovalDecision.APPROVED, actor="fake"))
    with pytest.raises(ValueError, match="history"):
        await repo.create(forged, user)
    assert len((await repo.get(state.campaign_id)).state.approvals) == 2


async def test_read_is_a_consistent_snapshot_during_concurrent_save(migrated_pool, identities, monkeypatch):
    user, (workspace, _) = identities
    repo = PostgresCampaignRepository(migrated_pool, workspace)
    state = complete_snapshot()
    await repo.create(state, user)
    changed = state.model_copy(deep=True)
    changed.brief.brand = "Changed"
    changed.metadata = {"revision": "new"}
    writer = PostgresCampaignRepository(migrated_pool, workspace)
    original_get = repo._get

    class InterleavedConnection:
        def __init__(self, connection):
            self.connection = connection

        async def fetchrow(self, sql, *args):
            if "FROM campaign_briefs" in sql:
                await writer.save(changed)
            return await self.connection.fetchrow(sql, *args)

        def __getattr__(self, name):
            return getattr(self.connection, name)

    async def interleaved_get(connection, campaign_id):
        return await original_get(InterleavedConnection(connection), campaign_id)

    monkeypatch.setattr(repo, "_get", interleaved_get)
    assert (await repo.get(state.campaign_id)).state == state
    assert (await writer.get(state.campaign_id)).state.brief.brand == "Changed"


async def test_repository_works_with_runtime_grants(restricted_pools, identities):
    user, (workspace, _) = identities
    pool = restricted_pools["runtime"]
    await require_campaign_schema(pool)
    repo = PostgresCampaignRepository(pool, workspace)
    state = complete_snapshot()
    await repo.create(state, user)
    state.metadata = {"runtime": True}
    assert (await repo.save(state)).state.metadata == {"runtime": True}
    assert len(await repo.list()) == 1
