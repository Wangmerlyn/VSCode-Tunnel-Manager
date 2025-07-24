import pathlib

from vscode_tunnel_manager import VSCodeTunnelManager, VSCodeTunnelManagerConfig
from vscode_tunnel_manager.email_manager import SMTPConfig

mail_config = SMTPConfig(
    host="smtp.example.com",
    port=587,
    username="user@example.com",
    use_ssl=False,
    starttls=True,
    from_addr="user@example.com",
    to_addrs=["recipient@example.com"],
    subject_prefix="[VS Code Tunnel] ",
)

tunnel_config = VSCodeTunnelManagerConfig(
    working_dir=pathlib.Path("~/tmp/code-tunnel").expanduser(),
)


def test_download_and_extract_vscode(tmp_path: pathlib.Path) -> None:
    """
    Downloads and extracts the VS Code CLI tarball.
    """
    manager = VSCodeTunnelManager(mailer_config=mail_config, tunnel_config=tunnel_config)
    vscode_path = manager.download_vscode()
    assert vscode_path.is_file(), "VS Code tarball was not downloaded successfully."
    assert vscode_path.name.endswith(".tar.gz"), "Downloaded file is not a tar.gz file."
    manager.extract_tar_gz(vscode_path)
    assert (manager.working_dir / "code").is_file(), (
        "VS Code was not extracted successfully."
    )
