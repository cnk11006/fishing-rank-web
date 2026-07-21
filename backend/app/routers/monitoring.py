from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.dependencies import (
    require_authenticated_session,
)
from app.services.monitoring_collect_service import (
    collect_monitoring_ranks,
)
from app.services.monitoring_history_service import (
    RankHistoryError,
    calculate_monitoring_history,
)
from app.services.monitoring_service import (
    DuplicateMonitorError,
    MonitorSheetError,
    add_monitor_item,
    delete_monitor_items,
    read_monitor_items,
)


router = APIRouter(
    prefix="/api/monitoring",
    tags=["monitoring"],
    dependencies=[
        Depends(require_authenticated_session)
    ],
)


class MonitorAddRequest(BaseModel):
    keyword: str = Field(
        min_length=1,
        max_length=100,
    )
    memo: str = Field(
        default="",
        max_length=500,
    )
    product_id: str = Field(
        default="",
        max_length=100,
    )
    product_name: str = Field(
        default="",
        max_length=300,
    )

    @field_validator(
        "keyword",
        "memo",
        "product_id",
        "product_name",
    )
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class MonitorDeleteRequest(BaseModel):
    item_ids: list[str] = Field(
        min_length=1,
        max_length=100,
    )


@router.get("/list")
def list_monitoring():
    try:
        items = read_monitor_items()

        return {
            "count": len(items),
            "items": items,
        }
    except MonitorSheetError as error:
        raise HTTPException(
            status_code=500,
            detail=str(error),
        ) from error


@router.post("/add")
def add_monitoring(
    request: MonitorAddRequest,
):
    try:
        item = add_monitor_item(
            keyword=request.keyword,
            memo=request.memo,
            product_id=request.product_id,
            product_name=request.product_name,
        )

        return {
            "message": "모니터링 항목을 등록했습니다.",
            "item": item,
        }
    except DuplicateMonitorError as error:
        raise HTTPException(
            status_code=409,
            detail=str(error),
        ) from error
    except (ValueError, MonitorSheetError) as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error


@router.post("/delete")
def delete_monitoring(
    request: MonitorDeleteRequest,
):
    try:
        deleted_count = delete_monitor_items(
            request.item_ids
        )

        return {
            "message": (
                f"모니터링 항목 "
                f"{deleted_count}개를 삭제했습니다."
            ),
            "deleted_count": deleted_count,
        }
    except (ValueError, MonitorSheetError) as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

@router.post("/collect")
def collect_monitoring():
    try:
        return collect_monitoring_ranks()
    except MonitorSheetError as error:
        raise HTTPException(
            status_code=500,
            detail=str(error),
        ) from error

@router.get("/history")
def monitoring_history():
    try:
        return calculate_monitoring_history()
    except (MonitorSheetError, RankHistoryError) as error:
        raise HTTPException(
            status_code=500,
            detail=str(error),
        ) from error

