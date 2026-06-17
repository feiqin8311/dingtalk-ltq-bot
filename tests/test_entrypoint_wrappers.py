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

    def test_windows_start_scripts_include_cdp_diagnostics_on_timeout(self):
        project_dir = Path(__file__).resolve().parents[1]

        for relative_path in (
            "scripts/windows/start_all.ps1",
            "scripts/windows/start_api.ps1",
            "scripts/windows/start_bot.ps1",
        ):
            script_text = (project_dir / relative_path).read_text(encoding="utf-8")

            self.assertIn("function Write-CdpDiagnostics", script_text)
            self.assertIn("function Resolve-AbsolutePath", script_text)
            self.assertIn("CDP diagnostics:", script_text)
            self.assertIn("Get-NetTCPConnection", script_text)
            self.assertIn("Chrome may have attached to an existing profile", script_text)


if __name__ == "__main__":
    unittest.main()
