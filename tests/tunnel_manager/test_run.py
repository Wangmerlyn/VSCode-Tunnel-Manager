import threading
import time
from pathlib import Path

import pytest

from vscode_tunnel_manager import VSCodeTunnelManager, VSCodeTunnelManagerConfig

LOGIN_URL="https://github.com/login/device"
CODE_PREFIX="use code"


@pytest.mark.manual
def test_running_tunnel(tmp_path: Path=Path("tmp/code_working_dir")) -> None:
    tunnel_config = VSCodeTunnelManagerConfig(
        working_dir=tmp_path
    )

    cfg =None
    manager = VSCodeTunnelManager(cfg, tunnel_config=tunnel_config)
    vscode_path = manager.download_vscode()
    manager.extract_tar_gz(vscode_path)

    tunnel_thread = threading.Thread(target=manager.start_tunnel)
    tunnel_thread.daemon = True
    tunnel_thread.start()

    time.sleep(30)

    log_path = tmp_path / "vscode_tunnel_runtime.log"
    assert log_path.exists(), "Log file not found."

    log_content = log_path.read_text()
    assert LOGIN_URL in log_content, (
        "Tunnel did not start correctly, the log does not contain login url."
    )
    assert CODE_PREFIX in log_content, (
        "Tunnel did not start correctly, the log does not contain code."
    )
