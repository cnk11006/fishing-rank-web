from __future__ import annotations

import re

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
from app.services.candidate_service import (
    CandidateAnalysisError,
    analyze_candidates,
)


router = APIRouter(
    prefix="/api/candidates",
    tags=["candidates"],
    dependencies=[
        Depends(require_authenticated_session)
    ],
)


@router.post("/analyze")
async def candidate_analysis(
    master_file: UploadFile = File(...),
    keywords: str = Form(...),
    max_results: int = Form(100),
    result_limit: int = Form(100),
    min_volume: int = Form(10),
    exclude_owned: bool = Form(True),
    exclude_group: bool = Form(False),
    exclude_used: bool = Form(True),
    exclude_rental: bool = Form(True),
    exclude_overseas: bool = Form(True),
):
    content = await master_file.read()

    try:
        keyword_list = [
            keyword.strip()
            for keyword in re.split(
                r"[\n,]+",
                keywords,
            )
            if keyword.strip()
        ]

        return analyze_candidates(
            master_file_name=(
                master_file.filename
                or "product-master.xlsx"
            ),
            master_content=content,
            keywords=keyword_list,
            max_results=max_results,
            result_limit=result_limit,
            min_volume=min_volume,
            exclude_owned=exclude_owned,
            exclude_group=exclude_group,
            exclude_used=exclude_used,
            exclude_rental=exclude_rental,
            exclude_overseas=exclude_overseas,
        )
    except CandidateAnalysisError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error
    finally:
        await master_file.close()
