from fastapi import APIRouter

from app.api.admin import admin_routes
from app.api.article import article_routes, public_article_routes
from app.api.auth import auth_routes
from app.api.niche import niche_routes
from app.api.settings import settings_routes
from app.api.trend_keyword import keyword_routes
from app.api.videos import video_routes
from app.api.youtube import youtube_routes

router = APIRouter()

router.include_router(auth_routes.router, prefix="/auth", tags=["auth"])
router.include_router(admin_routes.router, prefix="/admin", tags=["admin"])
router.include_router(
    settings_routes.router, prefix="/admin/settings", tags=["settings"]
)

# google trend scraper
router.include_router(
    keyword_routes.router, prefix="/admin/google-trends", tags=["trend-keyword"]
)

# niches & keywords management
router.include_router(niche_routes.router, prefix="/admin/niches", tags=["niches"])

# YT videos scanner for popular and niche
router.include_router(
    youtube_routes.router, prefix="/admin/yt-scan", tags=["yt_scanner_google_api"]
)

# Videos fetching & storage
router.include_router(
    video_routes.router, prefix="/admin/videos", tags=["videos_query_api"]
)

# articles management
router.include_router(
    article_routes.router, prefix="/admin/articles", tags=["articles"]
)
router.include_router(
    public_article_routes.router, prefix="/public/articles", tags=["public-articles"]
)
