import threading
import time
from pathlib import Path

import pytest

from vscode_tunnel_manager import VSCodeTunnelManager, VSCodeTunnelManagerConfig
from vscode_tunnel_manager.email_manager import SMTPConfig


@pytest.mark.manual
def test_running_tunnel(tmp_path: Path) -> None:
    tunnel_config = VSCodeTunnelManagerConfig(
        working_dir=tmp_path
    )

    cfg = SMTPConfig(
        host="smtp.gmail.com",
        port=587,
        username="sywang0227@gmail.com",
        use_ssl=False,
        starttls=True,
        from_addr="sywang0227@gmail.com",
        to_addrs=["wsy0227@sjtu.edu.cn"],
        subject_prefix="[VS Code Tunnel] ",
    )
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
    assert "device_code" in log_content, (
        "Tunnel did not start correctly, the log does not contain 'device_code'."
    )
