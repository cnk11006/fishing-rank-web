from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from app.dependencies import (
    require_authenticated_session,
)
from app.services.keyword_service import (
    KeywordAnalysisError,
    analyze_keywords,
    create_keyword_analysis_workbook,
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
        50,
        100,
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



class KeywordExportRow(BaseModel):
    keyword: str
    pc_volume: int = 0
    pc_volume_raw: str = "0"
    mobile_volume: int = 0
    mobile_volume_raw: str = "0"
    total_volume: int = 0
    competition: str = ""
    average_pc_clicks: float = 0
    average_mobile_clicks: float = 0
    product_count: int = 0
    representative_category: str = ""
    category_sample_count: int = 0


class KeywordExportRequest(BaseModel):
    keyword: str = Field(
        min_length=1,
        max_length=100,
    )
    rows: list[KeywordExportRow] = Field(
        min_length=1,
        max_length=100,
    )


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



@router.post("/export")
def export_keyword_analysis(
    request: KeywordExportRequest,
):
    workbook_bytes = (
        create_keyword_analysis_workbook(
            [
                row.model_dump()
                for row in request.rows
            ]
        )
    )

    return StreamingResponse(
        iter([workbook_bytes]),
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": (
                'attachment; filename="keyword-analysis.xlsx"'
            ),
        },
    )
