"""Deploy engine REST + WebSocket endpoints."""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import json
import logging

from app.core.database import get_db
from app.schemas.deployment import (
    ServerCreate, ServerResponse, ServerPingResult,
    EnvironmentCreate, EnvironmentUpdate, EnvironmentResponse,
    DeploymentCreate, DeploymentResponse, DeploymentListResponse,
    RollbackRequest, PromoteRequest, PromoteResponse,
    DeployStats,
)
from app.services.deploy_service import DeployService
from app.services.orchestrator import orchestrator
from app.api.v1.deps import get_current_user, CurrentUser

router = APIRouter()
logger = logging.getLogger("jarviis.deploy.api")


# ── Servers ───────────────────────────────────────────────────

@router.post("/orgs/{org_id}/servers", response_model=ServerResponse, status_code=201, tags=["Servers"])
async def add_server(
    org_id: str,
    data: ServerCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = DeployService(db)
    return await svc.create_server(data, org_id)


@router.get("/orgs/{org_id}/servers", response_model=list[ServerResponse], tags=["Servers"])
async def list_servers(
    org_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = DeployService(db)
    return await svc.list_servers(org_id)


@router.post("/orgs/{org_id}/servers/{server_id}/ping", response_model=ServerPingResult, tags=["Servers"])
async def ping_server(
    org_id: str,
    server_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Test SSH connectivity and Docker availability on a server."""
    svc = DeployService(db)
    result = await svc.ping_server(server_id, org_id)
    return {**result, "server_id": server_id}


# ── Environments ──────────────────────────────────────────────

@router.post("/orgs/{org_id}/projects/{project_id}/environments",
             response_model=EnvironmentResponse, status_code=201, tags=["Environments"])
async def create_environment(
    org_id: str,
    project_id: str,
    data: EnvironmentCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = DeployService(db)
    return await svc.create_environment(project_id, org_id, data)


@router.get("/orgs/{org_id}/projects/{project_id}/environments",
            response_model=list[EnvironmentResponse], tags=["Environments"])
async def list_environments(
    org_id: str,
    project_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = DeployService(db)
    return await svc.list_environments(project_id, org_id)


@router.patch("/orgs/{org_id}/environments/{env_id}",
              response_model=EnvironmentResponse, tags=["Environments"])
async def update_environment(
    org_id: str,
    env_id: str,
    data: EnvironmentUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = DeployService(db)
    return await svc.update_environment(env_id, org_id, data)


# ── Deployments ───────────────────────────────────────────────

@router.post("/orgs/{org_id}/projects/{project_id}/deployments",
             response_model=DeploymentResponse, status_code=201, tags=["Deployments"])
async def create_deployment(
    org_id: str,
    project_id: str,
    data: DeploymentCreate,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger a new deployment to an environment."""
    svc = DeployService(db)
    dep = await svc.create_deployment(project_id, org_id, current_user["sub"], data)

    # Run pipeline in background
    background_tasks.add_task(orchestrator.run, dep.id, db)

    return dep


@router.get("/orgs/{org_id}/projects/{project_id}/deployments",
            response_model=DeploymentListResponse, tags=["Deployments"])
async def list_deployments(
    org_id: str,
    project_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    environment_id: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = DeployService(db)
    deps, total = await svc.list_deployments(org_id, project_id, environment_id, page, page_size)
    return {"deployments": deps, "total": total, "page": page, "page_size": page_size}


@router.get("/orgs/{org_id}/deployments/{dep_id}",
            response_model=DeploymentResponse, tags=["Deployments"])
async def get_deployment(
    org_id: str,
    dep_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = DeployService(db)
    dep = await svc.get_deployment(dep_id, org_id)
    if not dep:
        raise HTTPException(status_code=404, detail="Deployment not found")
    return dep


@router.post("/orgs/{org_id}/deployments/{dep_id}/rollback",
             response_model=DeploymentResponse, tags=["Deployments"])
async def rollback_deployment(
    org_id: str,
    dep_id: str,
    data: RollbackRequest,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """One-click rollback to the state before this deployment."""
    try:
        rollback = await orchestrator.rollback(dep_id, db, reason=data.reason or "Manual rollback")
        return rollback
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/orgs/{org_id}/projects/{project_id}/promote",
             response_model=PromoteResponse, tags=["Deployments"])
async def promote_deployment(
    org_id: str,
    project_id: str,
    data: PromoteRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Promote an image from one environment tier to the next (e.g. staging → production)."""
    try:
        dep = await orchestrator.promote(
            from_env_id=data.from_environment_id,
            to_env_id=data.to_environment_id,
            image_tag=data.image_tag,
            db=db,
            triggered_by=current_user["sub"],
            run_tests=data.run_tests_first,
        )
        from_env = await db.get(
            DeployEnvironment,
            data.from_environment_id
        )
        to_env = await db.get(
            DeployEnvironment,
            data.to_environment_id
        )
        return {
            "deployment_id": dep.id,
            "from_tier": from_env.tier if from_env else "unknown",
            "to_tier": to_env.tier if to_env else "unknown",
            "image_tag": dep.image_tag,
            "status": dep.status,
            "message": f"Promoting {dep.image_tag} to {to_env.tier if to_env else 'unknown'}",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/orgs/{org_id}/deploy-stats", response_model=DeployStats, tags=["Dashboard"])
async def get_deploy_stats(
    org_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = DeployService(db)
    return await svc.get_stats(org_id)


# ── Live deploy log WebSocket ─────────────────────────────────

@router.websocket("/ws/deployments/{dep_id}")
async def deployment_websocket(websocket: WebSocket, dep_id: str):
    """Stream real-time deployment log events."""
    await websocket.accept()
    logger.info(f"WS connected for deployment {dep_id}")

    from app.core.config import settings
    import redis.asyncio as aioredis

    r = aioredis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
    pubsub = r.pubsub()
    await pubsub.subscribe(f"deploy:{dep_id}:events")

    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                await websocket.send_text(message["data"])
                try:
                    parsed = json.loads(message["data"])
                    if parsed.get("event") in ("complete", "error"):
                        break
                except Exception:
                    pass
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe(f"deploy:{dep_id}:events")
        await pubsub.close()
        await r.close()
