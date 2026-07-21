from __future__ import annotations

import time
from collections import defaultdict
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd


MAX_FILE_COUNT = 10
MAX_FILE_SIZE = 15 * 1024 * 1024
MAX_TOTAL_SIZE = 50 * 1024 * 1024
TARGET_STORE = "피싱템"

ORDER_COLUMN_CANDIDATES = [
    "주문번호",
    "주문 번호",
    "구매번호",
]
NAME_COLUMN_CANDIDATES = [
    "상품명",
    "상품 명",
    "제품명",
]
PRODUCT_ID_COLUMN_CANDIDATES = [
    "상품번호",
    "상품 번호",
    "상품ID",
]


class CrossPurchaseError(Exception):
    pass


def find_column(
    columns: list[str],
    candidates: list[str],
) -> str | None:
    normalized_columns = [
        str(column).strip()
        for column in columns
    ]

    for candidate in candidates:
        for column in normalized_columns:
            if column == candidate:
                return column

    for candidate in candidates:
        for column in normalized_columns:
            if candidate in column:
                return column

    return None


def clean_cell(value: Any) -> str:
    if value is None:
        return ""

    text = str(value).strip()

    if text.casefold() in {"nan", "none", "nat"}:
        return ""

    if text.endswith(".0"):
        integer_text = text[:-2]

        if integer_text.isdigit():
            return integer_text

    return text


def read_excel_content(
    file_name: str,
    content: bytes,
) -> pd.DataFrame:
    suffix = Path(file_name).suffix.casefold()

    if suffix not in {".xlsx", ".xls"}:
        raise CrossPurchaseError(
            "xlsx 또는 xls 파일만 업로드할 수 있습니다."
        )

    engine = (
        "openpyxl"
        if suffix == ".xlsx"
        else "xlrd"
    )

    try:
        frame = pd.read_excel(
            BytesIO(content),
            dtype=str,
            engine=engine,
        )
    except Exception as error:
        raise CrossPurchaseError(
            f"엑셀 파일을 읽지 못했습니다: {error}"
        ) from error

    if frame is None or frame.empty:
        raise CrossPurchaseError(
            "엑셀 파일에 주문 데이터가 없습니다."
        )

    frame.columns = [
        str(column).strip()
        for column in frame.columns
    ]

    return frame.fillna("")


def normalize_order_frame(
    frame: pd.DataFrame,
) -> tuple[list[dict[str, str]], list[str]]:
    columns = list(frame.columns)

    order_column = find_column(
        columns,
        ORDER_COLUMN_CANDIDATES,
    )
    name_column = find_column(
        columns,
        NAME_COLUMN_CANDIDATES,
    )
    product_id_column = find_column(
        columns,
        PRODUCT_ID_COLUMN_CANDIDATES,
    )

    if not order_column or not name_column:
        raise CrossPurchaseError(
            "주문번호와 상품명 열을 찾지 못했습니다."
        )

    rows: list[dict[str, str]] = []

    for record in frame.to_dict(orient="records"):
        order_number = clean_cell(
            record.get(order_column)
        )
        product_name = clean_cell(
            record.get(name_column)
        )
        product_id = (
            clean_cell(
                record.get(product_id_column)
            )
            if product_id_column
            else ""
        )

        if not order_number or not product_name:
            continue

        rows.append({
            "order_number": order_number,
            "product_name": product_name,
            "product_id": product_id,
        })

    return rows, columns


def is_target_product(
    row: dict[str, str],
    query: str,
) -> bool:
    normalized_query = query.casefold()

    return (
        normalized_query
        in row["product_name"].casefold()
        or (
            bool(row["product_id"])
            and row["product_id"].casefold()
            == normalized_query
        )
    )


