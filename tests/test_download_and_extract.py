import os

from vscode_tunnel_manager import VSCodeTunnelManager


def test_download_and_extract_vscode() -> None:
    """
    Downloads and extracts the VS Code CLI tarball.
    """
    test_path = os.path.join(os.getcwd(), "test_playground")
    os.makedirs("test_playground", exist_ok=True)
    manager = VSCodeTunnelManager(working_dir=test_path)
    vscode_path = manager.download_vscode()
    assert vscode_path.is_file(), "VS Code tarball was not downloaded successfully."
    assert vscode_path.name[-7:] == ".tar.gz", "Downloaded file is not a tar.gz file."
    manager.extract_tar_gz(vscode_path)
    assert (manager.working_dir / "code").is_file(), (
        "VS Code was not extracted successfully."
    )
