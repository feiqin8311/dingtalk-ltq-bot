import os
import subprocess
import time
from pathlib import Path

import requests


def get_cdp_url(port: int) -> str:
    host = os.environ.get("LOCAL_CDP_HOST", "127.0.0.1").strip() or "127.0.0.1"
    return f"http://{host}:{port}/json/version/"


def is_cdp_ready(port: int) -> bool:
    try:
        response = requests.get(get_cdp_url(port), timeout=2)
        response.raise_for_status()
        payload = response.json()
        return isinstance(payload, dict) and bool(payload.get("webSocketDebuggerUrl"))
    except (requests.RequestException, ValueError):
        return False


def ensure_host_cdp(project_dir: Path, port: int = 19444, mode: str = "visible", wait_seconds: int = 15) -> None:
    if is_cdp_ready(port):
        return

    subprocess.run(
        [str(project_dir / "start_host_cdp.sh"), str(port), mode],
        cwd=str(project_dir),
        check=True,
    )

    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if is_cdp_ready(port):
            return
        time.sleep(0.5)

    raise RuntimeError(f"宿主机 CDP 未在 {wait_seconds}s 内就绪: {get_cdp_url(port)}")
def main() -> None:
    project_dir = Path(__file__).resolve().parent
    port = int(os.environ.get("LOCAL_CDP_PORT", "19444").strip() or "19444")
    mode = "headless" if os.environ.get("LOCAL_CDP_HEADLESS", "").strip().lower() in {"1", "true", "yes", "on"} else "visible"
    ensure_host_cdp(project_dir, port=port, mode=mode)


if __name__ == "__main__":
    main()
