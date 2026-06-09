import asyncio
import os
from typing import Any

import requests
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field


DEFAULT_UPSTREAM_BASE = "http://127.0.0.1:18081"
DEFAULT_GATEWAY_TIMEOUT = 180


app = FastAPI(
    title="Logistics Query Gateway",
    version="1.0.0",
    description=(
        "公网 API 网关，仅负责鉴权、转发、超时控制和错误透传。\n\n"
        "鉴权：当环境变量 `GATEWAY_AUTH_TOKEN` 已配置时，请在请求头中传 `X-API-Key`。"
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


def build_api_response(*, success: bool, data: dict[str, Any] | None = None, error: str | None = None) -> dict[str, Any]:
    return {
        "success": success,
        "data": data,
        "error": error,
    }


async def validate_gateway_key(x_api_key: str | None = Header(default=None)) -> None:
    expected_token = os.environ.get("GATEWAY_AUTH_TOKEN", "").strip()
    if not expected_token:
        return
    if x_api_key != expected_token:
        raise HTTPException(status_code=401, detail="Invalid API key")


def _get_upstream_base_url() -> str:
    return os.environ.get("UPSTREAM_API_BASE_URL", DEFAULT_UPSTREAM_BASE).rstrip("/")


def _get_upstream_auth_token() -> str:
    return os.environ.get("UPSTREAM_API_TOKEN", "").strip()


def _get_gateway_timeout() -> int:
    raw = os.environ.get("GATEWAY_REQUEST_TIMEOUT", str(DEFAULT_GATEWAY_TIMEOUT)).strip()
    try:
        return max(5, int(raw))
    except ValueError:
        return DEFAULT_GATEWAY_TIMEOUT


def _build_upstream_headers() -> dict[str, str]:
    token = _get_upstream_auth_token()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-API-Key"] = token
    return headers


def _proxy_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{_get_upstream_base_url()}{path}"
    try:
        response = requests.post(
            url,
            json=payload,
            headers=_build_upstream_headers(),
            timeout=_get_gateway_timeout(),
        )
    except requests.RequestException as exc:
        return build_api_response(
            success=False,
            data=None,
            error=f"上游服务不可用: {exc}",
        )

    try:
        body = response.json()
    except ValueError:
        body = {
            "success": False,
            "data": None,
            "error": f"上游返回非 JSON 响应: HTTP {response.status_code}",
        }

    success = bool(body.get("success", False))
    data = body.get("data")
    error = body.get("error")

    if not success and not error:
        error = f"上游请求失败: HTTP {response.status_code}"

    return build_api_response(success=success, data=data, error=error)


@app.get("/api/health", response_model=ApiResponse, summary="健康检查")
async def health() -> dict[str, Any]:
    return build_api_response(
        success=True,
        data={"ok": True, "service": "logistics-query-gateway"},
        error=None,
    )


@app.post(
    "/api/tracking/query",
    response_model=ApiResponse,
    summary="按跟踪号查询",
    dependencies=[Depends(validate_gateway_key)],
)
async def query_tracking(payload: TrackingQueryRequest) -> dict[str, Any]:
    return await asyncio.to_thread(_proxy_post, "/api/tracking/query", payload.model_dump())


@app.post(
    "/api/fba/query",
    response_model=ApiResponse,
    summary="按 FBA 编号查询",
    dependencies=[Depends(validate_gateway_key)],
)
async def query_fba(payload: FbaQueryRequest) -> dict[str, Any]:
    return await asyncio.to_thread(_proxy_post, "/api/fba/query", payload.model_dump())
