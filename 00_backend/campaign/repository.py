from threading import RLock
from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from .models import ApprovalRecord, CampaignState


class CampaignNotFoundError(KeyError):
    pass


class CampaignConflictError(ValueError):
    pass


@dataclass(frozen=True)
class StoredApproval:
    record: ApprovalRecord
    actor_firebase_uid: str | None
    identity_source: Literal["firebase_verified", "legacy_unverified"]


@dataclass(frozen=True)
class StoredCampaign:
    state: CampaignState
    workspace_id: UUID
    created_by_user_id: UUID
    approval_history: tuple[StoredApproval, ...] = ()


class CampaignRepository(Protocol):
    """Async, workspace-scoped storage contract; callers enforce membership/roles."""

    async def create(self, campaign: CampaignState, created_by_user_id: UUID) -> StoredCampaign: ...
    async def get(self, campaign_id: UUID) -> StoredCampaign: ...
    async def list(self) -> list[StoredCampaign]: ...
    async def save(self, campaign: CampaignState) -> StoredCampaign: ...


class InMemoryCampaignRepository:
    """Thread-safe development repository; replace with a durable adapter in production."""

    def __init__(self) -> None:
        self._campaigns: dict[UUID, CampaignState] = {}
        self._lock = RLock()

    def create(self, campaign: CampaignState) -> CampaignState:
        with self._lock:
            self._campaigns[campaign.campaign_id] = campaign.model_copy(deep=True)
        return campaign

    def get(self, campaign_id: UUID) -> CampaignState:
        with self._lock:
            campaign = self._campaigns.get(campaign_id)
            if campaign is None:
                raise CampaignNotFoundError(str(campaign_id))
            return campaign.model_copy(deep=True)

    def list(self) -> list[CampaignState]:
        with self._lock:
            return [item.model_copy(deep=True) for item in self._campaigns.values()]

    def save(self, campaign: CampaignState) -> CampaignState:
        with self._lock:
            if campaign.campaign_id not in self._campaigns:
                raise CampaignNotFoundError(str(campaign.campaign_id))
            campaign.version += 1
            self._campaigns[campaign.campaign_id] = campaign.model_copy(deep=True)
        return campaign
