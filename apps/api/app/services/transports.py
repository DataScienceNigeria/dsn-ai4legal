"""What actually carries an outbox event out of the platform.

The outbox, its retries and its dead letter were real from the start. The last
hop was not: it logged. This is that hop.

A transport is chosen by configuration and every one of them, including the
log, reports what it did so the outbox can retry a failure rather than mark a
message sent that never left. Nothing here decides whether a message should be
sent; the connector register did that before the event was queued.
"""

from __future__ import annotations

import json
import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

import httpx

from app.core.config import settings
from app.core.security import sign_webhook

logger = logging.getLogger(__name__)


class DeliveryFailed(RuntimeError):
    """The transport could not deliver. The outbox will try again."""


@dataclass
class Message:
    connector: str
    recipients: list[str]
    subject: str
    body: str
    record_reference: str | None = None
    matter_id: str | None = None


class Transport(Protocol):
    name: str

    def available(self) -> bool: ...

    def send(self, message: Message) -> str: ...


class LogTransport:
    """The honest default.

    It says a message was written to the log, not that it was sent, because a
    queue that reports success for messages nobody received is worse than one
    that never ran.
    """

    name = "log"

    def available(self) -> bool:
        return True

    def send(self, message: Message) -> str:
        logger.info(
            "outbox %s to %s: %s",
            message.connector,
            ", ".join(message.recipients) or "nobody",
            message.subject,
        )
        return "Written to the log. No transport is configured, so nothing was sent."


class SmtpTransport:
    """Plain SMTP with STARTTLS.

    Administrative mail only. Everything routed here is templated and carries
    no legal position, which is what makes automated sending acceptable at all.
    """

    name = "smtp"

    def available(self) -> bool:
        return bool(settings.smtp_host)

    def send(self, message: Message) -> str:
        if not message.recipients:
            return "No recipient was addressed, so nothing was sent."

        mail = EmailMessage()
        mail["From"] = settings.smtp_from
        mail["To"] = ", ".join(message.recipients)
        mail["Subject"] = message.subject
        if message.record_reference:
            mail["X-Record-Reference"] = message.record_reference
        mail.set_content(message.body)

        # Hostname checking and certificate verification are set explicitly.
        # They are already the defaults, and stating them means a later edit
        # has to disable them on purpose rather than by omission.
        context = ssl.create_default_context()
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED

        if settings.smtp_username and not settings.smtp_starttls:
            raise DeliveryFailed(
                "SMTP credentials are configured but STARTTLS is off, so the password "
                "would cross the network in the clear. Enable SMTP_STARTTLS."
            )

        try:
            with smtplib.SMTP(
                settings.smtp_host, settings.smtp_port, timeout=30
            ) as server:
                if settings.smtp_starttls:
                    server.starttls(context=context)
                if settings.smtp_username:
                    server.login(settings.smtp_username, settings.smtp_password)
                server.send_message(mail)
        except (smtplib.SMTPException, OSError) as exc:
            raise DeliveryFailed(f"SMTP refused the message: {exc}") from exc

        return f"Sent to {len(message.recipients)} recipients over SMTP."


class WebhookTransport:
    """An outbound webhook, signed the same way inbound ones are verified.

    This is the route to Teams, Slack or an internal bus, and the signature is
    what lets the receiver tell a real event from a replayed one.
    """

    name = "webhook"

    def available(self) -> bool:
        return bool(settings.dsnlai_webhook_url)

    def send(self, message: Message) -> str:
        payload = json.dumps(
            {
                "connector": message.connector,
                "recipients": message.recipients,
                "subject": message.subject,
                "body": message.body,
                "record_reference": message.record_reference,
                "matter_id": message.matter_id,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode()

        try:
            response = httpx.post(
                settings.dsnlai_webhook_url,
                content=payload,
                headers={
                    "Content-Type": "application/json",
                    "X-DSNLAI-Signature": sign_webhook(
                        payload, settings.dsnlai_webhook_secret or None
                    ),
                },
                timeout=20.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise DeliveryFailed(f"The webhook endpoint refused the event: {exc}") from exc

        return f"Delivered to the webhook endpoint, status {response.status_code}."


TRANSPORTS: dict[str, Transport] = {
    "log": LogTransport(),
    "smtp": SmtpTransport(),
    "webhook": WebhookTransport(),
}


def selected() -> Transport:
    """The configured transport, or the log where it is not usable.

    Falling back is deliberate and visible: the message says the transport was
    not configured rather than claiming delivery.
    """
    transport = TRANSPORTS.get(settings.dsnlai_notify_transport)
    if transport is None or not transport.available():
        return TRANSPORTS["log"]
    return transport


def send(message: Message) -> str:
    return selected().send(message)
