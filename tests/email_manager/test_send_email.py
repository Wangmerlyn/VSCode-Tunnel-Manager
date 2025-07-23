from unittest.mock import MagicMock, patch

from vscode_tunnel_manager.vscode_tunnel_manager.email_manager import (
    EmailManager,
    SMTPConfig,
)


def smtp_config() -> SMTPConfig:
    return SMTPConfig(
        host="smtp.example.com",
        port=587,
        username="user@example.com",
        password="secret",
        starttls=True,
        use_ssl=False,
        from_addr="sender@example.com",
        to_addrs=["receiver@example.com"],
        subject_prefix="[Test] ",
    )


def test_send_text_email(smtp_config: SMTPConfig) -> None:
    email_mgr = EmailManager(smtp_config)

    with patch("smtplib.SMTP") as mock_smtp:
        instance = MagicMock()
        mock_smtp.return_value.__enter__.return_value = instance

        result = email_mgr.send_text("Hello", "This is a test email.")

        assert result is True
        instance.starttls.assert_called()
        instance.login.assert_called_with("user@example.com", "secret")
        instance.send_message.assert_called_once()
