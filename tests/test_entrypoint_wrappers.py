import unittest
from pathlib import Path


class EntrypointWrapperTests(unittest.TestCase):
    def test_gateway_server_root_wrapper_delegates_to_services_package(self):
        project_dir = Path(__file__).resolve().parents[1]
        script_text = (project_dir / "gateway_server.py").read_text(encoding="utf-8")

        self.assertIn("from services.gateway_server import *", script_text)

    def test_host_bootstrap_root_wrapper_delegates_to_services_package(self):
        project_dir = Path(__file__).resolve().parents[1]
        script_text = (project_dir / "host_bootstrap.py").read_text(encoding="utf-8")

        self.assertIn("from services.host_bootstrap import *", script_text)

    def test_gewechat_root_wrappers_delegate_to_integrations_package(self):
        project_dir = Path(__file__).resolve().parents[1]

        client_text = (project_dir / "gewechat_client.py").read_text(encoding="utf-8")
        bootstrap_text = (project_dir / "gewechat_bootstrap.py").read_text(encoding="utf-8")
        webhook_text = (project_dir / "gewechat_webhook.py").read_text(encoding="utf-8")

        self.assertIn("from integrations.gewechat.client import *", client_text)
        self.assertIn("from integrations.gewechat.bootstrap import *", bootstrap_text)
        self.assertIn("from integrations.gewechat.webhook import *", webhook_text)


if __name__ == "__main__":
    unittest.main()
