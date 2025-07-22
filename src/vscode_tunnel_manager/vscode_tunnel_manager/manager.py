import os
import pathlib
import tarfile
from typing import Union

import requests

from vscode_tunnel_manager.utils.logger import setup_logger

logger = setup_logger(name=__name__)


class VSCodeTunnelManager:
    """
    Manages the CLI interface for the VSCode Tunnel Manager.
    This class handles the command-line interface operations, including
    parsing arguments and executing commands.
    """

    def __init__(self, working_dir: Union[str, pathlib.Path] = ".") -> None:
        self.working_dir = pathlib.Path(working_dir).resolve()
        if not self.working_dir.is_dir():
            logger.error(f"Working directory does not exist: {self.working_dir}")
            raise ValueError(f"Invalid working directory: {self.working_dir}")
        logger.info(
            f"Initialized VSCodeTunnelManager with working dir: {self.working_dir}"
        )
        self.change_working_directory(self.working_dir)

    @staticmethod
    def change_working_directory(new_path: Union[str, pathlib.Path]) -> None:
        """
        Changes the current working directory.

        Args:
            new_path (str | Path): The new directory path to change to.
        """
        new_path = pathlib.Path(new_path)
        if not new_path.is_dir():
            logger.error(f"Directory does not exist: {new_path}")
            return
        logger.info(f"Changing working directory to: {new_path}")
        os.chdir(new_path)
        logger.debug(f"Current working directory is now: {pathlib.Path.cwd()}")

    @staticmethod
    def download_vscode(
        url: str = "https://code.visualstudio.com/sha/download?build=stable&os=cli-alpine-x64",
        output: Union[str, pathlib.Path] = "vscode_cli.tar.gz",
        verify_ssl: bool = True,
        chunk_size: int = 8192,
    ) -> pathlib.Path:
        """
        Downloads the VS Code CLI tarball using a streaming HTTP request.

        Args:
            url (str): The URL to download the file from.
            output (str | Path): Path where the downloaded file should be saved.
            verify_ssl (bool): Whether to verify SSL certificates
            (disable to mimic `curl -k`).
            chunk_size (int): Number of bytes to read per stream chunk.

        Returns:
            pathlib.Path: Path to the downloaded file.
        """
        output_path = pathlib.Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with requests.get(url, stream=True, verify=verify_ssl) as response:
            response.raise_for_status()
            with output_path.open("wb") as file:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:  # filter out keep-alive chunks
                        file.write(chunk)
        if not output_path.is_file():
            logger.error(f"Failed to download VS Code tarball: {output_path}")
            raise FileNotFoundError(f"Downloaded file not found: {output_path}")
        return output_path

    @staticmethod
    def extract_tar_gz(
        archive_path: Union[str, pathlib.Path],
        extract_to: Union[str, pathlib.Path] = ".",
    ) -> pathlib.Path:
        """
        Extracts a .tar.gz archive to the specified directory.

        Args:
            archive_path (str | Path): Path to the .tar.gz file.
            extract_to (str | Path): Directory where the contents will be extracted.

        Returns:
            pathlib.Path: Path to the destination directory.
        """
        archive_path = pathlib.Path(archive_path)
        extract_path = pathlib.Path(extract_to)
        extract_path.mkdir(parents=True, exist_ok=True)

        with tarfile.open(archive_path, "r:gz") as tar:
            # Security: Prevent path traversal attacks by checking each member.
            resolved_extract_path = extract_path.resolve()
            for member in tar.getmembers():
                member_path = (resolved_extract_path / member.name).resolve()
                if not str(member_path).startswith(str(resolved_extract_path)):
                    raise PermissionError(f"Path traversal attempt in tar file: {member.name}")
            tar.extractall(path=extract_path)

        return extract_path
