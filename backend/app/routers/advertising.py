from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.dependencies import (
    require_authenticated_session,
)
from app.services.advertising_service import (
    AdvertisingApiError,
    get_advertising_overview,
)
from app.services.advertising_diagnosis_service import (
    run_advertising_diagnosis,
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


class AdvertisingDiagnosisTarget(BaseModel):
    campaign_id: str = Field(min_length=1)
    adgroup_ids: list[str] = Field(default_factory=list)


class AdvertisingDiagnosisRequest(BaseModel):
    mode: str = "selected"
    targets: list[AdvertisingDiagnosisTarget] = Field(
        default_factory=list
    )
    days: int = 7
    exclude_off_campaigns: bool = True

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, value: str) -> str:
        if value not in {"selected", "all"}:
            raise ValueError(
                "진단 모드는 selected 또는 all이어야 합니다."
            )
        return value

    @field_validator("days")
    @classmethod
    def validate_days(cls, value: int) -> int:
        if value not in {7, 14, 30}:
            raise ValueError(
                "진단 기간은 7일, 14일, 30일만 가능합니다."
            )
        return value


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



@router.post("/diagnose")
def advertising_diagnosis(
    request: AdvertisingDiagnosisRequest,
):
    if request.mode == "selected" and not request.targets:
        raise HTTPException(
            status_code=400,
            detail="진단할 캠페인을 한 개 이상 선택해 주세요.",
        )

    try:
        return run_advertising_diagnosis(
            mode=request.mode,
            targets=[
                target.model_dump()
                for target in request.targets
            ],
            days=request.days,
            exclude_off_campaigns=(
                request.exclude_off_campaigns
            ),
        )
    except AdvertisingApiError as error:
        raise HTTPException(
            status_code=502,
            detail=str(error),
        ) from error
    except RuntimeError as error:
        raise HTTPException(
            status_code=500,
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
