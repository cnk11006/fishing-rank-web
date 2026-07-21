from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import (
    require_authenticated_session,
)
from app.services.advertising_service import (
    AdvertisingApiError,
    get_advertising_overview,
)


router = APIRouter(
    prefix="/api/advertising",
    tags=["advertising"],
    dependencies=[
        Depends(require_authenticated_session)
    ],
)


@router.get("/overview")
def advertising_overview():
    try:
        return get_advertising_overview()
    except AdvertisingApiError as error:
        raise HTTPException(
            status_code=502,
            detail=str(error),
        ) from error
