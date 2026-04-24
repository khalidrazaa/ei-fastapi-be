from .admin_user import AdminUser
from .email_otp import EmailOTP
from .token import Token
from .article import Article
from .niche import Niche, NicheKeyword
from .trend_video import TrendVideo
from .trends import TrendItem, TrendStatus
from .discovered_trend import DiscoveredTrend
from .idea_generated import TrendIdea
from .popular_scan_setting import PopularScanSetting

__all__ = [
    "AdminUser",
    "EmailOTP",
    "Token",
    "Article",
    "Niche",
    "NicheKeyword",
    "TrendVideo",
    "TrendItem",
    "TrendStatus",
    "DiscoveredTrend",
    "TrendIdea",
    "PopularScanSetting",
]  #  include all models
