from __future__ import annotations

import math
import re
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
    "스마트스토어 상품번호",
]
STATUS_COLUMN_CANDIDATES = [
    "주문상태",
    "주문 상태",
    "배송상태",
    "배송 상태",
    "클레임상태",
    "클레임 상태",
]
QUANTITY_COLUMN_CANDIDATES = [
    "수량",
    "구매수량",
    "주문수량",
    "상품수량",
]
AMOUNT_COLUMN_CANDIDATES = [
    "결제금액",
    "상품주문금액",
    "주문금액",
    "상품금액",
    "총 결제금액",
]

EXCLUDED_STATUS_WORDS = {
    "취소완료",
    "취소요청",
    "반품완료",
    "반품요청",
    "교환완료",
    "환불완료",
}


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

    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]

    return text


def parse_number(value: Any) -> int:
    text = re.sub(
        r"[^0-9.\-]",
        "",
        clean_cell(value),
    )

    if not text:
        return 0

    try:
        return max(0, int(float(text)))
    except (TypeError, ValueError):
        return 0


def normalize_text(value: Any) -> str:
    return re.sub(
        r"[^0-9a-z가-힣]",
        "",
        clean_cell(value).casefold(),
    )


def is_excluded_status(value: Any) -> bool:
    normalized = normalize_text(value)

    return any(
        normalize_text(word) in normalized
        for word in EXCLUDED_STATUS_WORDS
    )


def read_order_content(
    file_name: str,
    content: bytes,
) -> pd.DataFrame:
    suffix = Path(file_name).suffix.casefold()

    if suffix not in {".xlsx", ".xls", ".csv"}:
        raise CrossPurchaseError(
            "xlsx, xls 또는 csv 파일만 업로드할 수 있습니다."
        )

    try:
        if suffix == ".csv":
            frame = None
            last_error: Exception | None = None

            for encoding in (
                "utf-8-sig",
                "cp949",
                "euc-kr",
            ):
                try:
                    frame = pd.read_csv(
                        BytesIO(content),
                        dtype=str,
                        encoding=encoding,
                        keep_default_na=False,
                    )
                    break
                except UnicodeDecodeError as error:
                    last_error = error

            if frame is None:
                raise CrossPurchaseError(
                    "CSV 문자 인코딩을 확인할 수 없습니다."
                ) from last_error
        else:
            frame = pd.read_excel(
                BytesIO(content),
                dtype=str,
                engine=(
                    "openpyxl"
                    if suffix == ".xlsx"
                    else "xlrd"
                ),
            )

    except CrossPurchaseError:
        raise
    except Exception as error:
        raise CrossPurchaseError(
            f"주문 파일을 읽지 못했습니다: {error}"
        ) from error

    if frame is None or frame.empty:
        raise CrossPurchaseError(
            "파일에 주문 데이터가 없습니다."
        )

    frame.columns = [
        str(column).strip()
        for column in frame.columns
    ]

    return frame.fillna("")


def normalize_order_frame(
    frame: pd.DataFrame,
) -> tuple[list[dict[str, Any]], list[str], int]:
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
    status_column = find_column(
        columns,
        STATUS_COLUMN_CANDIDATES,
    )
    quantity_column = find_column(
        columns,
        QUANTITY_COLUMN_CANDIDATES,
    )
    amount_column = find_column(
        columns,
        AMOUNT_COLUMN_CANDIDATES,
    )

    if not order_column or not name_column:
        raise CrossPurchaseError(
            "주문번호와 상품명 열을 찾지 못했습니다. "
            f"현재 열: {', '.join(columns)}"
        )

    rows: list[dict[str, Any]] = []
    excluded_status_count = 0

    for record in frame.to_dict(orient="records"):
        order_number = clean_cell(
            record.get(order_column)
        )
        product_name = clean_cell(
            record.get(name_column)
        )
        product_id = (
            clean_cell(record.get(product_id_column))
            if product_id_column
            else ""
        )
        status = (
            clean_cell(record.get(status_column))
            if status_column
            else ""
        )

        if not order_number or not product_name:
            continue

        if status and is_excluded_status(status):
            excluded_status_count += 1
            continue

        quantity = (
            parse_number(record.get(quantity_column))
            if quantity_column
            else 1
        )
        amount = (
            parse_number(record.get(amount_column))
            if amount_column
            else 0
        )

        rows.append({
            "order_number": order_number,
            "product_name": product_name,
            "product_id": product_id,
            "status": status,
            "quantity": max(quantity, 1),
            "amount": amount,
        })

    return rows, columns, excluded_status_count


