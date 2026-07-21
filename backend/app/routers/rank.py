from typing import Literal

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
)
from pydantic import BaseModel, Field, field_validator

from app.dependencies import (
    require_authenticated_session,
)
from app.services.google_sheets import (
    save_rank_search_result_safely,
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
    background_tasks: BackgroundTasks,
):
    try:
        result = search_our_store_ranks(
            keyword=request.keyword,
            limit=request.limit,
        )

        save_scheduled = bool(
            result.get("results")
        )

        if save_scheduled:
            background_tasks.add_task(
                save_rank_search_result_safely,
                result,
            )

        return {
            **result,
            "save_scheduled": save_scheduled,
        }

    except NaverShoppingError as error:
        raise HTTPException(
            status_code=502,
            detail=str(error),
        ) from error
