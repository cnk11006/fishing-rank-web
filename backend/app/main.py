from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import router as auth_router
from app.config import get_settings
from app.routers.rank import router as rank_router
from app.routers.monitoring import router as monitoring_router
from app.routers.keywords import router as keywords_router
from app.routers.advertising import router as advertising_router
from app.routers.cross_purchase import router as cross_purchase_router
from app.routers.candidates import router as candidates_router
from app.routers.data_management import router as data_management_router
from app.routers.product_names import router as product_names_router


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description=(
        "피싱템 순위·키워드·광고·상품 분석을 제공하는 "
        "Python 백엔드 API입니다."
    ),
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=[
        "GET",
        "POST",
        "PUT",
        "DELETE",
        "OPTIONS",
    ],
    allow_headers=[
        "Content-Type",
        "Authorization",
    ],
)

app.include_router(auth_router)
app.include_router(rank_router)
app.include_router(monitoring_router)
app.include_router(keywords_router)
app.include_router(advertising_router)
app.include_router(cross_purchase_router)
app.include_router(candidates_router)
app.include_router(data_management_router)
app.include_router(product_names_router)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "status": "running",
        "docs": "/docs",
        "health": "/api/health",
    }


@app.get("/api/health")
def health_check() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.app_environment,
        "authentication_ready": (
            settings.authentication_ready
        ),
        "external_api_settings_ready": (
            settings.required_api_settings_ready
        ),
        "keyword_api_settings_ready": (
            settings.keyword_api_settings_ready
        ),
        "commerce_api_settings_ready": (
            settings.commerce_api_settings_ready
        ),
        "checked_at": datetime.now(
            timezone.utc
        ).isoformat(),
    }
