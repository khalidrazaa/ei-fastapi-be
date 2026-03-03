from fastapi import APIRouter
from app.api.admin import admin_routes
from app.api.auth import auth_routes
from app.api.trend_keyword import keyword_routes
from app.api.niche import niche_routes

router = APIRouter()

router.include_router(admin_routes.router, prefix="/admin", tags=["admin"])
router.include_router(auth_routes.router, prefix="/auth", tags=["auth"])
router.include_router(
    keyword_routes.router, prefix="/admin/trends", tags=["trend-keyword"]
)

router.include_router(niche_routes.router, prefix="/admin/niches", tags=["niches"])