def product_key(row: dict[str, Any]) -> str:
    product_id = clean_cell(row.get("product_id"))

    if product_id:
        return f"id:{product_id}"

    return (
        "name:"
        + normalize_text(row.get("product_name"))
    )


def is_target_product(
    row: dict[str, Any],
    query: str,
) -> bool:
    normalized_query = normalize_text(query)
    product_id = normalize_text(row.get("product_id"))
    product_name = normalize_text(row.get("product_name"))

    if not normalized_query:
        return False

    return (
        normalized_query == product_id
        or normalized_query in product_name
    )


def recommendation_grade(
    together_orders: int,
    lift: float,
    confidence: float,
) -> str:
    if (
        together_orders >= 5
        and lift >= 2.0
        and confidence >= 10
    ):
        return "매우 높음"

    if (
        together_orders >= 3
        and lift >= 1.3
    ):
        return "높음"

    if lift >= 1.0:
        return "보통"

    return "낮음"


def recommendation_score(
    together_orders: int,
    confidence: float,
    lift: float,
) -> int:
    order_score = min(
        100.0,
        math.log1p(together_orders)
        / math.log(21)
        * 100,
    )
    confidence_score = min(
        100.0,
        confidence * 2,
    )
    lift_score = min(
        100.0,
        lift / 3 * 100,
    )

    return round(
        order_score * 0.35
        + confidence_score * 0.30
        + lift_score * 0.35
    )


