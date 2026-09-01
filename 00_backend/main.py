from uuid import UUID

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, status

from campaign.auth import AuthenticatedUser, require_user
from campaign.models import ApprovalRequest, CampaignCreate, CampaignState, Phase
from campaign.config import get_settings
from campaign.orchestrator import CampaignOrchestrator, InvalidTransitionError
from campaign.repository import CampaignNotFoundError, InMemoryCampaignRepository
from campaign.runner_factory import build_phase_runners

settings = get_settings()
app = FastAPI(title="Marketing Campaign Orchestrator API", version="0.1.0")
repository = InMemoryCampaignRepository()
runner_mode = settings.runner_mode
orchestrator = CampaignOrchestrator(repository, runners=build_phase_runners(runner_mode))


def load_campaign(campaign_id: UUID) -> CampaignState:
    try:
        return repository.get(campaign_id)
    except CampaignNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Campaign not found") from exc


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "runner_mode": runner_mode.value}


@app.post("/api/v1/campaigns", response_model=CampaignState, status_code=status.HTTP_201_CREATED)
def create_campaign(
    request: CampaignCreate,
    _user: AuthenticatedUser = Depends(require_user),
) -> CampaignState:
    return repository.create(CampaignState(brief=request.brief, metadata=request.metadata))


@app.get("/api/v1/campaigns", response_model=list[CampaignState])
def list_campaigns(_user: AuthenticatedUser = Depends(require_user)) -> list[CampaignState]:
    return repository.list()


@app.get("/api/v1/campaigns/{campaign_id}", response_model=CampaignState)
def get_campaign(
    campaign_id: UUID,
    _user: AuthenticatedUser = Depends(require_user),
) -> CampaignState:
    return load_campaign(campaign_id)


@app.post("/api/v1/campaigns/{campaign_id}/phases/{phase}/run", response_model=CampaignState)
async def run_phase(
    campaign_id: UUID,
    phase: Phase,
    _user: AuthenticatedUser = Depends(require_user),
) -> CampaignState:
    try:
        return await orchestrator.run_phase(load_campaign(campaign_id), phase)
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/v1/campaigns/{campaign_id}/run", response_model=CampaignState)
async def run_campaign(
    campaign_id: UUID,
    _user: AuthenticatedUser = Depends(require_user),
) -> CampaignState:
    try:
        return await orchestrator.run_until_blocked(load_campaign(campaign_id))
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/v1/campaigns/{campaign_id}/execution/approval", response_model=CampaignState)
def decide_execution(
    campaign_id: UUID,
    request: ApprovalRequest,
    user: AuthenticatedUser = Depends(require_user),
) -> CampaignState:
    try:
        return orchestrator.decide_execution(
            load_campaign(campaign_id), request.decision, user.audit_actor, request.comment)
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=settings.port, log_level=settings.log_level)
