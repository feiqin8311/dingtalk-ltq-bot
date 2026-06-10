import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests


GEWECHAT_CALLBACK_EVENTS_PATH = Path(
    os.environ.get('GEWECHAT_CALLBACK_EVENTS_PATH', 'tmp/gewechat-callback-events.jsonl')
).expanduser()


def clean_text(value: Any) -> str:
    return ' '.join(str(value).split()).strip()


class GewechatClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        app_id: str,
        timeout_seconds: int = 15,
    ) -> None:
        self.base_url = base_url.rstrip('/') + '/'
        self.token = clean_text(token)
        self.app_id = clean_text(app_id)
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        if self.token:
            self.session.headers.update({'X-GEWE-TOKEN': self.token})

    def _optional_proxy_ip(self) -> str:
        return clean_text(os.environ.get('GEWECHAT_PROXY_IP', ''))

    def _optional_region_id(self) -> str:
        return clean_text(os.environ.get('GEWECHAT_REGION_ID', ''))

    def _build_url(self, path: str) -> str:
        return urljoin(self.base_url, path.lstrip('/'))

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.session.post(
            self._build_url(path),
            json=payload,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise RuntimeError(f'Gewechat 返回格式异常: {body!r}')
        return body

    def get_token(self) -> dict[str, Any]:
        token_path = os.environ.get('GEWECHAT_GET_TOKEN_PATH', '/tools/getTokenId')
        return self._post(token_path, {})

    def send_text(
        self,
        chat_wxid: str,
        content: str,
        at_user_list: list[str] | None = None,
    ) -> dict[str, Any]:
        send_text_path = os.environ.get('GEWECHAT_SEND_TEXT_PATH', '/message/sendText')
        chat_id = clean_text(chat_wxid)
        text = str(content)
        at_list = [clean_text(item) for item in (at_user_list or []) if clean_text(item)]

        payload = {
            'appId': self.app_id,
            'toWxid': chat_id,
            'wxid': chat_id,
            'content': text,
        }
        proxy_ip = self._optional_proxy_ip()
        if proxy_ip:
            payload['proxyIp'] = proxy_ip
        if at_list:
            payload['ats'] = ','.join(at_list)

        return self._post(send_text_path, payload)

    def set_callback_url(self, token: str, callback_url: str) -> dict[str, Any]:
        callback_path = os.environ.get('GEWECHAT_SET_CALLBACK_PATH', '/tools/setCallback')
        payload = {
            'token': clean_text(token),
            'callbackUrl': clean_text(callback_url),
        }
        return self._post(callback_path, payload)

    def get_login_qr_code(self, app_id: str = '') -> dict[str, Any]:
        login_qr_path = os.environ.get('GEWECHAT_GET_LOGIN_QR_PATH', '/login/getLoginQrCode')
        payload = {
            'appId': clean_text(app_id),
        }
        proxy_ip = self._optional_proxy_ip()
        region_id = self._optional_region_id()
        if proxy_ip:
            payload['proxyIp'] = proxy_ip
        if region_id:
            payload['regionId'] = region_id
        return self._post(login_qr_path, payload)

    def check_login(self, app_id: str, uuid: str, captch_code: str = '') -> dict[str, Any]:
        path = os.environ.get('GEWECHAT_CHECK_LOGIN_PATH', '/login/checkLogin')
        payload = {
            'appId': clean_text(app_id),
            'uuid': clean_text(uuid),
            'captchCode': clean_text(captch_code),
        }
        proxy_ip = self._optional_proxy_ip()
        if proxy_ip:
            payload['proxyIp'] = proxy_ip
        return self._post(path, payload)

    def check_online(self, app_id: str) -> dict[str, Any]:
        path = os.environ.get('GEWECHAT_CHECK_ONLINE_PATH', '/login/checkOnline')
        payload = {
            'appId': clean_text(app_id),
        }
        proxy_ip = self._optional_proxy_ip()
        if proxy_ip:
            payload['proxyIp'] = proxy_ip
        return self._post(path, payload)


def get_gewechat_client() -> GewechatClient:
    base_url = clean_text(os.environ.get('GEWECHAT_BASE_URL', ''))
    token = clean_text(os.environ.get('GEWECHAT_TOKEN', ''))
    app_id = clean_text(os.environ.get('GEWECHAT_APP_ID', ''))
    if not base_url:
        raise RuntimeError('缺少环境变量: GEWECHAT_BASE_URL')
    if not token:
        raise RuntimeError('缺少环境变量: GEWECHAT_TOKEN')
    if not app_id:
        raise RuntimeError('缺少环境变量: GEWECHAT_APP_ID')
    timeout_seconds = int(os.environ.get('GEWECHAT_TIMEOUT_SECONDS', '15'))
    return GewechatClient(
        base_url=base_url,
        token=token,
        app_id=app_id,
        timeout_seconds=timeout_seconds,
    )


def append_callback_event(event: dict[str, Any]) -> Path:
    GEWECHAT_CALLBACK_EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {
        'received_at': int(time.time()),
        'event': event,
    }
    with GEWECHAT_CALLBACK_EVENTS_PATH.open('a', encoding='utf-8') as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + '\n')
    return GEWECHAT_CALLBACK_EVENTS_PATH
