import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from integrations.gewechat.client import GewechatClient, clean_text


ENV_PATH = Path(__file__).resolve().parents[2] / '.env'


def load_env(path: Path = ENV_PATH) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip())


def upsert_env(updates: dict[str, str], path: Path = ENV_PATH) -> None:
    existing_lines = path.read_text(encoding='utf-8').splitlines() if path.exists() else []
    pending = dict(updates)
    new_lines: list[str] = []
    for raw_line in existing_lines:
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in raw_line:
            new_lines.append(raw_line)
            continue
        key, _ = raw_line.split('=', 1)
        stripped_key = key.strip()
        if stripped_key in pending:
            new_lines.append(f'{stripped_key}={pending.pop(stripped_key)}')
        else:
            new_lines.append(raw_line)
    for key, value in pending.items():
        new_lines.append(f'{key}={value}')
    path.write_text('\n'.join(new_lines) + '\n', encoding='utf-8')


def get_env(name: str, default: str = '') -> str:
    return clean_text(os.environ.get(name, default))


def make_client(token: str = '') -> GewechatClient:
    base_url = get_env('GEWECHAT_BASE_URL')
    if not base_url:
        raise RuntimeError('缺少环境变量: GEWECHAT_BASE_URL')
    app_id = get_env('GEWECHAT_APP_ID')
    timeout_seconds = int(get_env('GEWECHAT_TIMEOUT_SECONDS', '15') or '15')
    return GewechatClient(
        base_url=base_url,
        token=token or get_env('GEWECHAT_TOKEN'),
        app_id=app_id,
        timeout_seconds=timeout_seconds,
    )


def acquire_token() -> str:
    client = make_client(token='')
    resp = client.get_token()
    if resp.get('ret') != 200:
        raise RuntimeError(f'获取 token 失败: {resp}')
    token = clean_text(resp.get('data', ''))
    if not token:
        raise RuntimeError(f'获取 token 返回空值: {resp}')
    upsert_env({'GEWECHAT_TOKEN': token})
    return token


def bootstrap_login() -> dict[str, Any]:
    token = get_env('GEWECHAT_TOKEN') or acquire_token()
    client = make_client(token=token)
    current_app_id = get_env('GEWECHAT_APP_ID')

    if current_app_id:
        online_resp = client.check_online(current_app_id)
        if online_resp.get('ret') == 200 and online_resp.get('data'):
            callback_url = get_env('GEWECHAT_CALLBACK_URL')
            callback_resp = client.set_callback_url(token, callback_url) if callback_url else {}
            return {
                'token': token,
                'app_id': current_app_id,
                'online': True,
                'callback': callback_resp,
                'message': '当前 app_id 已在线',
            }

    qr_resp = client.get_login_qr_code(current_app_id)
    if qr_resp.get('ret') != 200:
        raise RuntimeError(f'获取登录二维码失败: {qr_resp}')
    qr_data = qr_resp.get('data') or {}
    app_id = clean_text(qr_data.get('appId', ''))
    uuid = clean_text(qr_data.get('uuid', ''))
    qr_url = clean_text(qr_data.get('qrData', '')) or (f'http://weixin.qq.com/x/{uuid}' if uuid else '')
    if not app_id or not uuid:
        raise RuntimeError(f'二维码返回缺少 appId/uuid: {qr_resp}')

    upsert_env({'GEWECHAT_TOKEN': token, 'GEWECHAT_APP_ID': app_id})

    print('请扫码登录:')
    print(f'app_id={app_id}')
    print(f'uuid={uuid}')
    print(f'qr_url={qr_url}')

    max_attempts = int(get_env('GEWECHAT_LOGIN_POLL_MAX_ATTEMPTS', '100') or '100')
    poll_interval_seconds = float(get_env('GEWECHAT_LOGIN_POLL_INTERVAL_SECONDS', '5') or '5')

    for _ in range(max_attempts):
        check_resp = client.check_login(app_id, uuid, '')
        if check_resp.get('ret') != 200:
            raise RuntimeError(f'检查登录状态失败: {check_resp}')
        data = check_resp.get('data') or {}
        status = data.get('status')
        expired_time = int(data.get('expiredTime') or 0)
        if status == 2:
            callback_url = get_env('GEWECHAT_CALLBACK_URL')
            callback_resp = client.set_callback_url(token, callback_url) if callback_url else {}
            return {
                'token': token,
                'app_id': app_id,
                'uuid': uuid,
                'qr_url': qr_url,
                'online': True,
                'callback': callback_resp,
                'nick_name': data.get('nickName', ''),
            }
        if expired_time and expired_time <= 5:
            raise RuntimeError('二维码即将过期，请重新执行 bootstrap')
        time.sleep(poll_interval_seconds)

    raise RuntimeError('登录超时，请重新执行 bootstrap')


def main() -> None:
    load_env()
    parser = argparse.ArgumentParser()
    parser.add_argument('--token-only', action='store_true')
    args = parser.parse_args()

    if args.token_only:
        token = acquire_token()
        print(json.dumps({'token': token}, ensure_ascii=False, indent=2))
        return

    result = bootstrap_login()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False, indent=2))
        sys.exit(1)
