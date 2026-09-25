"""Durable lifecycle operations, serialized per campaign across API instances."""
import asyncio
import hashlib
from contextlib import asynccontextmanager

from .authorization import resolve_membership
from .models import (
    ApprovalDecision, CampaignState, CampaignStatus, DevelopmentOutput, ExecutionOutput,
    MonitoringOutput, Phase, PhaseStatus, PlanningOutput, utc_now,
)
from .orchestrator import CampaignOrchestrator, InvalidTransitionError
from .postgres_repository import PostgresCampaignRepository
from .repository import CampaignConflictError


class DatabaseUnavailableError(Exception):
    pass


class PhaseExecutionError(Exception):
    pass


OUTPUT_MODELS = {Phase.PLANNING: PlanningOutput, Phase.DEVELOPMENT: DevelopmentOutput,
                 Phase.EXECUTION: ExecutionOutput, Phase.MONITORING: MonitoringOutput}


class CampaignService:
    def __init__(self, pool, workspace_id, user, runners):
        self.pool, self.workspace_id, self.user, self.runners = pool, workspace_id, user, runners
        self.repository = PostgresCampaignRepository(pool, workspace_id)

    async def _access(self, connection, minimum, campaign_id=None, *, lock=False):
        membership = await resolve_membership(connection, self.user.uid, self.workspace_id, lock=lock)
        stored = await self.repository._get(connection, campaign_id) if campaign_id else None
        membership.require(minimum)  # Scoped existence precedes role denial.
        return membership, stored

    async def create(self, request):
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                membership, _ = await self._access(connection, "editor", lock=True)
                return await self.repository.create_in_transaction(
                    connection, CampaignState(brief=request.brief, metadata=request.metadata), membership.user_id,
                )

    async def get(self, campaign_id):
        async with self.pool.acquire() as connection:
            async with connection.transaction(isolation="repeatable_read", readonly=True):
                _, stored = await self._access(connection, "viewer", campaign_id)
                return stored

    async def list(self):
        async with self.pool.acquire() as connection:
            async with connection.transaction(isolation="repeatable_read", readonly=True):
                await self._access(connection, "viewer")
                rows = await connection.fetch("""
                    SELECT campaign_id FROM campaigns WHERE workspace_id = $1
                    ORDER BY updated_at DESC, campaign_id
                """, self.workspace_id)
                return [await self.repository._get(connection, row["campaign_id"]) for row in rows]

    @asynccontextmanager
    async def _campaign_lock(self, campaign_id, minimum):
        async with self.pool.acquire() as connection:
            async with connection.transaction(isolation="repeatable_read", readonly=True):
                await self._access(connection, minimum, campaign_id)
            key = int.from_bytes(hashlib.sha256(campaign_id.bytes).digest()[:8], "big", signed=True)
            if not await connection.fetchval("SELECT pg_try_advisory_lock($1)", key):
                raise CampaignConflictError("Campaign is already running")
            task = asyncio.current_task()
            lost = False

            def disconnected(_):
                nonlocal lost
                lost = True
                task.cancel()

            connection.add_termination_listener(disconnected)
            try:
                yield connection
                if lost or connection.is_closed():
                    raise DatabaseUnavailableError()
            except asyncio.CancelledError:
                if lost:
                    raise DatabaseUnavailableError() from None
                raise
            finally:
                if not connection.is_closed():
                    connection.remove_termination_listener(disconnected)
                    try:
                        await connection.execute("SELECT pg_advisory_unlock($1)", key)
                    except BaseException:
                        connection.terminate()  # Never return a locked session to the pool.
                        raise

    async def run(self, campaign_id, requested_phase=None):
        async with self._campaign_lock(campaign_id, "runner") as connection:
            while True:
                async with connection.transaction():
                    _, stored = await self._access(connection, "runner", campaign_id, lock=True)
                    state = stored.state
                    phase = CampaignOrchestrator._next_incomplete_phase(state)
                    if requested_phase is not None and requested_phase != phase:
                        raise InvalidTransitionError(f"Next runnable phase is {phase.value}")
                    run = state.phase_runs[phase]
                    # An orphaned running state is retried only while owning its lock.
                    run.status, run.started_at = PhaseStatus.RUNNING, utc_now()
                    run.completed_at, run.error = None, None
                    state.status, state.current_phase = CampaignStatus.IN_PROGRESS, phase
                    state = (await self.repository.save_in_transaction(connection, state)).state
                try:
                    # A runner can mutate only its private input; validate its output
                    # before changing canonical state or writing to the database.
                    output = await self.runners[phase].run(state.model_copy(deep=True))
                    output = OUTPUT_MODELS[phase].model_validate(output)
                except Exception:
                    async with connection.transaction():
                        await self._access(connection, "runner", campaign_id, lock=True)
                        state.phase_runs[phase].status = PhaseStatus.FAILED
                        state.phase_runs[phase].error = "Phase execution failed; retry the phase"
                        state.status = CampaignStatus.FAILED
                        await self.repository.save_in_transaction(connection, state)
                    raise PhaseExecutionError() from None
                async with connection.transaction():
                    await self._access(connection, "runner", campaign_id, lock=True)
                    setattr(state, phase.value, output)
                    state.phase_runs[phase].completed_at = utc_now()
                    state.phase_runs[phase].status = (
                        PhaseStatus.AWAITING_APPROVAL if phase == Phase.EXECUTION else PhaseStatus.COMPLETED
                    )
                    state.status = (CampaignStatus.AWAITING_APPROVAL if phase == Phase.EXECUTION else
                                    CampaignStatus.COMPLETED if phase == Phase.MONITORING else CampaignStatus.IN_PROGRESS)
                    stored = await self.repository.save_in_transaction(connection, state)
                if requested_phase or stored.state.status in {CampaignStatus.AWAITING_APPROVAL, CampaignStatus.COMPLETED}:
                    return stored

    async def approve(self, campaign_id, request):
        async with self._campaign_lock(campaign_id, "approver") as connection:
            async with connection.transaction():
                membership, stored = await self._access(connection, "approver", campaign_id, lock=True)
                state = stored.state
                run = state.phase_runs[Phase.EXECUTION]
                if run.status != PhaseStatus.AWAITING_APPROVAL:
                    raise InvalidTransitionError("Execution is not awaiting approval")
                if request.decision == ApprovalDecision.APPROVED:
                    run.status = PhaseStatus.COMPLETED
                    state.current_phase, state.status = Phase.MONITORING, CampaignStatus.IN_PROGRESS
                else:
                    run.status, run.error = PhaseStatus.FAILED, request.comment or "Execution rejected"
                    state.status = CampaignStatus.FAILED
                # Generic save retains history; append the new audit event in the
                # same transaction afterward. Failure of either write rolls back both.
                saved = await self.repository.save_in_transaction(connection, state)
                await connection.execute("""
                    INSERT INTO approval_events
                    (campaign_id, workspace_id, actor_user_id, actor_firebase_uid, actor,
                     phase, decision, comment, campaign_version)
                    VALUES ($1, $2, $3, $4, $5, 'execution', $6, $7, $8)
                """, campaign_id, self.workspace_id, membership.user_id, self.user.uid,
                    self.user.audit_actor, request.decision.value, request.comment, saved.state.version)
                return await self.repository._get(connection, campaign_id)
