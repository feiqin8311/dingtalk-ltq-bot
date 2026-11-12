import unittest
from pathlib import Path

from services import runtime_artifacts


class RuntimeArtifactsTests(unittest.TestCase):
    def test_debug_dir_uses_platform_debug_suffix(self):
        project_dir = Path("/project")

        directory = runtime_artifacts.debug_dir(project_dir, platform="uniuni", day="2026-06-18")

        self.assertEqual(directory, project_dir / "tmp" / "uniuni-debug" / "2026-06-18")

    def test_download_dir_uses_tracking_downloads_layout(self):
        project_dir = Path("/project")

        directory = runtime_artifacts.download_dir(project_dir, platform="gofo", day="2026-06-18")

        self.assertEqual(directory, project_dir / "tmp" / "tracking-downloads" / "2026-06-18" / "gofo")


if __name__ == "__main__":
    unittest.main()
