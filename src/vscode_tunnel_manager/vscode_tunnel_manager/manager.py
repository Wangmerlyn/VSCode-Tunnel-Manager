import pathlib
import tarfile
from typing import Union

import requests

from vscode_tunnel_manager.utils.logger import setup_logger

logger = setup_logger(name=__name__)


class VSCodeTunnelManager:
    """
    Manages the CLI interface for the VSCode Tunnel Manager.

    This class provides utilities to download and extract the VS Code CLI
    without mutating global process state (i.e., without calling os.chdir()).
    """

    def __init__(self, working_dir: Union[str, pathlib.Path] = ".") -> None:
        self.working_dir = pathlib.Path(working_dir).resolve()
        if not self.working_dir.is_dir():
            logger.error(f"Working directory does not exist: {self.working_dir}")
            raise ValueError(f"Invalid working directory: {self.working_dir}")
        logger.info(
            "Initialized VSCodeTunnelManager with working dir: %s", self.working_dir
        )

    def download_vscode(
        self,
        url: str = "https://code.visualstudio.com/sha/download?build=stable&os=cli-alpine-x64",
        output: Union[str, pathlib.Path] = "vscode_cli.tar.gz",
        verify_ssl: bool = True,
        chunk_size: int = 8192,
    ) -> pathlib.Path:
        """
        Download the VS Code CLI tarball using a streaming HTTP request.

        Args:
            url: Download URL.
            output: Relative (to working_dir) or absolute path to save the file.
            verify_ssl: Verify SSL certificates (False mimics `curl -k`).
            chunk_size: Stream chunk size in bytes.

        Returns:
            Path to the downloaded file.
        """
        output_path = (self.working_dir / output).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info("Downloading VS Code CLI from %s to %s", url, output_path)
        with requests.get(url, stream=True, verify=verify_ssl) as resp:
            resp.raise_for_status()
            with output_path.open("wb") as f:
                for chunk in resp.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)

        if not output_path.is_file():
            logger.error("Failed to download VS Code tarball: %s", output_path)
            raise FileNotFoundError(f"Downloaded file not found: {output_path}")

        logger.debug("Downloaded file size: %d bytes", output_path.stat().st_size)
        return output_path

    def extract_tar_gz(
        self,
        archive_path: Union[str, pathlib.Path],
        extract_to: Union[str, pathlib.Path] = ".",
    ) -> pathlib.Path:
        """
        Extract a .tar.gz archive into the given directory.

        Args:
            archive_path: Path to the .tar.gz file
            (relative to working_dir or absolute).
            extract_to: Directory to extract into (relative to working_dir or absolute).

        Returns:
            Path to the extraction directory.
        """
        archive_path = (self.working_dir / archive_path).resolve()
        extract_path = (self.working_dir / extract_to).resolve()
        extract_path.mkdir(parents=True, exist_ok=True)

        logger.info("Extracting %s to %s", archive_path, extract_path)
        with tarfile.open(archive_path, "r:gz") as tar:
            # Security: Prevent path traversal attacks by checking each member.
            resolved_extract_path = extract_path.resolve()
            for member in tar.getmembers():
                member_path = (resolved_extract_path / member.name).resolve()
                if not str(member_path).startswith(str(resolved_extract_path)):
                    raise PermissionError(
                        f"Path traversal attempt in tar file: {member.name}"
                    )
            tar.extractall(path=extract_path)

        return extract_path
