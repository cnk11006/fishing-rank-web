from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.dependencies import (
    require_authenticated_session,
)
from app.services.keyword_service import (
    KeywordAnalysisError,
    analyze_keywords,
)


router = APIRouter(
    prefix="/api/keywords",
    tags=["keywords"],
    dependencies=[
        Depends(require_authenticated_session)
    ],
)


class KeywordAnalysisRequest(BaseModel):
    keyword: str = Field(
        min_length=1,
        max_length=100,
    )
    related_limit: Literal[
        10,
        20,
        30,
    ] = 20

    @field_validator("keyword")
    @classmethod
    def normalize_keyword(cls, value: str) -> str:
        keyword = value.strip()

        if not keyword:
            raise ValueError(
                "분석할 키워드를 입력해 주세요."
            )

        return keyword


@router.post("/analyze")
def analyze_keyword(
    request: KeywordAnalysisRequest,
):
    try:
        return analyze_keywords(
            keyword=request.keyword,
            related_limit=request.related_limit,
        )
    except KeywordAnalysisError as error:
        raise HTTPException(
            status_code=502,
            detail=str(error),
        ) from error
