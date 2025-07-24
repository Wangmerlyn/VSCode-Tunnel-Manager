import os
import pathlib
import select
import subprocess
import tarfile as tar
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Sequence, Union

import requests

from vscode_tunnel_manager.email_manager import EmailManager, SMTPConfig
from vscode_tunnel_manager.utils.logger import setup_logger

logger = setup_logger(name=__name__)

_DEFAULT_VSCODE_CLI_URL = (
    "https://code.visualstudio.com/sha/download?build=stable&os=cli-alpine-x64"
)
_DEFAULT_VSCODE_CLI_OUTPUT = "vscode_cli.tar.gz"


@dataclass
class VSCodeTunnelManagerConfig:
    tunnel_name: str = "vscode-tunnel"
    # choice of authentication
    #  - "github" (default): use GitHub Device Code flow
    #  - "microsoft": no authentication, open tunnel to localhost
    provider: str = "github"
    working_dir: Union[str, pathlib.Path] = "."
    batch_lines: int = 20
    idle_seconds: float = 5.0
    poll_interval: float = 1.0
    subject_prefix: str = "[VS Code Tunnel]"
    extra_args: Optional[Sequence[str]] = None
    log_file: Optional[Union[str, pathlib.Path]] = None
    log_append: bool = True

    def __post_init__(self) -> None:
        assert self.provider in ["github", "microsoft"], (
            f"Invalid provider: {self.provider}. Must be 'github' or 'microsoft'."
        )


