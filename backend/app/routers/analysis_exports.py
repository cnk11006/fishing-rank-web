from __future__ import annotations

from typing import Any

from fastapi import (
    APIRouter,
    Body,
    Depends,
    HTTPException,
)
from fastapi.responses import StreamingResponse

from app.dependencies import (
    require_authenticated_session,
)
from app.services.analysis_export_service import (
    create_candidate_workbook,
    create_cross_purchase_workbook,
)


router = APIRouter(
    tags=["analysis-exports"],
    dependencies=[
        Depends(require_authenticated_session)
    ],
)

EXCEL_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument."
    "spreadsheetml.sheet"
)


def validate_payload(
    payload: dict[str, Any],
    max_results: int,
) -> None:
    results = payload.get("results")

    if not isinstance(results, list):
        raise HTTPException(
            status_code=400,
            detail="내보낼 분석 결과가 올바르지 않습니다.",
        )

    if len(results) > max_results:
        raise HTTPException(
            status_code=400,
            detail=(
                f"한 번에 최대 {max_results}건까지 "
                "내보낼 수 있습니다."
            ),
        )


@router.post("/api/cross-purchase/export")
def export_cross_purchase(
    payload: dict[str, Any] = Body(...),
):
    validate_payload(payload, 500)

    workbook = create_cross_purchase_workbook(
        payload
    )

    return StreamingResponse(
        iter([workbook]),
        media_type=EXCEL_MEDIA_TYPE,
        headers={
            "Content-Disposition": (
                'attachment; filename="cross-purchase.xlsx"'
            ),
        },
    )


@router.post("/api/candidates/export")
def export_candidates(
    payload: dict[str, Any] = Body(...),
):
    validate_payload(payload, 500)

    workbook = create_candidate_workbook(
        payload
    )

    return StreamingResponse(
        iter([workbook]),
        media_type=EXCEL_MEDIA_TYPE,
        headers={
            "Content-Disposition": (
                'attachment; filename="candidates.xlsx"'
            ),
        },
    )
