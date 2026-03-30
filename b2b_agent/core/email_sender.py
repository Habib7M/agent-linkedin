"""Envoi d'emails via SMTP ou SendGrid. Rate limit, retry, bounce handling."""

import smtplib
import time
import random
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Optional

import logging

from .config import load_config
from .models import SendResult

log = logging.getLogger(__name__)


class RateLimiter:
    """Contrôle le débit d'envoi."""

    def __init__(self, max_per_hour: int = 50):
        self.max_per_hour = max_per_hour
        self.sent_timestamps: list[float] = []

    def wait_if_needed(self):
        """Attend si le rate limit est atteint."""
        now = time.time()
        # Nettoyer les timestamps > 1h
        self.sent_timestamps = [t for t in self.sent_timestamps if now - t < 3600]
        if len(self.sent_timestamps) >= self.max_per_hour:
            wait_time = 3600 - (now - self.sent_timestamps[0])
            if wait_time > 0:
                log.info(f"rate_limit_wait seconds={round(wait_time)}")
                time.sleep(wait_time)
        # Jitter 2-10s entre chaque envoi
        jitter = random.uniform(2, 10)
        time.sleep(jitter)
        self.sent_timestamps.append(time.time())


def test_smtp_connection() -> tuple[bool, str]:
    """Teste la connexion SMTP. Retourne (success, message)."""
    cfg = load_config()
    try:
        with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.login(cfg.smtp_user, cfg.smtp_password)
        return True, "Connexion SMTP OK"
    except Exception as e:
        return False, f"Erreur SMTP : {e}"


def send_email(
    to_email: str,
    subject: str,
    body: str,
    prospect_id: str,
    step: int,
    ab_variant: Optional[str] = None,
    rate_limiter: Optional[RateLimiter] = None,
) -> SendResult:
    """Envoie un email avec retry et gestion des erreurs.

    Args:
        to_email: adresse destinataire
        subject: sujet de l'email
        body: corps du message
        prospect_id: ID du prospect
        step: numéro de l'étape dans la séquence
        ab_variant: variante A/B
        rate_limiter: instance RateLimiter partagée

    Returns:
        SendResult avec le statut de l'envoi
    """
    cfg = load_config()

    if rate_limiter:
        rate_limiter.wait_if_needed()

    msg = MIMEMultipart("alternative")
    msg["From"] = f"{cfg.smtp_sender_name} <{cfg.smtp_user}>"
    msg["To"] = to_email
    msg["Subject"] = subject
    msg["List-Unsubscribe"] = f"<mailto:{cfg.smtp_user}?subject=unsubscribe>"
    msg.attach(MIMEText(body, "plain", "utf-8"))

    max_retries = 3
    for attempt in range(max_retries):
        try:
            with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=30) as server:
                server.ehlo()
                server.starttls()
                server.login(cfg.smtp_user, cfg.smtp_password)
                server.send_message(msg)

            log.info(f"email_sent to={to_email} subject={subject} step={step}")
            return SendResult(
                prospect_id=prospect_id,
                channel="email",
                step=step,
                status="sent",
                message_subject=subject,
                message_preview=body[:100],
                ab_variant=ab_variant,
            )

        except smtplib.SMTPRecipientsRefused:
            log.warning(f"email_bounced to={to_email}")
            return SendResult(
                prospect_id=prospect_id,
                channel="email",
                step=step,
                status="bounced",
                message_subject=subject,
                message_preview=body[:100],
                error="Recipient refused (hard bounce)",
                ab_variant=ab_variant,
            )

        except Exception as e:
            wait = (2 ** attempt) + random.uniform(0, 1)
            log.warning(f"email_retry attempt={attempt + 1} error={e} wait={wait}")
            if attempt < max_retries - 1:
                time.sleep(wait)
            else:
                return SendResult(
                    prospect_id=prospect_id,
                    channel="email",
                    step=step,
                    status="failed",
                    message_subject=subject,
                    message_preview=body[:100],
                    error=str(e),
                    ab_variant=ab_variant,
                )

    # Fallback (ne devrait pas arriver)
    return SendResult(
        prospect_id=prospect_id,
        channel="email",
        step=step,
        status="failed",
        message_subject=subject,
        message_preview=body[:100],
        error="Max retries exceeded",
        ab_variant=ab_variant,
    )
