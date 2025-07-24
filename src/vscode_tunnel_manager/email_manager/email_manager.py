import mimetypes
import os
import pathlib
import random
import re
import smtplib
import ssl
import threading
import time
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Iterable, Optional, Sequence

from vscode_tunnel_manager.utils.logger import setup_logger

logger = setup_logger(__name__)


@dataclass
class SMTPConfig:
    host: str
    port: int
    username: str
    password: str = os.getenv("SMTP_PASSWORD", "")
    use_ssl: bool = False  # SMTPS port 465
    starttls: bool = True  # SMTP + STARTTLS port 587
    from_addr: str = ""
    to_addrs: Sequence[str] = field(default_factory=list)
    subject_prefix: str = ""  # Optional subject prefix for all emails


class EmailManager:
    """Simple and robust email sender with retry support, attachments, and thread safety."""  # noqa: E501

    def __init__(
        self, config: SMTPConfig, max_retries: int = 3, base_backoff: float = 1.0
    ):
        self.cfg = config
        self.max_retries = max_retries
        self.base_backoff = base_backoff
        self._lock = threading.Lock()

        if not self.cfg.from_addr:
            self.cfg.from_addr = self.cfg.username

    def send_text(
        self, subject: str, body: str, to_addrs: Optional[Iterable[str]] = None
    ) -> bool:
        """Send plain text email"""
        return self._send(subject, body, to_addrs=to_addrs)

    def send_html(
        self,
        subject: str,
        html: str,
        text_fallback: str = "",
        to_addrs: Optional[Iterable[str]] = None,
    ) -> bool:
        """Send HTML email with optional plain text fallback"""
        return self._send(
            subject,
            text_fallback or self._html2text(html),
            html=html,
            to_addrs=to_addrs,
        )

    def send_with_attachments(
        self,
        subject: str,
        body: str,
        attachments: Iterable[str | pathlib.Path],
        html: Optional[str] = None,
        to_addrs: Optional[Iterable[str]] = None,
    ) -> bool:
        """Send email with attachments"""
        return self._send(
            subject, body, html=html, attachments=attachments, to_addrs=to_addrs
        )

    # -------------------- Internal Implementation --------------------

    def _send(
        self,
        subject: str,
        text: str,
        html: Optional[str] = None,
        attachments: Optional[Iterable[str | pathlib.Path]] = None,
        to_addrs: Optional[Iterable[str]] = None,
    ) -> bool:
        msg = self._build_message(subject, text, html, attachments, to_addrs)

        # Prevent multiple threads from connecting/sending simultaneously
        with self._lock:
            for attempt in range(1, self.max_retries + 1):
                try:
                    self._smtp_send(msg)
                    return True
                except Exception as e:
                    if attempt == self.max_retries:
                        logger.error(
                            f"[EmailManager] Send failed after {attempt} attempts: {e}"
                        )
                        return False
                    sleep_t = self.base_backoff * (2 ** (attempt - 1)) + random.random()
                    time.sleep(sleep_t)
        return False

    def _smtp_send(self, msg: EmailMessage) -> None:
        if self.cfg.use_ssl:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(
                self.cfg.host, self.cfg.port, context=context
            ) as server:
                server.login(self.cfg.username, self.cfg.password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(self.cfg.host, self.cfg.port, timeout=30) as server:
                if self.cfg.starttls:
                    context = ssl.create_default_context()
                    server.starttls(context=context)
                server.login(self.cfg.username, self.cfg.password)
                server.send_message(msg)

    def _build_message(
        self,
        subject: str,
        text: str,
        html: Optional[str],
        attachments: Optional[Iterable[str | pathlib.Path]],
        to_addrs: Optional[Iterable[str]],
    ) -> EmailMessage:
        to_list = list(to_addrs) if to_addrs else list(self.cfg.to_addrs)
        if not to_list:
            raise ValueError("No recipient specified")

        msg = EmailMessage()
        msg["From"] = self.cfg.from_addr
        msg["To"] = ", ".join(to_list)
        msg["Subject"] = f"{self.cfg.subject_prefix}{subject}"

        if html:
            # Add both plain text and HTML parts
            msg.set_content(text or "See HTML part.")
            msg.add_alternative(html, subtype="html")
        else:
            msg.set_content(text)

        if attachments:
            for path in attachments:
                path = pathlib.Path(path)
                ctype, encoding = mimetypes.guess_type(path.name)
                if ctype is None or encoding is not None:
                    ctype = "application/octet-stream"
                maintype, subtype = ctype.split("/", 1)
                with open(path, "rb") as f:
                    msg.add_attachment(
                        f.read(), maintype=maintype, subtype=subtype, filename=path.name
                    )
        return msg

    @staticmethod
    def _html2text(html: str) -> str:
        """Minimal HTML to plain text conversion (can be replaced with html2text library)"""  # noqa: E501

        txt = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
        txt = re.sub(r"<[^>]+>", "", txt)
        return txt.strip()
