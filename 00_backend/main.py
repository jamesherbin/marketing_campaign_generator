from contextlib import asynccontextmanager
from typing import Literal
from uuid import UUID

import asyncpg
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from campaign.auth import AuthenticatedUser, require_user
from campaign.authorization import AccessDeniedError, list_workspaces
from campaign.config import DatabaseSettings, get_settings
from campaign.database import database_pool, require_campaign_schema
from campaign.models import ApprovalRecord, ApprovalRequest, CampaignCreate, CampaignState, Phase
from campaign.orchestrator import InvalidTransitionError
from campaign.repository import CampaignConflictError, CampaignNotFoundError
from campaign.runner_factory import build_phase_runners
from campaign.service import CampaignService, DatabaseUnavailableError, PhaseExecutionError


class ApprovalResponse(ApprovalRecord):
    actor_firebase_uid: str | None
    identity_source: Literal['firebase_verified', 'legacy_unverified']


class CampaignResponse(CampaignState):
    workspace_id: UUID
    created_by_user_id: UUID
    approvals: list[ApprovalResponse]


class WorkspaceResponse(BaseModel):
    workspace_id: UUID
    name: str
    slug: str
    role: Literal['viewer', 'editor', 'runner', 'approver']


def response(stored):
    data = stored.state.model_dump()
    data.update(workspace_id=stored.workspace_id, created_by_user_id=stored.created_by_user_id)
    data['approvals'] = [dict(**item.record.model_dump(), actor_firebase_uid=item.actor_firebase_uid,
                              identity_source=item.identity_source) for item in stored.approval_history]
    return CampaignResponse.model_validate(data)


def create_app(database_settings_factory=DatabaseSettings, settings_factory=get_settings):
    @asynccontextmanager
    async def lifespan(app):
        settings = settings_factory()
        async with database_pool(database_settings_factory()) as pool:
            await require_campaign_schema(pool)
            app.state.database_pool = pool
            app.state.runner_mode = settings.runner_mode
            app.state.runners = build_phase_runners(settings.runner_mode)
            try:
                yield
            finally:
                del app.state.database_pool
                del app.state.runners

    app = FastAPI(title='Marketing Campaign Orchestrator API', version='0.2.0', lifespan=lifespan)

    async def service(request: Request, user: AuthenticatedUser = Depends(require_user)):
        try:
            workspace_id = UUID(request.headers.get('X-Workspace-ID', ''))
        except ValueError:
            raise HTTPException(422, 'X-Workspace-ID must be a UUID') from None
        return CampaignService(request.app.state.database_pool, workspace_id, user, request.app.state.runners)

    @app.exception_handler(AccessDeniedError)
    async def access_denied(_request, error):
        return JSONResponse({'detail': error.detail}, status_code=error.status_code)

    @app.exception_handler(CampaignNotFoundError)
    async def not_found(_request, _error):
        return JSONResponse({'detail': 'Resource not found'}, status_code=404)

    async def conflict(_request, error):
        return JSONResponse({'detail': str(error)}, status_code=409)
    app.add_exception_handler(CampaignConflictError, conflict)
    app.add_exception_handler(InvalidTransitionError, conflict)

    async def unavailable(_request, _error):
        return JSONResponse({'detail': 'Database unavailable'}, status_code=503)
    for error_type in (asyncpg.PostgresError, asyncpg.InterfaceError, OSError, TimeoutError, DatabaseUnavailableError):
        app.add_exception_handler(error_type, unavailable)

    @app.exception_handler(PhaseExecutionError)
    async def phase_failed(_request, _error):
        return JSONResponse({'detail': 'Phase execution failed; retry the phase'}, status_code=502)

    @app.get('/health')
    async def health(request: Request):
        return {'status': 'ok', 'runner_mode': request.app.state.runner_mode.value}

    @app.get('/api/v1/workspaces', response_model=list[WorkspaceResponse])
    async def workspaces(request: Request, user: AuthenticatedUser = Depends(require_user)):
        async with request.app.state.database_pool.acquire() as connection:
            async with connection.transaction(isolation='repeatable_read', readonly=True):
                return await list_workspaces(connection, user.uid)

    @app.post('/api/v1/campaigns', response_model=CampaignResponse, status_code=201)
    async def create_campaign(payload: CampaignCreate, svc: CampaignService = Depends(service)):
        return response(await svc.create(payload))

    @app.get('/api/v1/campaigns', response_model=list[CampaignResponse])
    async def campaigns(svc: CampaignService = Depends(service)):
        return [response(item) for item in await svc.list()]

    @app.get('/api/v1/campaigns/{campaign_id}', response_model=CampaignResponse)
    async def campaign(campaign_id: UUID, svc: CampaignService = Depends(service)):
        return response(await svc.get(campaign_id))

    @app.post('/api/v1/campaigns/{campaign_id}/run', response_model=CampaignResponse)
    async def run_campaign(campaign_id: UUID, svc: CampaignService = Depends(service)):
        return response(await svc.run(campaign_id))

    @app.post('/api/v1/campaigns/{campaign_id}/phases/{phase}/run', response_model=CampaignResponse)
    async def run_phase(campaign_id: UUID, phase: Phase, svc: CampaignService = Depends(service)):
        return response(await svc.run(campaign_id, phase))

    @app.post('/api/v1/campaigns/{campaign_id}/execution/approval', response_model=CampaignResponse)
    async def approve(campaign_id: UUID, payload: ApprovalRequest, svc: CampaignService = Depends(service)):
        return response(await svc.approve(campaign_id, payload))

    return app


app = create_app()

if __name__ == '__main__':
    settings = get_settings()
    uvicorn.run(app, host='0.0.0.0', port=settings.port, log_level=settings.log_level)
