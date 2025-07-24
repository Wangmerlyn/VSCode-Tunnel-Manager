import pytest

from vscode_tunnel_manager import VSCodeTunnelManager
from vscode_tunnel_manager.email_manager import SMTPConfig


@pytest.mark.manual
def test_running_tunnel() -> None:
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
    manager = VSCodeTunnelManager(cfg, working_dir="~/tmp/code-tunnel")
    vscode_path = manager.download_vscode()
    manager.extract_tar_gz(vscode_path)
    manager.start_tunnel()
