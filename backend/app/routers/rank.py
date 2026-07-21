from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.dependencies import (
    require_authenticated_session,
)
from app.services.rank_service import (
    NaverShoppingError,
    search_our_store_ranks,
)


router = APIRouter(
    prefix="/api/rank",
    tags=["rank"],
    dependencies=[
        Depends(require_authenticated_session)
    ],
)


class RankSearchRequest(BaseModel):
    keyword: str = Field(
        min_length=1,
        max_length=100,
    )
    limit: Literal[100, 200, 300, 400] = 400

    @field_validator("keyword")
    @classmethod
    def normalize_keyword(cls, value: str) -> str:
        keyword = value.strip()

        if not keyword:
            raise ValueError(
                "검색 키워드를 입력해 주세요."
            )

        return keyword


@router.post("/search")
def search_rank(
    request: RankSearchRequest,
):
    try:
        return search_our_store_ranks(
            keyword=request.keyword,
            limit=request.limit,
        )
    except NaverShoppingError as error:
        raise HTTPException(
            status_code=502,
            detail=str(error),
        ) from error
