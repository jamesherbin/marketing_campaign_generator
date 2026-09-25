"""Normalized, transactional storage bound to one server-validated workspace.

This adapter does not authorize callers. The API must resolve membership before
constructing it, and the forthcoming mutation service must recheck permission in
its write transaction. Generic saves cannot append or alter approval history.
"""
from __future__ import annotations

import json
from uuid import UUID

import asyncpg

from .models import ApprovalRecord, CampaignState
from .repository import (
    CampaignConflictError, CampaignNotFoundError, StoredApproval, StoredCampaign,
)


# Identifiers are fixed application constants. All values use SQL parameters.
FIELDS = {
    "campaign_briefs": ("brand", "campaign_goal", "target_audience", "duration_weeks",
                        "budget", "currency", "preferred_channels", "success_metrics",
                        "industry", "product", "constraints"),
    "planning_outputs": ("goals", "measurable_objectives", "audience_segments",
                         "positioning_statement", "value_proposition", "key_messages",
                         "recommended_channels", "budget_by_channel"),
    "development_outputs": ("creative_direction", "media_plan"),
    "execution_outputs": ("publication_summary",),
    "monitoring_outputs": ("kpis", "analysis", "recommendations", "stakeholder_summary"),
    "content_assets": ("asset_id", "channel", "format", "headline", "body", "call_to_action", "status"),
    "scheduled_activities": ("channel", "action", "scheduled_for", "status"),
    "phase_runs": ("status", "started_at", "completed_at", "error"),
}
JSON_FIELDS = {"budget_by_channel", "media_plan", "kpis"}
OUTPUTS = ("planning", "development", "execution", "monitoring")


def _values(table, data):
    return [json.dumps(data[key], allow_nan=False) if key in JSON_FIELDS else data[key]
            for key in FIELDS[table]]


def _payload(table, row):
    return {key: json.loads(row[key]) if key in JSON_FIELDS else row[key]
            for key in FIELDS[table]}


async def _upsert(connection, table, campaign_id, data, *, creating=False):
    fields = ("campaign_id", *FIELDS[table])
    args = [campaign_id, *_values(table, data)]
    placeholders = ", ".join(f"${i}" for i in range(1, len(args) + 1))
    assignments = ", ".join(f"{key} = EXCLUDED.{key}" for key in FIELDS[table])
    sql = f"INSERT INTO {table} ({', '.join(fields)}) VALUES ({placeholders})"
    if not creating:
        sql += f" ON CONFLICT (campaign_id) DO UPDATE SET {assignments}"
    await connection.execute(sql, *args)


