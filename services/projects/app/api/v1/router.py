from fastapi import APIRouter
from app.api.v1.endpoints.projects import router as projects_router
from app.api.v1.endpoints.internal import router as internal_router

api_router = APIRouter()
api_router.include_router(projects_router)
api_router.include_router(internal_router)