class VSCodeTunnelManager:
    """
    Manages the CLI interface for the VSCode Tunnel Manager.

    This class provides utilities to download and extract the VS Code CLI
    without mutating global process state (i.e., without calling os.chdir()).
    """

    def __init__(
        self,
        mailer_config: Optional[SMTPConfig],
        tunnel_config: VSCodeTunnelManagerConfig = VSCodeTunnelManagerConfig(),
    ) -> None:
        self.mailer = EmailManager(mailer_config) if mailer_config else None
        if mailer_config and self.mailer:
            is_successful = self.mailer.send_text(
                f"VS Code Tunnel Manager {tunnel_config.tunnel_name} Initialized",
                body=f"Tunnel Manager initialized with working directory: {tunnel_config.working_dir}",
                to_addrs=mailer_config.to_addrs,
            )
            if not is_successful:
                logger.error(
                    "Failed to send initialization email, using print instead."
                )
                self.mailer = None
        self.tunnel_config = tunnel_config
        self.working_dir = pathlib.Path(tunnel_config.working_dir).resolve()
        os.makedirs(self.working_dir, exist_ok=True)
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

    def tunnel_login(
        self,
        tunnel_name: str = "vscode-tunnel",
        batch_lines: int = 20,
        idle_seconds: float = 5.0,
        poll_interval: float = 1.0,
        subject_prefix: str = "[VS Code Tunnel]",
        extra_args: Optional[Sequence[str]] = None,
        log_file: Optional[Union[str, pathlib.Path]] = None,
        log_append: bool = True,
    ) -> None:
        """
        Start `./code tunnel`, continuously read its combined stdout/stderr,
        and email chunks of the output when either:
        1) the number of buffered lines reaches `batch_lines`, or
        2) no new line has been received for `idle_seconds`.

        Meanwhile, stream every output line to a dedicated log file for debugging.
        Additionally, automatically send Down-Arrow key(s) + Enter to the process'
        stdin once after start, and again on every flush.
        """  # noqa: D401

        # ---- internal constants you asked to hard-code ----
        DOWN_PRESSES = 0  # how many times to press Arrow-Down
        SEND_KEYS_ON_FLUSH = False  # also send on every flush
        # ---------------------------------------------------

        mailer = self.mailer
        code_executable = self.working_dir / "code"
        if not code_executable.is_file():
            logger.error("VS Code CLI executable not found: %s", code_executable)
            raise FileNotFoundError(
                f"VS Code CLI executable not found: {code_executable}"
            )

        # Resolve log file path
        if log_file is None:
            log_path = self.working_dir / "vscode_tunnel_runtime.log"
        else:
            log_path = pathlib.Path(log_file)
            if not log_path.is_absolute():
                log_path = (self.working_dir / log_path).resolve()
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # Compose the full command
        cmd = [
            str(code_executable),
            "tunnel",
            "user",
            "login",
            "--provider",
            self.tunnel_config.provider,
        ]
        if extra_args:
            cmd.extend(extra_args)

        logger.info("Starting VS Code tunnel with command: %s", " ".join(cmd))
        logger.info("Streaming tunnel output to log file: %s", log_path)

        # Start the subprocess (merge stderr into stdout; enable stdin)
        proc = subprocess.Popen(
            cmd,
            cwd=self.working_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )

        # Open the log file
        mode = "a" if log_append else "w"
        f_log = log_path.open(mode, encoding="utf-8", buffering=1)

        buffer: list[str] = []
        last_new_line_ts = time.time()
        batch_idx = 1

        def write_log_line(raw_line: str) -> None:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            try:
                f_log.write(f"[{ts}] {raw_line}\n")
            except Exception as e:
                logger.exception("Failed to write line to log file: %s", e)

        def _write_to_stdin(p: subprocess.Popen[str], payload: str) -> None:
            if p.stdin is None:
                logger.warning("stdin is not available for the tunnel process.")
                return
            try:
                p.stdin.write(payload)
                p.stdin.flush()
                logger.info(
                    "Wrote to tunnel stdin: %r",
                    payload.encode("unicode_escape").decode(),
                )
            except BrokenPipeError:
                logger.warning("Tunnel process stdin is closed (BrokenPipeError).")
            except Exception as e:
                logger.exception("Failed to write to tunnel stdin: %s", e)

        def _send_down_and_enter() -> None:
            # Arrow Down = \x1b[B, Enter = \r
            seq = "\x1b[B" * DOWN_PRESSES + "\r"
            _write_to_stdin(proc, seq)

        def flush(reason: str, force: bool = False) -> None:
            nonlocal buffer, batch_idx
            if not buffer and not force:
                if SEND_KEYS_ON_FLUSH:
                    _send_down_and_enter()
                return

            body = "\n".join(buffer) if buffer else "(no new output)"
            subject = f"{subject_prefix}[{tunnel_name}] Batch #{batch_idx} ({len(buffer)} lines) - {reason}"
            if mailer is None:
                print(body)
            else:
                ok = mailer.send_text(subject, body)
                if ok:
                    logger.info("Email sent: %s", subject)
                else:
                    logger.error("Failed to send email: %s", subject)

            if SEND_KEYS_ON_FLUSH:
                _send_down_and_enter()

            buffer.clear()
            batch_idx += 1

        try:
            stdout = proc.stdout
            if stdout is None:
                raise RuntimeError("Failed to capture process stdout.")

            while True:
                if proc.poll() is not None and stdout.closed:
                    break

                rlist, _, _ = select.select([stdout], [], [], poll_interval)
                if rlist:
                    line = stdout.readline()
                    if line:
                        clean_line = line.rstrip("\n")
                        buffer.append(clean_line)
                        write_log_line(clean_line)
                        last_new_line_ts = time.time()

                        if len(buffer) >= batch_lines:
                            flush(reason="batch_lines")
                    else:
                        if proc.poll() is not None:
                            break
                else:
                    now = time.time()
                    if now - last_new_line_ts >= idle_seconds:
                        flush(reason="idle_timeout")

            flush(reason="process_exit", force=True)

        finally:
            try:
                f_log.flush()
                f_log.close()
            except Exception:
                pass

            try:
                if proc.stdin:
                    proc.stdin.close()
            except Exception:
                pass

            try:
                if proc.poll() is None:
                    proc.terminate()
                    proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def tunnel_rename(self, new_name: str) -> None:
        cmd = [
            str(self.working_dir / "code"),
            "tunnel",
            "rename",
            f'"{new_name}"',
        ]
        logger.info("Renaming tunnel with command: %s", " ".join(cmd))
        proc = subprocess.run(
            cmd,
            cwd=self.working_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if proc.returncode != 0:
            logger.error(
                "Failed to rename tunnel: %s\n%s",
                proc.stderr.strip(),
                proc.stdout.strip(),
            )
            raise RuntimeError(f"Failed to rename tunnel: {proc.stderr.strip()}")

    def tunnel_start(self) -> None:
        cmd = [
            str(self.working_dir / "code"),
            "tunnel",
        ]
        logger.info("Starting tunnel with command: %s", " ".join(cmd))
        proc = subprocess.run(
            cmd,
            cwd=self.working_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if proc.returncode != 0:
            logger.error(
                "Failed to start tunnel: %s\n%s",
                proc.stderr.strip(),
                proc.stdout.strip(),
            )
            raise RuntimeError(f"Failed to start tunnel: {proc.stderr.strip()}")

    def run(self) -> None:
        if not self.working_dir.is_dir():
            os.makedirs(self.working_dir, exist_ok=True)
        logger.info(
            "VSCodeTunnelManager is running with working dir: %s", self.working_dir
        )
        # check if the VS Code CLI is already downloaded
        vscode_tar_gz = self.working_dir / _DEFAULT_VSCODE_CLI_OUTPUT
        if not vscode_tar_gz.is_file():
            logger.info("Downloading VS Code CLI...")
            self.download_vscode()
        else:
            logger.info("VS Code CLI already downloaded: %s", vscode_tar_gz)
        if not (self.working_dir / "code").is_file():
            logger.info("Extracting VS Code CLI...")
            self.extract_tar_gz(vscode_tar_gz)
        else:
            logger.info("VS Code CLI already extracted.")
        self.tunnel_login(
            tunnel_name=self.tunnel_config.tunnel_name,
            batch_lines=self.tunnel_config.batch_lines,
            idle_seconds=self.tunnel_config.idle_seconds,
            poll_interval=self.tunnel_config.poll_interval,
            subject_prefix=self.tunnel_config.subject_prefix,
            extra_args=self.tunnel_config.extra_args,
            log_file=self.tunnel_config.log_file,
            log_append=self.tunnel_config.log_append,
        )
        time.sleep(3)  # give some time for the tunnel to stabilize
        import pdb

        pdb.set_trace()  # noqa: T201
        self.tunnel_rename(self.tunnel_config.tunnel_name)
        self.tunnel_start()
