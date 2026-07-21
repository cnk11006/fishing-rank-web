from __future__ import annotations

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)

from app.dependencies import (
    require_authenticated_session,
)
from app.services.cross_purchase_service import (
    CrossPurchaseError,
    analyze_cross_purchase,
)


router = APIRouter(
    prefix="/api/cross-purchase",
    tags=["cross-purchase"],
    dependencies=[
        Depends(require_authenticated_session)
    ],
)


@router.post("/analyze")
async def cross_purchase_analysis(
    files: list[UploadFile] = File(...),
    target_query: str = Form(...),
    top_n: int = Form(50),
    min_orders: int = Form(2),
):
    uploaded: list[tuple[str, bytes]] = []

    try:
        for file in files:
            content = await file.read()

            uploaded.append((
                file.filename or "orders.xlsx",
                content,
            ))

        return analyze_cross_purchase(
            files=uploaded,
            target_query=target_query,
            top_n=top_n,
            min_orders=min_orders,
        )
    except CrossPurchaseError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error
    finally:
        for file in files:
            await file.close()