class PostgresCampaignRepository:
    def __init__(self, pool: asyncpg.Pool, workspace_id: UUID):
        self.pool = pool
        self.workspace_id = workspace_id

    async def create(self, campaign: CampaignState, created_by_user_id: UUID) -> StoredCampaign:
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                return await self.create_in_transaction(connection, campaign, created_by_user_id)

    async def create_in_transaction(self, connection, campaign, created_by_user_id):
        if campaign.approvals:
            raise ValueError("Approval history requires the dedicated approval/import transaction")
        try:
            await connection.execute("""
                INSERT INTO campaigns
                (campaign_id, workspace_id, created_by_user_id, version, status,
                 current_phase, metadata, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """, campaign.campaign_id, self.workspace_id, created_by_user_id,
                campaign.version, campaign.status.value, campaign.current_phase.value,
                json.dumps(campaign.metadata, allow_nan=False), campaign.created_at,
                campaign.updated_at)
            await self._write_snapshot(connection, campaign, creating=True)
        except asyncpg.UniqueViolationError:
            raise CampaignConflictError("Campaign or asset identifier already exists") from None
        return await self._get(connection, campaign.campaign_id)


    async def get(self, campaign_id: UUID) -> StoredCampaign:
        async with self.pool.acquire() as connection:
            async with connection.transaction(isolation="repeatable_read", readonly=True):
                return await self._get(connection, campaign_id)

    async def list(self) -> list[StoredCampaign]:
        async with self.pool.acquire() as connection:
            async with connection.transaction(isolation="repeatable_read", readonly=True):
                rows = await connection.fetch("""
                    SELECT campaign_id FROM campaigns WHERE workspace_id = $1
                    ORDER BY updated_at DESC, campaign_id
                """, self.workspace_id)
                return [await self._get(connection, row["campaign_id"]) for row in rows]

    async def save(self, campaign: CampaignState) -> StoredCampaign:
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                return await self.save_in_transaction(connection, campaign)

    async def save_in_transaction(self, connection, campaign):
        # Lock scoped parent before reading children or checking history.
        version = await connection.fetchval("""
            SELECT version FROM campaigns
            WHERE campaign_id = $1 AND workspace_id = $2 FOR UPDATE
        """, campaign.campaign_id, self.workspace_id)
        if version is None:
            raise CampaignNotFoundError(str(campaign.campaign_id))
        if version != campaign.version:
            raise CampaignConflictError("Campaign version is stale")
        stored = await self._get(connection, campaign.campaign_id)
        if stored.state.approvals != campaign.approvals:
            raise ValueError("Approval history cannot be changed by a generic save")
        result = await connection.execute("""
            UPDATE campaigns SET status = $1, current_phase = $2,
                metadata = $3, version = version + 1
            WHERE campaign_id = $4 AND workspace_id = $5 AND version = $6
        """, campaign.status.value, campaign.current_phase.value,
            json.dumps(campaign.metadata, allow_nan=False), campaign.campaign_id,
            self.workspace_id, campaign.version)
        if result != "UPDATE 1":
            raise CampaignConflictError("Campaign version is stale")
        try:
            await self._write_snapshot(connection, campaign)
        except asyncpg.UniqueViolationError:
            raise CampaignConflictError("Asset identifier already exists") from None
        return await self._get(connection, campaign.campaign_id)


    async def _get(self, connection, campaign_id):
        row = await connection.fetchrow("""
            SELECT * FROM campaigns WHERE campaign_id = $1 AND workspace_id = $2
        """, campaign_id, self.workspace_id)
        if row is None:
            raise CampaignNotFoundError(str(campaign_id))
        data = dict(row)
        workspace_id = data.pop("workspace_id")
        created_by_user_id = data.pop("created_by_user_id")
        data["metadata"] = json.loads(data["metadata"])
        brief = await connection.fetchrow("SELECT * FROM campaign_briefs WHERE campaign_id = $1", campaign_id)
        if brief is None:
            raise RuntimeError("Stored campaign has no brief")
        data["brief"] = _payload("campaign_briefs", brief)
        for phase in OUTPUTS:
            table = f"{phase}_outputs"
            output = await connection.fetchrow(f"SELECT * FROM {table} WHERE campaign_id = $1", campaign_id)
            data[phase] = _payload(table, output) if output else None
        for phase, table, field in (("development", "content_assets", "assets"),
                                    ("execution", "scheduled_activities", "activities")):
            if data[phase] is not None:
                rows = await connection.fetch(
                    f"SELECT * FROM {table} WHERE campaign_id = $1 ORDER BY position", campaign_id,
                )
                data[phase][field] = [_payload(table, item) for item in rows]
        phases = await connection.fetch("SELECT * FROM phase_runs WHERE campaign_id = $1", campaign_id)
        if {item["phase"] for item in phases} != set(OUTPUTS):
            raise RuntimeError("Stored campaign has incomplete phase records")
        data["phase_runs"] = {item["phase"]: _payload("phase_runs", item) for item in phases}
        history = []
        for table, order, source in (
            ("legacy_approval_history", "position", "legacy_unverified"),
            ("approval_events", "campaign_version, decided_at, approval_event_id", "firebase_verified"),
        ):
            rows = await connection.fetch(
                f"SELECT * FROM {table} WHERE campaign_id = $1 AND workspace_id = $2 ORDER BY {order}",
                campaign_id, self.workspace_id,
            )
            for item in rows:
                history.append(StoredApproval(
                    record=ApprovalRecord.model_validate(dict(item)),
                    actor_firebase_uid=item["actor_firebase_uid"] if source == "firebase_verified" else None,
                    identity_source=source,
                ))
        data["approvals"] = [item.record for item in history]
        return StoredCampaign(CampaignState.model_validate(data), workspace_id, created_by_user_id, tuple(history))

    async def _write_snapshot(self, connection, campaign, *, creating=False):
        campaign_id = campaign.campaign_id
        await _upsert(connection, "campaign_briefs", campaign_id, campaign.brief.model_dump(), creating=creating)
        for phase in OUTPUTS:
            table = f"{phase}_outputs"
            output = getattr(campaign, phase)
            if output is None:
                if not creating:
                    await connection.execute(f"DELETE FROM {table} WHERE campaign_id = $1", campaign_id)
            else:
                await _upsert(connection, table, campaign_id, output.model_dump(), creating=creating)
        for phase, table, field in (("development", "content_assets", "assets"),
                                    ("execution", "scheduled_activities", "activities")):
            if not creating:
                await connection.execute(f"DELETE FROM {table} WHERE campaign_id = $1", campaign_id)
            output = getattr(campaign, phase)
            if output:
                fields = ("campaign_id", "position", *FIELDS[table])
                placeholders = ", ".join(f"${i}" for i in range(1, len(fields) + 1))
                for position, item in enumerate(getattr(output, field)):
                    await connection.execute(
                        f"INSERT INTO {table} ({', '.join(fields)}) VALUES ({placeholders})",
                        campaign_id, position, *_values(table, item.model_dump()),
                    )
        for phase, run in campaign.phase_runs.items():
            sql = """
                INSERT INTO phase_runs (campaign_id, phase, status, started_at, completed_at, error)
                VALUES ($1, $2, $3, $4, $5, $6)
            """
            if not creating:
                sql += """ ON CONFLICT (campaign_id, phase) DO UPDATE SET
                    status = EXCLUDED.status, started_at = EXCLUDED.started_at,
                    completed_at = EXCLUDED.completed_at, error = EXCLUDED.error
                """
            await connection.execute(sql, campaign_id, phase.value, run.status.value,
                                     run.started_at, run.completed_at, run.error)
