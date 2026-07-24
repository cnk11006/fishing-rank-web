from typing import Literal

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from pydantic import BaseModel, Field, field_validator

from app.dependencies import (
    require_authenticated_session,
)
from app.services.product_name_service import (
    ProductNameRecommendationError,
    recommend_product_names,
    resolve_existing_product,
)


router = APIRouter(
    prefix="/api/product-names",
    tags=["product-names"],
    dependencies=[
        Depends(require_authenticated_session)
    ],
)


class ProductLinkRequest(BaseModel):
    product_url: str = Field(
        min_length=1,
        max_length=1000,
    )

    @field_validator("product_url")
    @classmethod
    def clean_url(cls, value: str) -> str:
        return value.strip()


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


@router.post("/resolve")
def resolve_product_link(
    request: ProductLinkRequest,
):
    try:
        return resolve_existing_product(
            request.product_url
        )
    except ProductNameRecommendationError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error


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