def analyze_cross_purchase(
    files: list[tuple[str, bytes]],
    target_query: str,
    top_n: int = 50,
    min_orders: int = 2,
    ours_ids: set[str] | None = None,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    query = clean_cell(target_query)

    if not query:
        raise CrossPurchaseError(
            "기준 상품명 또는 상품번호를 입력해 주세요."
        )

    if not files:
        raise CrossPurchaseError(
            "주문 파일을 한 개 이상 업로드해 주세요."
        )

    if len(files) > MAX_FILE_COUNT:
        raise CrossPurchaseError(
            f"주문 파일은 최대 {MAX_FILE_COUNT}개까지 가능합니다."
        )

    if top_n < 1 or top_n > 200:
        raise CrossPurchaseError(
            "표시 결과 수는 1~200 사이여야 합니다."
        )

    if min_orders < 1:
        raise CrossPurchaseError(
            "최소 동시구매 주문 수는 1 이상이어야 합니다."
        )

    total_size = sum(
        len(content)
        for _, content in files
    )

    if total_size > MAX_TOTAL_SIZE:
        raise CrossPurchaseError(
            "전체 파일 용량은 50MB 이하여야 합니다."
        )

    all_rows: list[dict[str, Any]] = []
    seen_rows: set[tuple[Any, ...]] = set()
    file_errors: list[dict[str, str]] = []
    successful_files = 0
    duplicate_row_count = 0
    excluded_status_count = 0

    for file_name, content in files:
        try:
            if len(content) > MAX_FILE_SIZE:
                raise CrossPurchaseError(
                    "파일 하나의 용량은 15MB 이하여야 합니다."
                )

            frame = read_order_content(
                file_name,
                content,
            )
            rows, _, excluded_count = (
                normalize_order_frame(frame)
            )
            excluded_status_count += excluded_count

            for row in rows:
                identity = (
                    row["order_number"],
                    product_key(row),
                    row["quantity"],
                    row["amount"],
                )

                if identity in seen_rows:
                    duplicate_row_count += 1
                    continue

                seen_rows.add(identity)
                all_rows.append(row)

            successful_files += 1

        except Exception as error:
            file_errors.append({
                "file_name": file_name,
                "message": str(error),
            })

    if successful_files == 0:
        raise CrossPurchaseError(
            "정상적으로 읽은 주문 파일이 없습니다."
        )

    orders: dict[str, list[dict[str, Any]]] = (
        defaultdict(list)
    )

    for row in all_rows:
        orders[row["order_number"]].append(row)

    target_order_numbers = {
        order_number
        for order_number, rows in orders.items()
        if any(
            is_target_product(row, query)
            for row in rows
        )
    }

    if not target_order_numbers:
        raise CrossPurchaseError(
            f"'{query}'이 포함된 주문을 찾지 못했습니다."
        )

    total_order_count = len(orders)
    total_target_orders = len(
        target_order_numbers
    )

    product_meta: dict[str, dict[str, str]] = {}
    overall_product_orders: dict[str, set[str]] = (
        defaultdict(set)
    )

    for order_number, rows in orders.items():
        keys_in_order: set[str] = set()

        for row in rows:
            key = product_key(row)

            if not key or key == "name:":
                continue

            product_meta.setdefault(key, {
                "product_id": clean_cell(
                    row.get("product_id")
                ),
                "product_name": clean_cell(
                    row.get("product_name")
                ),
            })
            keys_in_order.add(key)

        for key in keys_in_order:
            overall_product_orders[key].add(
                order_number
            )

    associated_orders: dict[str, set[str]] = (
        defaultdict(set)
    )
    associated_quantity: dict[str, int] = (
        defaultdict(int)
    )
    associated_revenue: dict[str, int] = (
        defaultdict(int)
    )

    for order_number in target_order_numbers:
        rows = orders[order_number]
        counted_keys: set[str] = set()

        for row in rows:
            if is_target_product(row, query):
                continue

            key = product_key(row)

            if not key or key == "name:":
                continue

            associated_quantity[key] += int(
                row.get("quantity") or 1
            )
            associated_revenue[key] += int(
                row.get("amount") or 0
            )

            if key not in counted_keys:
                associated_orders[key].add(
                    order_number
                )
                counted_keys.add(key)

    normalized_ours_ids = {
        clean_cell(value)
        for value in (ours_ids or set())
        if clean_cell(value)
    }

    results: list[dict[str, Any]] = []

    for key, order_numbers in associated_orders.items():
        together_orders = len(order_numbers)

        if together_orders < min_orders:
            continue

        meta = product_meta.get(key, {})
        product_id = meta.get("product_id", "")
        product_name = meta.get(
            "product_name",
            "",
        )
        overall_orders = len(
            overall_product_orders.get(key, set())
        )

        confidence = (
            together_orders
            / total_target_orders
            * 100
        )
        support = (
            overall_orders
            / total_order_count
            * 100
            if total_order_count
            else 0
        )
        lift = (
            (confidence / 100)
            / (support / 100)
            if support > 0
            else 0
        )

        if product_id and normalized_ours_ids:
            is_ours = (
                product_id in normalized_ours_ids
            )
        else:
            is_ours = (
                TARGET_STORE.casefold()
                in product_name.casefold()
            )

        grade = recommendation_grade(
            together_orders,
            lift,
            confidence,
        )
        score = recommendation_score(
            together_orders,
            confidence,
            lift,
        )

        warnings: list[str] = []

        if together_orders < 5:
            warnings.append(
                "표본이 적어 추가 주문 데이터 확인이 필요합니다."
            )

        if lift < 1:
            warnings.append(
                "전체적으로 인기 있는 상품일 수 있으나 "
                "기준 상품과의 특별한 연관성은 낮습니다."
            )

        results.append({
            # 기존 화면 호환 필드
            "product_id": product_id,
            "product_name": product_name,
            "together_order_count": together_orders,
            "cross_purchase_rate": round(
                confidence,
                1,
            ),
            "is_ours": is_ours,

            # 리뉴얼 필드
            "support": round(support, 2),
            "confidence": round(confidence, 2),
            "lift": round(lift, 2),
            "overall_order_count": overall_orders,
            "together_quantity": (
                associated_quantity[key]
            ),
            "together_revenue": (
                associated_revenue[key]
            ),
            "recommendation_score": score,
            "recommendation_grade": grade,
            "warnings": warnings,
        })

    results.sort(
        key=lambda item: (
            -item["recommendation_score"],
            -item["together_order_count"],
            -item["lift"],
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
            "total_order_count": total_order_count,
            "target_order_count": total_target_orders,
            "result_count": len(results),
            "top_n": top_n,
            "min_orders": min_orders,
            "duplicate_row_count": (
                duplicate_row_count
            ),
            "excluded_status_count": (
                excluded_status_count
            ),
        },
        "results": results,
        "file_errors": file_errors,
        "analysis_guide": {
            "support": (
                "전체 주문 중 해당 연관 상품이 포함된 비율"
            ),
            "confidence": (
                "기준 상품 주문 중 함께 구매된 비율"
            ),
            "lift": (
                "1보다 크면 일반 구매율보다 함께 구매될 "
                "가능성이 높은 상품"
            ),
        },
        "elapsed_seconds": round(
            time.perf_counter() - started_at,
            3,
        ),
    }
