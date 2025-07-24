import pathlib
import tarfile as tar
from typing import Optional, Sequence, Union

import requests

from vscode_tunnel_manager.email_manager import EmailManager
from vscode_tunnel_manager.utils.logger import setup_logger

logger = setup_logger(name=__name__)

_DEFAULT_VSCODE_CLI_URL = (
    "https://code.visualstudio.com/sha/download?build=stable&os=cli-alpine-x64"
)
_DEFAULT_VSCODE_CLI_OUTPUT = "vscode_cli.tar.gz"


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
        url: str = _DEFAULT_VSCODE_CLI_URL,
        output: Union[str, pathlib.Path] = _DEFAULT_VSCODE_CLI_OUTPUT,
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
        if not output_path.name.endswith(".tar.gz"):
            logger.error("Downloaded file is not a tar.gz file: %s", output_path)
            raise ValueError(f"Downloaded file is not a tar.gz file: {output_path}")

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
        safe_members = []
        with tar.open(archive_path, "r:gz") as tar_file:
            resolved_extract_path = extract_path.resolve()
            for member in tar_file.getmembers():
                member_path = (resolved_extract_path / member.name).resolve()
                if not str(member_path).startswith(str(resolved_extract_path)):
                    raise PermissionError(
                        f"Path traversal attempt in tar file: {member.name}"
                    )
                safe_members.append(member)

            tar_file.extractall(path=extract_path, members=safe_members)

        return extract_path

    def start_tunnel(
        self,
        mailer: EmailManager,  # Your EmailManager instance
        batch_lines: int = 20,
        idle_seconds: float = 5.0,
        poll_interval: float = 1.0,
        subject_prefix: str = "[VS Code Tunnel]",
        extra_args: Optional[Sequence[str]] = None,
    ) -> None:
        """
        Start `./code tunnel`, continuously read its combined stdout/stderr,
        and email chunks of the output when either:
        1) the number of buffered lines reaches `batch_lines`, or
        2) no new line has been received for `idle_seconds`.

        Args:
            mailer: An EmailManager instance that handles sending emails.
            batch_lines: Send an email every time this many lines are buffered.
            idle_seconds: Send an email if we receive no new output for this many seconds.
            poll_interval: How frequently (seconds) to check for new output / idle.
            subject_prefix: Prefix added to the email subject.
            extra_args: Extra CLI flags to forward to `code tunnel`.

        Raises:
            FileNotFoundError: If the `code` binary does not exist in working_dir.
        """  # noqa
        import select
        import subprocess
        import time

        code_executable = self.working_dir / "code"
        if not code_executable.is_file():
            logger.error("VS Code CLI executable not found: %s", code_executable)
            raise FileNotFoundError(
                f"VS Code CLI executable not found: {code_executable}"
            )

        # Compose the full command
        cmd = [str(code_executable), "tunnel"]
        if extra_args:
            cmd.extend(extra_args)

        logger.info("Starting VS Code tunnel with command: %s", " ".join(cmd))

        # Start the subprocess (merge stderr into stdout)
        proc = subprocess.Popen(
            cmd,
            cwd=self.working_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,  # decode to str automatically
            bufsize=1,  # line-buffered
            universal_newlines=True,  # ensure text mode
        )

        # Internal state
        buffer: list[str] = []
        last_new_line_ts = time.time()
        batch_idx = 1

        def flush(reason: str, force: bool = False) -> None:
            """Send the currently buffered lines via email (if any)."""
            nonlocal buffer, batch_idx
            if not buffer and not force:
                return
            body = "\n".join(buffer) if buffer else "(no new output)"
            subject = (
                f"{subject_prefix} Batch #{batch_idx} ({len(buffer)} lines) - {reason}"
            )
            ok = mailer.send_text(subject, body)
            if ok:
                logger.info("Email sent: %s", subject)
            else:
                logger.error("Failed to send email: %s", subject)
            buffer.clear()
            batch_idx += 1

        try:
            stdout = proc.stdout
            if stdout is None:
                raise RuntimeError("Failed to capture process stdout.")

            # Main loop: poll for new lines or idle timeout
            while True:
                # If the process has exited and stdout is closed, break out
                if proc.poll() is not None and stdout.closed:
                    break

                # Use select to non-blockingly check for new output
                rlist, _, _ = select.select([stdout], [], [], poll_interval)
                if rlist:
                    # Read one line
                    line = stdout.readline()
                    if line:
                        buffer.append(line.rstrip("\n"))
                        last_new_line_ts = time.time()

                        # Condition 1: enough lines buffered
                        if len(buffer) >= batch_lines:
                            flush(reason="batch_lines")
                    else:
                        # EOF case: if process exited, break after flushing
                        if proc.poll() is not None:
                            break
                else:
                    # No new output in this poll interval; check idle condition
                    now = time.time()
                    if now - last_new_line_ts >= idle_seconds:
                        flush(reason="idle_timeout")

            # Final flush after the process exits
            flush(reason="process_exit", force=True)

        finally:
            # Ensure we clean up the process if still alive
            try:
                if proc.poll() is None:
                    proc.terminate()
                    proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
