import os
import tempfile
import unittest
from unittest import mock

from integrations.ziniao import client as ziniao_client
from integrations.ziniao.client import ZiniaoWebDriverClient, resolve_ziniao_client_path


class ZiniaoWebDriverClientTests(unittest.TestCase):
    def test_resolve_client_path_prefers_explicit_existing_path(self):
        with mock.patch('integrations.ziniao.client.Path.is_file', return_value=True):
            self.assertEqual(resolve_ziniao_client_path('/custom/ziniao.exe'), '/custom/ziniao.exe')

    def test_start_browser_uses_official_http_payload_and_returns_debug_port(self):
        client = ZiniaoWebDriverClient('company', 'user', 'password', 16851)
        core_result = {'statusCode': 0}
        start_result = {'statusCode': 0, 'debuggingPort': 24567, 'browserOauth': 'store'}

        with mock.patch.object(client, 'ensure_running') as ensure_running, \
             mock.patch.object(client, 'update_core') as update_core, \
             mock.patch.object(client, '_request', return_value=start_result) as request:
            result = client.start_browser('27864375894927')

        ensure_running.assert_called_once()
        update_core.assert_called_once()
        request.assert_called_once_with(
            'startBrowser',
            {
                'isWaitPluginUpdate': 0,
                'isHeadless': 0,
                'isWebDriverReadOnlyMode': 0,
                'cookieTypeLoad': 0,
                'cookieTypeSave': 0,
                'runMode': '1',
                'isLoadUserPlugin': False,
                'pluginIdType': 1,
                'privacyMode': 0,
                'browserId': '27864375894927',
            },
        )
        self.assertEqual(result, start_result)

    def test_start_browser_requires_debugging_port(self):
        client = ZiniaoWebDriverClient('company', 'user', 'password', 16851)
        with mock.patch.object(client, 'ensure_running'), \
             mock.patch.object(client, 'update_core'), \
             mock.patch.object(client, '_request', return_value={'statusCode': 0}):
            with self.assertRaisesRegex(RuntimeError, 'debuggingPort'):
                client.start_browser('27864375894927')

    def test_get_or_start_browser_reuses_reachable_debugging_port(self):
        client = ZiniaoWebDriverClient('company', 'user', 'password', 16851)
        with mock.patch('integrations.ziniao.client._BROWSER_DEBUGGING_PORTS', {'27864375894927': 24567}), \
             mock.patch.object(client, '_debugging_port_is_available', return_value=True), \
             mock.patch.object(client, 'start_browser') as start_browser:
            result = client.get_or_start_browser('27864375894927')

        self.assertEqual(result['debuggingPort'], 24567)
        self.assertTrue(result['reused'])
        start_browser.assert_not_called()

    def test_get_or_start_browser_starts_when_cached_port_is_unavailable(self):
        client = ZiniaoWebDriverClient('company', 'user', 'password', 16851)
        with mock.patch('integrations.ziniao.client._BROWSER_DEBUGGING_PORTS', {'27864375894927': 24567}) as ports, \
             mock.patch.object(client, '_debugging_port_is_available', return_value=False), \
             mock.patch.object(client, '_forget_debugging_port') as forget_debugging_port, \
             mock.patch.object(client, '_remember_debugging_port') as remember_debugging_port, \
             mock.patch.object(client, 'start_browser', return_value={'statusCode': 0, 'debuggingPort': 24568}) as start_browser:
            result = client.get_or_start_browser('27864375894927')

        self.assertEqual(result['debuggingPort'], 24568)
        forget_debugging_port.assert_called_once_with('27864375894927')
        remember_debugging_port.assert_called_once_with('27864375894927', 24568)
        start_browser.assert_called_once_with('27864375894927')

    def test_get_or_start_browser_reuses_persisted_reachable_debugging_port(self):
        browser_id = '27864375894927'
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = os.path.join(temp_dir, 'ziniao-browser-ports.json')
            with mock.patch.dict(os.environ, {'ZINIAO_BROWSER_STATE_PATH': state_path}, clear=False), \
                 mock.patch('integrations.ziniao.client._BROWSER_DEBUGGING_PORTS', {}), \
                 mock.patch.object(ZiniaoWebDriverClient, '_debugging_port_is_available', return_value=True), \
                 mock.patch.object(ZiniaoWebDriverClient, 'start_browser') as start_browser:
                first_client = ZiniaoWebDriverClient('company', 'user', 'password', 16851)
                first_client._remember_debugging_port(browser_id, 24567)
                ziniao_client._BROWSER_DEBUGGING_PORTS.clear()

                second_client = ZiniaoWebDriverClient('company', 'user', 'password', 16851)
                result = second_client.get_or_start_browser(browser_id)

        self.assertEqual(result['debuggingPort'], 24567)
        self.assertTrue(result['reused'])
        start_browser.assert_not_called()

    def test_credentials_are_sent_with_every_request(self):
        client = ZiniaoWebDriverClient('company', 'user', 'password', 16851)
        response = mock.Mock()
        response.json.return_value = {'statusCode': 0}
        response.raise_for_status.return_value = None

        with mock.patch('integrations.ziniao.client.requests.post', return_value=response) as post:
            result = client._request('getBrowserList', {'example': True}, timeout=12)

        self.assertEqual(result, {'statusCode': 0})
        payload = __import__('json').loads(post.call_args.kwargs['data'].decode('utf-8'))
        self.assertEqual(payload['action'], 'getBrowserList')
        self.assertEqual(payload['company'], 'company')
        self.assertEqual(payload['username'], 'user')
        self.assertEqual(payload['password'], 'password')
        self.assertTrue(payload['example'])
        self.assertEqual(post.call_args.kwargs['timeout'], 12)


if __name__ == '__main__':
    unittest.main()
