import asyncio
import logging
import os
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from logistics_query import (
    BaosenLoginError,
    SERIAL_BROWSER_TRACKING_PLATFORMS,
    attach_tracking_result_link,
    decide_platform,
    decide_tracking_platform,
    find_order_by_fba,
    get_logistics_nos,
    get_primary_logistics_no,
    combine_tracking_results_by_logistics_no,
    get_tracking_query_cache,
    query_17track,
    query_agl,
    query_baosen,
    query_yinghe,
    query_meitong,
    query_pingyi,
    query_tracking_number,
    run_browser_tracking_query_with_queue,
    set_tracking_query_cache,
)
from qq_query import query_qq
from services.tracking_runtime import run_tracking_query_attempt_with_timeout


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
)
logger = logging.getLogger(__name__)

_TRACK_QUERY_MAX_ATTEMPTS = 3
_TRACK_QUERY_RETRY_DELAY_SECONDS = 2


def _build_agl_cache_key(order: dict[str, Any], tracking_no: str) -> str:
    brand = str(order.get("品牌", "") or "").strip().upper()
    normalized_tracking_no = str(tracking_no or "").strip().upper()
    return f"agl:{brand}:{normalized_tracking_no}"

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
    fba_code: str | None = Field(default=None, description="要查询的 FBA 编号；无 FBA 时可只传 logistics_no")
    logistics_no: str | None = Field(
        default=None,
        description="直接查询的物流编号；可配合 platform=agl 或 platform=yinghe 跳过钉钉表格",
    )
    brand: str | None = Field(default=None, description="直接龙舟查询的品牌，用于选择对应 AGL 账号")
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


def _should_retry_tracking_result(platform: str, result: dict[str, Any] | None) -> bool:
    if not isinstance(result, dict):
        return False
    error = str(result.get("错误", "") or "").strip()
    if not error:
        return False
    if result.get("物流轨迹"):
        return False
    normalized_platform = str(platform or "").strip().upper()
    if normalized_platform == "FEDEX":
        non_retryable_markers = (
            "FedEx 系统错误页",
            "fedextrack/system-error",
            "system-error",
        )
        if any(marker in error for marker in non_retryable_markers):
            return False
    if normalized_platform == "USPS":
        non_retryable_markers = (
            "Akamai",
            "ISTL-REFERER",
            "X-Akamai",
            "当前浏览器会话需要人工打开 USPS",
        )
        if any(marker in error for marker in non_retryable_markers):
            return False
    if normalized_platform == "AGL" and result.get("阻塞原因") in {
        "MFA_REQUIRED",
        "MANUAL_LOGIN_TIMEOUT",
        "LOGIN_NOT_COMPLETED",
        "ZINIAO_AGL_LOGIN_REQUIRED",
        "TRACKING_NOT_RENDERED",
    }:
        return False
    if normalized_platform == "QQ":
        non_retryable_markers = (
            "等待 QQ 回复超时",
            "token verify failed",
            "QQ API HTTP 异常: status=403",
            "action=send_group_msg error=Timeout",
            "NodeIKernelMsgService/sendMsg",
            "未找到目标QQ群",
            "中未找到成员",
            "存在多个同名成员",
            "当前货代公司未配置 QQ 查询规则",
        )
        if any(marker in error for marker in non_retryable_markers):
            return False
    if normalized_platform in {"平谊", "PINGYI"} and "未找到 FBA" in error:
        return False
    return True


async def _run_tracking_query_with_retry(
    platform: str,
    query_value: str,
    operation,
    *,
    enforce_attempt_timeout: bool = True,
):
    last_error: Exception | None = None
    last_result: dict[str, Any] | None = None

    for attempt in range(1, _TRACK_QUERY_MAX_ATTEMPTS + 1):
        try:
            if enforce_attempt_timeout:
                result = await run_tracking_query_attempt_with_timeout(platform, query_value, operation)
            else:
                result = operation()
                if asyncio.iscoroutine(result) or isinstance(result, asyncio.Future):
                    result = await result

            if _should_retry_tracking_result(platform, result):
                error = str((result or {}).get("错误", "")).strip() or "未知错误"
                last_result = result
                logger.warning(
                    "API跟踪号查询失败，准备重试: tracking_no=%s 平台=%s attempt=%s/%s 错误=%s",
                    query_value,
                    platform,
                    attempt,
                    _TRACK_QUERY_MAX_ATTEMPTS,
                    error,
                )
                if attempt < _TRACK_QUERY_MAX_ATTEMPTS:
                    await asyncio.sleep(_TRACK_QUERY_RETRY_DELAY_SECONDS)
                    continue
            return result
        except Exception as exc:
            last_error = exc
            if isinstance(exc, BaosenLoginError):
                logger.warning(
                    "API跟踪号查询遇到不可重试错误: tracking_no=%s 平台=%s 错误=%s",
                    query_value,
                    platform,
                    exc,
                )
                raise
            logger.warning(
                "API跟踪号查询异常，准备重试: tracking_no=%s 平台=%s attempt=%s/%s 错误=%s",
                query_value,
                platform,
                attempt,
                _TRACK_QUERY_MAX_ATTEMPTS,
                exc,
            )
            if attempt < _TRACK_QUERY_MAX_ATTEMPTS:
                await asyncio.sleep(_TRACK_QUERY_RETRY_DELAY_SECONDS)
                continue
            raise

    if last_result is not None:
        return last_result
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"跟踪号查询失败: 平台={platform} 查询值={query_value}")


