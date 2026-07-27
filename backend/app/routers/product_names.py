from typing import Literal

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from pydantic import BaseModel, Field

from app.dependencies import (
    require_authenticated_session,
)
from app.services.product_name_service import (
    ProductNameRecommendationError,
    recommend_product_names,
)


router = APIRouter(
    prefix="/api/product-names",
    tags=["product-names"],
    dependencies=[
        Depends(require_authenticated_session)
    ],
)


class ProductNameRequest(BaseModel):
    mode: Literal["new", "existing"]
    main_keyword: str = Field(
        default="",
        max_length=100,
    )
    product_type: str = Field(
        default="",
        max_length=100,
    )
    brand: str = Field(
        default="피싱템",
        max_length=100,
    )
    model_name: str = Field(
        default="",
        max_length=100,
    )
    features: list[str] = Field(
        default_factory=list,
        max_length=20,
    )
    required_words: list[str] = Field(
        default_factory=list,
        max_length=20,
    )
    excluded_words: list[str] = Field(
        default_factory=list,
        max_length=20,
    )
    current_title: str = Field(
        default="",
        max_length=300,
    )
    product_url: str = Field(
        default="",
        max_length=1000,
    )


@router.post("/recommend")
def recommend_product_name(
    request: ProductNameRequest,
):
    try:
        return recommend_product_names(
            **request.model_dump()
        )
    except ProductNameRecommendationError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error
