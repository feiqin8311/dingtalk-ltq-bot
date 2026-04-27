from __future__ import annotations

import os
from typing import Any

import requests

AUTOMATION_CENTER_LOGISTICS_BASE_URL = (
    os.environ.get("AUTOMATION_CENTER_LOGISTICS_BASE_URL", "http://127.0.0.1:27644").strip()
    or "http://127.0.0.1:27644"
)


def _post_query(platform: str, query_value: str, order: dict[str, Any] | None = None, headless: bool = False) -> dict[str, Any]:
    response = requests.post(
        f"{AUTOMATION_CENTER_LOGISTICS_BASE_URL}/query",
        json={
            "platform": platform,
            "query_value": query_value,
            "order": order or {},
            "headless": headless,
        },
        timeout=180,
    )
    response.raise_for_status()
    return response.json()


def query_agl(booking_id: str, order: dict[str, Any], headless: bool = False) -> dict[str, Any]:
    return _post_query("agl", booking_id, order=order, headless=headless)


async def query_pingyi(fba_code: str) -> dict[str, Any]:
    return _post_query("pingyi", fba_code)


async def query_baosen(order_no: str) -> dict[str, Any]:
    return _post_query("baosen", order_no)


async def query_17track(order_no: str) -> dict[str, Any]:
    return _post_query("17track", order_no)