async def _query_fba_tracking_result(order: dict[str, Any], fba_code: str, explicit_platform: str) -> dict[str, Any] | None:
    platform = decide_platform(order, explicit_platform)
    tracking_no = get_primary_logistics_no(order)
    logger.info(
        "API FBA轨迹查询: FBA=%s 平台=%s 查询值=%s explicit_platform=%s",
        fba_code,
        platform,
        tracking_no,
        explicit_platform,
    )

    if platform == "none":
        logger.info("API FBA轨迹查询跳过: FBA=%s 平台=none", fba_code)
        return None

    if platform in {"meitong", "agl", "baosen", "qq", "17track", "yinghe"} and not tracking_no:
        logger.warning("API FBA轨迹查询失败: FBA=%s 平台=%s 错误=缺少物流编号", fba_code, platform)
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
        cache_key = _build_agl_cache_key(order, tracking_no)
        cached_result = get_tracking_query_cache(cache_key)
        if cached_result is not None:
            logger.info("API FBA轨迹查询缓存命中: 平台=AGL 查询值=%s", tracking_no)
            return cached_result
        result = await run_browser_tracking_query_with_queue(
            platform="AGL",
            query_value=tracking_no,
            operation=lambda: _run_tracking_query_with_retry(
                platform="AGL",
                query_value=tracking_no,
                operation=lambda: asyncio.to_thread(query_agl, tracking_no, order, False),
                enforce_attempt_timeout=False,
            ),
            dedup_key=cache_key,
        )
        set_tracking_query_cache(cache_key, result)
        return result
    if platform == "pingyi":
        return await _run_tracking_query_with_retry(
            platform="PINGYI",
            query_value=fba_code,
            operation=lambda: query_pingyi(fba_code),
        )
    if platform == "baosen":
        logistics_nos = get_logistics_nos(order)
        baosen_results: list[tuple[str, dict[str, Any]]] = []
        for logistics_no in logistics_nos:
            result = await run_browser_tracking_query_with_queue(
                platform="BAOSEN",
                query_value=logistics_no,
                operation=lambda logistics_no=logistics_no: _run_tracking_query_with_retry(
                    platform="BAOSEN",
                    query_value=logistics_no,
                    operation=lambda: query_baosen(logistics_no),
                ),
            )
            baosen_results.append((logistics_no, result))
        return combine_tracking_results_by_logistics_no("堡森", baosen_results)
    if platform == "qq":
        return await asyncio.to_thread(query_qq, order, tracking_no)
    if platform == "17track":
        return await run_browser_tracking_query_with_queue(
            platform="17TRACK",
            query_value=tracking_no,
            operation=lambda: _run_tracking_query_with_retry(
                platform="17TRACK",
                query_value=tracking_no,
                operation=lambda: query_17track(tracking_no),
            ),
        )
    if platform == "yinghe":
        return await run_browser_tracking_query_with_queue(
            platform="YINGHE",
            query_value=tracking_no,
            operation=lambda: _run_tracking_query_with_retry(
                platform="YINGHE",
                query_value=tracking_no,
                operation=lambda: query_yinghe(tracking_no),
            ),
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
    logger.info("API跟踪号查询开始: tracking_no=%s 平台=%s", payload.tracking_no, platform)
    try:
        if platform in SERIAL_BROWSER_TRACKING_PLATFORMS:
            result = await run_browser_tracking_query_with_queue(
                platform=platform.upper(),
                query_value=payload.tracking_no,
                operation=lambda: _run_tracking_query_with_retry(
                    platform=platform.upper(),
                    query_value=payload.tracking_no,
                    operation=lambda: query_tracking_number(payload.tracking_no),
                ),
            )
        else:
            result = await _run_tracking_query_with_retry(
                platform=platform.upper(),
                query_value=payload.tracking_no,
                operation=lambda: query_tracking_number(payload.tracking_no),
            )
    except Exception as exc:
        error = str(exc).strip() or "跟踪号查询异常"
        logger.error(
            "API跟踪号查询异常: tracking_no=%s 平台=%s 错误=%s",
            payload.tracking_no,
            platform,
            error,
            exc_info=True,
        )
        result = attach_tracking_result_link(
            {
                "平台": str(platform).upper(),
                "查询值": payload.tracking_no,
                "物流轨迹": [],
                "最新轨迹": {},
                "错误": error,
            }
        )
        return build_api_response(success=False, data=result, error=error)

    result = attach_tracking_result_link(result)
    error = str(result.get("错误", "") or "").strip()
    if error:
        logger.warning(
            "API跟踪号查询失败: tracking_no=%s 平台=%s 错误=%s",
            payload.tracking_no,
            result.get("平台", platform),
            error,
        )
        return build_api_response(success=False, data=result, error=error)
    logger.info(
        "API跟踪号查询完成: tracking_no=%s 平台=%s 条数=%s",
        payload.tracking_no,
        result.get("平台", platform),
        len(result.get("物流轨迹") or []),
    )
    return build_api_response(success=True, data=result, error=None)


@app.post(
    "/api/fba/query",
    response_model=ApiResponse,
    summary="按 FBA 编号查询",
    dependencies=[Depends(validate_api_key)],
)
async def query_fba(payload: FbaQueryRequest) -> dict[str, Any]:
    fba_code = (payload.fba_code or "").strip()
    logistics_no = (payload.logistics_no or "").strip()
    logger.info(
        "API FBA查询开始: FBA=%s logistics_no=%s explicit_platform=%s include_order=%s include_tracking=%s",
        fba_code,
        logistics_no,
        payload.platform,
        payload.include_order,
        payload.include_tracking,
    )

    if logistics_no:
        if payload.platform not in {"auto", "agl", "yinghe"}:
            error = "传入 logistics_no 时仅支持 platform=agl、yinghe 或 auto"
            return build_api_response(success=False, data=None, error=error)

        direct_platform = "agl" if payload.platform == "auto" else payload.platform
        order = {
            "货代公司": "盈和" if direct_platform == "yinghe" else "龙舟",
            "物流编号": logistics_no,
            "品牌": (payload.brand or "").strip(),
        }
        matched_platform = direct_platform
        result: dict[str, Any] = {
            "FBA编号": fba_code,
            "物流编号": logistics_no,
            "线上表匹配结果": None,
            "命中平台": matched_platform,
            "物流查询结果": None,
        }
        if payload.include_tracking:
            result["物流查询结果"] = await _query_fba_tracking_result(
                order,
                fba_code or logistics_no,
                direct_platform,
            )
    else:
        if not fba_code:
            return build_api_response(success=False, data=None, error="fba_code 或 logistics_no 至少需要传一个")

        order = find_order_by_fba(fba_code)
        matched_platform = decide_platform(order, payload.platform)

        result = {
            "FBA编号": fba_code,
            "线上表匹配结果": order if payload.include_order else None,
            "命中平台": matched_platform,
            "物流查询结果": None,
        }

        if not order:
            logger.warning("API FBA查询失败: FBA=%s 错误=未找到对应FBA记录", fba_code)
            return build_api_response(success=False, data=result, error="未找到对应FBA记录")

        if payload.include_tracking:
            result["物流查询结果"] = await _query_fba_tracking_result(order, fba_code, payload.platform)

    tracking_error = ""
    if isinstance(result.get("物流查询结果"), dict):
        tracking_error = str(result["物流查询结果"].get("错误", "") or "").strip()

    if tracking_error:
        logger.warning(
            "API FBA查询失败: FBA=%s 平台=%s 错误=%s",
            fba_code,
            matched_platform,
            tracking_error,
        )
        return build_api_response(success=False, data=result, error=tracking_error)
    track_count = 0
    if isinstance(result.get("物流查询结果"), dict):
        track_count = len(result["物流查询结果"].get("物流轨迹") or [])
    logger.info(
        "API FBA查询完成: FBA=%s 平台=%s include_tracking=%s 条数=%s",
        fba_code,
        matched_platform,
        payload.include_tracking,
        track_count,
    )
    return build_api_response(success=True, data=result, error=None)
