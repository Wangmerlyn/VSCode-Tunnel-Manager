import argparse
import os
import pathlib

from vscode_tunnel_manager import VSCodeTunnelManager, VSCodeTunnelManagerConfig
from vscode_tunnel_manager.email_manager import SMTPConfig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="VSCode Tunnel Manager CLI")
    # for the email configuration
    parser.add_argument(
        "--host",
        type=str,
        default="smtp.google.com",
        help="SMTP host for sending emails.",
    )
    parser.add_argument(
        "--port", type=int, default=587, help="SMTP port for sending emails."
    )
    parser.add_argument(
        "--username", type=str, required=True, help="SMTP username for authentication."
    )
    parser.add_argument(
        "--password",
        type=str,
        default=os.getenv("SMTP_PASSWORD", ""),
        help="SMTP password for authentication. This is recommended to be set as an environment variable.",
    )
    parser.add_argument(
        "--use-ssl",
        action="store_true",
        help="Use SSL for SMTP connection (port 465).",
    )
    parser.add_argument(
        "--starttls",
        action="store_true",
        help="Use STARTTLS for SMTP connection (port 587).",
    )
    parser.add_argument(
        "--from-addr",
        type=str,
        required=True,
        help="Email address to send emails from.",
    )
    parser.add_argument(
        "--to-addrs",
        type=str,
        nargs="+",
        required=True,
        help="List of email addresses to send emails to.",
    )
    parser.add_argument(
        "--subject-prefix",
        type=str,
        default="[VS Code Tunnel] ",
        help="Prefix for the subject of the emails.",
    )

    parser.add_argument(
        "--tunnel-name", type=str, default="vscode-tunnel", help="Tunnel name"
    )
    parser.add_argument(
        "--provider",
        type=str,
        choices=["github", "microsoft"],
        default="github",
        help="Authentication provider",
    )
    parser.add_argument(
        "--working-dir", type=pathlib.Path, default=".", help="Working directory"
    )
    parser.add_argument(
        "--batch-lines",
        type=int,
        default=20,
        help="Number of lines to buffer from tunnel logs",
    )
    parser.add_argument(
        "--idle-seconds", type=float, default=5.0, help="Idle threshold in seconds"
    )
    parser.add_argument(
        "--poll-interval", type=float, default=1.0, help="Polling interval in seconds"
    )
    parser.add_argument(
        "--extra-args",
        nargs="*",
        default=None,
        help="Extra args to pass to VS Code tunnel",
    )
    parser.add_argument(
        "--log-file", type=pathlib.Path, default=None, help="Path to log file"
    )
    parser.add_argument(
        "--log-append",
        action="store_true",
        help="Append to log file instead of overwriting",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    tunnel_config = VSCodeTunnelManagerConfig(
        tunnel_name=args.tunnel_name,
        provider=args.provider,
        working_dir=args.working_dir,
        batch_lines=args.batch_lines,
        idle_seconds=args.idle_seconds,
        poll_interval=args.poll_interval,
        subject_prefix=args.subject_prefix,
        extra_args=args.extra_args,
        log_file=args.log_file,
        log_append=args.log_append,
    )

    mailer_config = SMTPConfig(
        host=args.host,
        port=args.port,
        username=args.username,
        password=args.password,
        use_ssl=args.use_ssl,
        starttls=args.starttls,
        from_addr=args.from_addr,
        to_addrs=args.to_addrs,
        subject_prefix=args.subject_prefix,
    )

    manager = VSCodeTunnelManager(mailer_config, tunnel_config=tunnel_config)
    manager.start_tunnel()
