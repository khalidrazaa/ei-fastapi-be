from fastapi import APIRouter
from app.api.article import article_routes
from app.api.admin import admin_routes
from app.api.auth import auth_routes
from app.api.trend_keyword import keyword_routes
from app.api.niche import niche_routes
from app.api.youtube import youtube_routes

router = APIRouter()

router.include_router(admin_routes.router, prefix="/admin", tags=["admin"])
router.include_router(article_routes.router, prefix="/admin/articles", tags=["articles"])
router.include_router(auth_routes.router, prefix="/auth", tags=["auth"])
router.include_router(
    keyword_routes.router, prefix="/admin/trends", tags=["trend-keyword"]
)

router.include_router(niche_routes.router, prefix="/admin/niches", tags=["niches"])

router.include_router(youtube_routes.router, prefix="/admin/youtube-scan", tags=["youtube-intelligence"]
)
