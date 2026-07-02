"""Email client for sending newsletters via SMTP."""

from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass, field
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from string import Template
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class EmailClient:
    """Send HTML newsletters through SMTP.

    Parameters
    ----------
    smtp_host:
        SMTP server hostname.
    smtp_port:
        SMTP server port (typically 587 for TLS, 465 for SSL).
    username:
        SMTP login username.
    password:
        SMTP login password.
    use_tls:
        Whether to issue STARTTLS (port 587).  For implicit SSL (465) set this
        to ``False`` and the client will connect over SSL directly.
    from_email:
        Default sender address.
    from_name:
        Default sender display name.
    """

    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    username: str = ""
    password: str = ""
    use_tls: bool = True
    from_email: str = ""
    from_name: str = "Content Agent"

    # ------------------------------------------------------------------
    # Template storage
    # ------------------------------------------------------------------

    _templates: dict[str, str] = field(default_factory=dict, repr=False)

    def create_template(self, name: str, html: str) -> str:
        """Register an HTML template by name.

        The *html* may contain ``$variable`` placeholders (Python Template
        syntax).  Returns the template name for convenience.
        """
        # Validate that it compiles
        Template(html)
        self._templates[name] = html
        logger.debug("Template '%s' registered (%d chars)", name, len(html))
        return name

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    def _build_message(
        self,
        to_email: str,
        subject: str,
        html_body: str,
    ) -> MIMEMultipart:
        msg = MIMEMultipart("alternative")
        msg["From"] = f"{self.from_name} <{self.from_email}>"
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(html_body, "html", "utf-8"))
        return msg

    def _connect(self) -> smtplib.SMTP:
        """Open an SMTP connection."""
        logger.debug("Connecting to %s:%s (tls=%s)", self.smtp_host, self.smtp_port, self.use_tls)
        if self.use_tls:
            server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30)
            server.ehlo()
            server.starttls()
            server.ehlo()
        else:
            server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=30)
        if self.username:
            server.login(self.username, self.password)
        return server

    def send_newsletter(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        *,
        template_name: str = "",
        template_vars: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Send a single HTML newsletter email.

        If *template_name* is given, *html_body* is treated as the subject and
        the registered template is rendered with *template_vars*.
        """
        body = html_body
        if template_name:
            tpl = self._templates.get(template_name)
            if tpl is None:
                raise ValueError(f"Unknown template: {template_name}")
            body = tpl.safe_substitute(template_vars or {})

        msg = self._build_message(to_email, subject, body)
        try:
            with self._connect() as server:
                server.sendmail(self.from_email, to_email, msg.as_string())
            logger.info("Newsletter sent to %s", to_email)
            return {"ok": True, "to": to_email}
        except Exception as exc:
            logger.error("Failed to send to %s: %s", to_email, exc)
            return {"ok": False, "to": to_email, "error": str(exc)}

    def send_bulk(
        self,
        recipients: list[str],
        subject: str,
        html_body: str,
        *,
        template_name: str = "",
        template_vars: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Send a newsletter to multiple recipients.

        Uses a single SMTP connection for efficiency.
        """
        body = html_body
        if template_name:
            tpl = self._templates.get(template_name)
            if tpl is None:
                raise ValueError(f"Unknown template: {template_name}")
            body = tpl.safe_substitute(template_vars or {})

        sent = 0
        failed = 0
        errors: list[str] = []
        try:
            with self._connect() as server:
                for addr in recipients:
                    msg = self._build_message(addr, subject, body)
                    try:
                        server.sendmail(self.from_email, addr, msg.as_string())
                        sent += 1
                    except smtplib.SMTPRecipientsRefused as exc:
                        failed += 1
                        errors.append(f"{addr}: {exc}")
                        logger.warning("Recipient refused: %s", addr)
        except Exception as exc:
            logger.error("Bulk send connection error: %s", exc)
            return {
                "ok": False,
                "sent": sent,
                "failed": len(recipients) - sent,
                "error": str(exc),
            }

        summary: dict[str, Any] = {
            "ok": failed == 0,
            "sent": sent,
            "failed": failed,
            "total": len(recipients),
        }
        if errors:
            summary["errors"] = errors
        logger.info("Bulk send: %s", summary)
        return summary

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def list_templates(self) -> list[str]:
        """Return registered template names."""
        return list(self._templates.keys())

    def remove_template(self, name: str) -> bool:
        """Remove a template by name. Returns True if it existed."""
        if name in self._templates:
            del self._templates[name]
            return True
        return False
