from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.dependencies import (
    require_authenticated_session,
)
from app.services.advertising_service import (
    AdvertisingApiError,
    get_advertising_overview,
)

from app.services.season_service import (
    SeasonAnalysisError,
    analyze_season,
)


router = APIRouter(
    prefix="/api/advertising",
    tags=["advertising"],
    dependencies=[
        Depends(require_authenticated_session)
    ],
)


class SeasonAnalysisRequest(BaseModel):
    keyword: str = Field(min_length=1, max_length=100)
    months: int = 24

    @field_validator("keyword")
    @classmethod
    def normalize_input_keyword(cls, value: str) -> str:
        normalized = value.strip()

        if not normalized:
            raise ValueError("키워드를 입력해 주세요.")

        return normalized

    @field_validator("months")
    @classmethod
    def validate_months(cls, value: int) -> int:
        if value not in {12, 24, 36}:
            raise ValueError(
                "분석 기간은 12개월, 24개월, 36개월만 가능합니다."
            )

        return value

@router.get("/overview")
def advertising_overview():
    try:
        return get_advertising_overview()
    except AdvertisingApiError as error:
        raise HTTPException(
            status_code=502,
            detail=str(error),
        ) from error



@router.post("/season")
def advertising_season_analysis(
    request: SeasonAnalysisRequest,
):
    try:
        return analyze_season(
            keyword=request.keyword,
            months=request.months,
        )
    except SeasonAnalysisError as error:
        raise HTTPException(
            status_code=502,
            detail=str(error),
        ) from error
