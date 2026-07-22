from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.dependencies import require_authenticated_session
from app.services.data_management_service import (
    DataManagementError,
    DataManagementQuotaError,
    clear_application_caches,
    get_data_overview,
    migrate_legacy_rank_sheets,
)


router = APIRouter(
    prefix="/api/data-management",
    tags=["data-management"],
    dependencies=[
        Depends(require_authenticated_session)
    ],
)


class MigrationRequest(BaseModel):
    backup_confirmed: bool = False


@router.get("/overview")
def data_overview():
    try:
        return get_data_overview()
    except DataManagementQuotaError as error:
        raise HTTPException(
            status_code=429,
            detail={
                "message": str(error),
                "retry_after": error.retry_after,
            },
            headers={
                "Retry-After": str(error.retry_after),
            },
        ) from error
    except DataManagementError as error:
        raise HTTPException(
            status_code=500,
            detail=str(error),
        ) from error


@router.post("/migrate")
def migrate_rank_sheets(
    request: MigrationRequest,
):
    if not request.backup_confirmed:
        raise HTTPException(
            status_code=400,
            detail=(
                "Google Sheets 백업 확인이 필요합니다."
            ),
        )

    try:
        return migrate_legacy_rank_sheets()
    except DataManagementError as error:
        raise HTTPException(
            status_code=500,
            detail=str(error),
        ) from error


@router.post("/clear-cache")
def clear_cache():
    return clear_application_caches()
