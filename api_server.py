import asyncio
import os
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from logistics_query import (
    SERIAL_BROWSER_TRACKING_PLATFORMS,
    attach_tracking_result_link,
    decide_platform,
    decide_tracking_platform,
    find_order_by_fba,
    get_primary_logistics_no,
    query_17track,
    query_agl,
    query_baosen,
    query_meitong,
    query_pingyi,
    query_tracking_number,
    run_browser_tracking_query_with_queue,
)
from qq_query import query_qq


app = FastAPI(
    title="Logistics Query API",
    version="1.1.0",
    description=(
        "提供跟踪号查询和 FBA 查询的 HTTP API。\n\n"
        "鉴权：当环境变量 `API_AUTH_TOKEN` 已配置时，请在请求头中传 `X-API-Key`。"
    ),
)


class ApiResponse(BaseModel):
    success: bool = Field(..., description="请求是否成功")
    data: dict[str, Any] | None = Field(default=None, description="成功时返回的数据")
    error: str | None = Field(default=None, description="失败时返回的错误信息")


class TrackingQueryRequest(BaseModel):
    tracking_no: str = Field(..., description="要查询的跟踪号")


class FbaQueryRequest(BaseModel):
    fba_code: str = Field(..., description="要查询的 FBA 编号")
    platform: str = Field(default="auto", description="指定平台，默认 auto")
    include_order: bool = Field(default=True, description="是否返回钉钉表匹配记录")
    include_tracking: bool = Field(default=True, description="是否继续查询物流轨迹")


async def validate_api_key(x_api_key: str | None = Header(default=None)) -> None:
    expected_token = os.environ.get("API_AUTH_TOKEN", "").strip()
    if not expected_token:
        return
    if x_api_key != expected_token:
        raise HTTPException(status_code=401, detail="Invalid API key")


def build_api_response(*, success: bool, data: dict[str, Any] | None = None, error: str | None = None) -> dict[str, Any]:
    return {
        "success": success,
        "data": data,
        "error": error,
    }


async def _query_fba_tracking_result(order: dict[str, Any], fba_code: str, explicit_platform: str) -> dict[str, Any] | None:
    platform = decide_platform(order, explicit_platform)
    tracking_no = get_primary_logistics_no(order)

    if platform == "none":
        return None

    if platform in {"meitong", "agl", "baosen", "qq", "17track"} and not tracking_no:
        return {
            "平台": platform,
            "查询值": "",
            "物流轨迹": [],
            "最新轨迹": {},
            "错误": "钉钉表格中缺少物流编号，暂时无法查询物流轨迹",
        }

    if platform == "meitong":
        return await asyncio.to_thread(query_meitong, tracking_no)
    if platform == "agl":
        return await run_browser_tracking_query_with_queue(
            platform="AGL",
            query_value=tracking_no,
            operation=lambda: asyncio.to_thread(query_agl, tracking_no, order, False),
        )
    if platform == "pingyi":
        return await run_browser_tracking_query_with_queue(
            platform="PINGYI",
            query_value=fba_code,
            operation=lambda: query_pingyi(fba_code),
        )
    if platform == "baosen":
        return await run_browser_tracking_query_with_queue(
            platform="BAOSEN",
            query_value=tracking_no,
            operation=lambda: query_baosen(tracking_no),
        )
    if platform == "qq":
        return await asyncio.to_thread(query_qq, order, tracking_no)
    if platform == "17track":
        return await run_browser_tracking_query_with_queue(
            platform="17TRACK",
            query_value=tracking_no,
            operation=lambda: query_17track(tracking_no),
        )
    return None


@app.get("/api/health", response_model=ApiResponse, summary="健康检查")
async def health() -> dict[str, Any]:
    return build_api_response(
        success=True,
        data={"ok": True, "service": "logistics-query-api"},
        error=None,
    )


@app.post(
    "/api/tracking/query",
    response_model=ApiResponse,
    summary="按跟踪号查询",
    dependencies=[Depends(validate_api_key)],
)
async def query_tracking(payload: TrackingQueryRequest) -> dict[str, Any]:
    platform = decide_tracking_platform(payload.tracking_no)
    if platform in SERIAL_BROWSER_TRACKING_PLATFORMS:
        result = await run_browser_tracking_query_with_queue(
            platform=platform.upper(),
            query_value=payload.tracking_no,
            operation=lambda: query_tracking_number(payload.tracking_no),
        )
    else:
        result = await query_tracking_number(payload.tracking_no)

    result = attach_tracking_result_link(result)
    error = str(result.get("错误", "") or "").strip()
    if error:
        return build_api_response(success=False, data=result, error=error)
    return build_api_response(success=True, data=result, error=None)


@app.post(
    "/api/fba/query",
    response_model=ApiResponse,
    summary="按 FBA 编号查询",
    dependencies=[Depends(validate_api_key)],
)
async def query_fba(payload: FbaQueryRequest) -> dict[str, Any]:
    order = find_order_by_fba(payload.fba_code)
    matched_platform = decide_platform(order, payload.platform)

    result: dict[str, Any] = {
        "FBA编号": payload.fba_code,
        "线上表匹配结果": order if payload.include_order else None,
        "命中平台": matched_platform,
        "物流查询结果": None,
    }

    if not order:
        return build_api_response(success=False, data=result, error="未找到对应FBA记录")

    if payload.include_tracking:
        result["物流查询结果"] = await _query_fba_tracking_result(order, payload.fba_code, payload.platform)

    tracking_error = ""
    if isinstance(result.get("物流查询结果"), dict):
        tracking_error = str(result["物流查询结果"].get("错误", "") or "").strip()

    if tracking_error:
        return build_api_response(success=False, data=result, error=tracking_error)
    return build_api_response(success=True, data=result, error=None)
