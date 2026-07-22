from typing import Literal
from urllib.parse import urlparse

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from pydantic import (
    BaseModel,
    Field,
    field_validator,
)

from app.dependencies import (
    require_authenticated_session,
)
from app.services.data_management_service import (
    clear_data_overview_cache,
)
from app.services.google_sheets import (
    save_rank_search_result,
)
from app.services.monitoring_service import (
    add_monitor_items_bulk,
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
    include_special_products: bool = False

    @field_validator("keyword")
    @classmethod
    def normalize_keyword(cls, value: str) -> str:
        keyword = value.strip()

        if not keyword:
            raise ValueError(
                "검색 키워드를 입력해 주세요."
            )

        return keyword


class SelectedRankItem(BaseModel):
    rank: int = Field(ge=1, le=1000)
    title: str = Field(
        min_length=1,
        max_length=1000,
    )
    mall_name: str = Field(
        default="",
        max_length=300,
    )
    price: int = Field(default=0, ge=0)
    highest_price: int = Field(default=0, ge=0)
    link: str = Field(default="", max_length=2048)
    image: str = Field(default="", max_length=2048)
    product_type: int = Field(default=0, ge=0)
    product_id: str = Field(
        default="",
        max_length=200,
    )
    brand: str = Field(default="", max_length=300)
    maker: str = Field(default="", max_length=300)
    categories: list[str] = Field(
        default_factory=list,
        max_length=4,
    )
    is_catalog: bool = False
    catalog_badge: str = Field(
        default="",
        max_length=100,
    )

    @field_validator("link", "image")
    @classmethod
    def validate_external_url(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip()

        if not normalized:
            return ""

        try:
            parsed = urlparse(normalized)

            if parsed.scheme in {"http", "https"}:
                return normalized
        except Exception:
            pass

        return ""


class SaveSelectedRankRequest(BaseModel):
    keyword: str = Field(
        min_length=1,
        max_length=100,
    )
    items: list[SelectedRankItem] = Field(
        min_length=1,
        max_length=400,
    )

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
        result = search_our_store_ranks(
            keyword=request.keyword,
            limit=request.limit,
            include_special_products=(
                request.include_special_products
            ),
        )

        return {
            **result,
            "save_scheduled": False,
        }

    except NaverShoppingError as error:
        raise HTTPException(
            status_code=502,
            detail=str(error),
        ) from error


@router.post("/save-selected")
def save_selected_rank_items(
    request: SaveSelectedRankRequest,
):
    unique_items: list[dict] = []
    seen: set[str] = set()

    for selected in request.items:
        item = selected.model_dump()

        identity = (
            item["product_id"]
            or (
                f"{item['rank']}|"
                f"{item['title'].casefold()}"
            )
        )

        if identity in seen:
            continue

        seen.add(identity)
        unique_items.append(item)

    if not unique_items:
        raise HTTPException(
            status_code=400,
            detail="저장할 상품을 선택해 주세요.",
        )

    search_result = {
        "keyword": request.keyword,
        "results": unique_items,
    }

    try:
        saved_count = save_rank_search_result(
            search_result
        )
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=(
                "선택 상품의 순위기록을 "
                f"저장하지 못했습니다: {error}"
            ),
        ) from error

    monitor_input = [
        {
            "keyword": request.keyword,
            "memo": (
                f"등록상품:{item['title']}"
            ),
            "product_id": item["product_id"],
            "product_name": item["title"],
        }
        for item in unique_items
    ]

    monitor_errors: list[str] = []

    try:
        monitor_result = add_monitor_items_bulk(
            monitor_input
        )
    except Exception as error:
        monitor_result = {
            "added_count": 0,
            "duplicate_count": 0,
            "added_items": [],
        }
        monitor_errors.append(str(error))

    clear_data_overview_cache()

    return {
        "message": (
            f"순위기록 {saved_count}건 저장, "
            f"모니터링 "
            f"{monitor_result['added_count']}건 등록 완료"
        ),
        "saved_count": saved_count,
        "selected_count": len(unique_items),
        "monitor_added_count": (
            monitor_result["added_count"]
        ),
        "monitor_duplicate_count": (
            monitor_result["duplicate_count"]
        ),
        "monitor_errors": monitor_errors,
        "saved_items": unique_items,
    }