def analyze_cross_purchase(
    files: list[tuple[str, bytes]],
    target_query: str,
    top_n: int = 50,
    min_orders: int = 2,
    ours_ids: set[str] | None = None,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    query = str(target_query or "").strip()

    if not query:
        raise CrossPurchaseError(
            "기준 상품명 또는 검색어를 입력해 주세요."
        )

    if not files:
        raise CrossPurchaseError(
            "주문내역 Excel 파일을 업로드해 주세요."
        )

    if len(files) > MAX_FILE_COUNT:
        raise CrossPurchaseError(
            f"파일은 최대 {MAX_FILE_COUNT}개까지 "
            "업로드할 수 있습니다."
        )

    if top_n < 10 or top_n > 200:
        raise CrossPurchaseError(
            "연관상품 수는 10~200 사이여야 합니다."
        )

    if min_orders < 1 or min_orders > 100:
        raise CrossPurchaseError(
            "최소 주문 수는 1~100 사이여야 합니다."
        )

    total_size = sum(
        len(content)
        for _, content in files
    )

    if total_size > MAX_TOTAL_SIZE:
        raise CrossPurchaseError(
            "전체 파일 크기는 50MB 이하여야 합니다."
        )

    all_rows: list[dict[str, str]] = []
    file_errors: list[dict[str, str]] = []
    successful_files = 0

    for file_name, content in files:
        if len(content) > MAX_FILE_SIZE:
            file_errors.append({
                "file_name": file_name,
                "message": "파일 크기가 15MB를 초과합니다.",
            })
            continue

        try:
            frame = read_excel_content(
                file_name,
                content,
            )
            rows, _ = normalize_order_frame(frame)
            all_rows.extend(rows)
            successful_files += 1
        except CrossPurchaseError as error:
            file_errors.append({
                "file_name": file_name,
                "message": str(error),
            })

    if successful_files == 0:
        message = (
            file_errors[0]["message"]
            if file_errors
            else "분석 가능한 엑셀 파일이 없습니다."
        )
        raise CrossPurchaseError(message)

    target_orders = {
        row["order_number"]
        for row in all_rows
        if is_target_product(row, query)
    }

    if not target_orders:
        return {
            "target_query": query,
            "summary": {
                "uploaded_file_count": len(files),
                "successful_file_count": successful_files,
                "file_error_count": len(file_errors),
                "order_row_count": len(all_rows),
                "target_order_count": 0,
                "result_count": 0,
                "top_n": top_n,
                "min_orders": min_orders,
            },
            "results": [],
            "file_errors": file_errors,
            "elapsed_seconds": round(
                time.perf_counter() - started_at,
                3,
            ),
        }

    unique_products: set[
        tuple[str, str, str]
    ] = set()

    for row in all_rows:
        if row["order_number"] not in target_orders:
            continue

        if is_target_product(row, query):
            continue

        unique_products.add((
            row["order_number"],
            row["product_id"],
            row["product_name"],
        ))

    grouped_orders: dict[
        tuple[str, str],
        set[str],
    ] = defaultdict(set)

    for order_number, product_id, product_name in unique_products:
        grouped_orders[
            (product_id, product_name)
        ].add(order_number)

    normalized_ours_ids = {
        clean_cell(product_id)
        for product_id in (ours_ids or set())
        if clean_cell(product_id)
    }

    total_target_orders = len(target_orders)
    results: list[dict[str, Any]] = []

    for (
        product_id,
        product_name,
    ), order_numbers in grouped_orders.items():
        together_orders = len(order_numbers)

        if together_orders < min_orders:
            continue

        if product_id and normalized_ours_ids:
            is_ours = (
                product_id in normalized_ours_ids
            )
        else:
            is_ours = (
                TARGET_STORE.casefold()
                in product_name.casefold()
            )

        results.append({
            "product_id": product_id,
            "product_name": product_name,
            "together_order_count": together_orders,
            "cross_purchase_rate": round(
                together_orders
                / total_target_orders
                * 100,
                1,
            ),
            "is_ours": is_ours,
        })

    results.sort(
        key=lambda item: (
            -item["together_order_count"],
            item["product_name"],
        )
    )
    results = results[:top_n]

    return {
        "target_query": query,
        "summary": {
            "uploaded_file_count": len(files),
            "successful_file_count": successful_files,
            "file_error_count": len(file_errors),
            "order_row_count": len(all_rows),
            "target_order_count": total_target_orders,
            "result_count": len(results),
            "top_n": top_n,
            "min_orders": min_orders,
        },
        "results": results,
        "file_errors": file_errors,
        "elapsed_seconds": round(
            time.perf_counter() - started_at,
            3,
        ),
    }
