import argparse
import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from integrations.gewechat.client import GEWECHAT_CALLBACK_EVENTS_PATH, append_callback_event


logger = logging.getLogger(__name__)


class GewechatWebhookHandler(BaseHTTPRequestHandler):
    server_version = 'GewechatWebhook/0.1'

    def _write_json(self, status_code: int, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_POST(self) -> None:  # noqa: N802
        content_length = int(self.headers.get('Content-Length', '0') or 0)
        raw_body = self.rfile.read(content_length) if content_length > 0 else b'{}'
        try:
            payload = json.loads(raw_body.decode('utf-8') or '{}')
        except json.JSONDecodeError:
            logger.warning('Gewechat webhook 收到非法 JSON: %r', raw_body[:500])
            self._write_json(400, {'ok': False, 'error': 'invalid json'})
            return

        output_path = append_callback_event(payload)
        logger.info('Gewechat webhook 已写入 %s', output_path)
        self._write_json(200, {'ok': True, 'events_path': str(output_path)})

    def log_message(self, format: str, *args: Any) -> None:
        logger.info('%s - %s', self.address_string(), format % args)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=8788)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)-8s %(message)s',
    )

    server = ThreadingHTTPServer((args.host, args.port), GewechatWebhookHandler)
    logger.info('Gewechat webhook 监听中: http://%s:%s', args.host, args.port)
    logger.info('事件文件: %s', GEWECHAT_CALLBACK_EVENTS_PATH)
    server.serve_forever()


if __name__ == '__main__':
    main()
