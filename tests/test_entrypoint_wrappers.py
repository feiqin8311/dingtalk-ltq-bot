import unittest
from pathlib import Path


class EntrypointWrapperTests(unittest.TestCase):
    def test_gateway_server_root_wrapper_delegates_to_services_package(self):
        project_dir = Path(__file__).resolve().parents[1]
        script_text = (project_dir / "gateway_server.py").read_text(encoding="utf-8")

        self.assertIn("from services.gateway_server import *", script_text)

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
            "launcher/start_all.ps1",
        ):
            script_text = (project_dir / relative_path).read_text(encoding="utf-8")

            self.assertIn("function Write-CdpDiagnostics", script_text)
            self.assertIn("function Resolve-AbsolutePath", script_text)
            self.assertIn("CDP diagnostics:", script_text)
            self.assertIn("Get-NetTCPConnection", script_text)
            self.assertIn("Chrome may have attached to an existing profile", script_text)

    def test_windows_start_all_batch_launcher_runs_powershell_wrapper(self):
        project_dir = Path(__file__).resolve().parents[1]
        script_text = (project_dir / "start_all.bat").read_text(encoding="utf-8")

        self.assertIn("conda run --no-capture-output -n dingtalk-bot", script_text)
        self.assertIn("DINGTALK_PYTHON_EXE=python", script_text)
        self.assertIn("powershell.exe", script_text)
        self.assertIn("-ExecutionPolicy Bypass", script_text)
        self.assertIn("%~dp0launcher\\start_all.ps1", script_text)
        self.assertIn("pause", script_text)

    def test_windows_start_all_prefers_explicit_launcher_python(self):
        project_dir = Path(__file__).resolve().parents[1]
        script_text = (project_dir / "launcher" / "start_all.ps1").read_text(encoding="utf-8")

        self.assertIn("$ConfiguredPython = $env:DINGTALK_PYTHON_EXE", script_text)
        self.assertIn("if ($ConfiguredPython)", script_text)
        self.assertIn(
            "$ProjectDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)",
            script_text,
        )

    def test_legacy_windows_launchers_are_removed(self):
        project_dir = Path(__file__).resolve().parents[1]

        for relative_path in (
            "start_all.ps1",
            "start_api.ps1",
            "start_bot.ps1",
            "start_chrome.bat",
            "start_remote_node.ps1",
            "scripts",
        ):
            self.assertFalse((project_dir / relative_path).exists(), relative_path)


if __name__ == "__main__":
    unittest.main()
