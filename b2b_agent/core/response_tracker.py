"""IMAP polling — détection des réponses, extraction du corps, génération A-C-A."""

import re
import imaplib
import email as emaillib
from email.header import decode_header
from datetime import datetime, timedelta
from typing import Optional

import logging

from .config import load_config
from .db import (
    get_prospect_by_email,
    update_prospect_status,
    insert_reply,
    save_draft_response,
    get_prospect_by_id,
)
from .webhook import send_webhook
from .reply_generator import generate_aca_reply

log = logging.getLogger(__name__)


def _decode_subject(subject_raw) -> str:
    """Décode un sujet d'email potentiellement encodé."""
    if not subject_raw:
        return ""
    parts = decode_header(subject_raw)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return " ".join(decoded)


def _extract_body(msg) -> str:
    """Extrait le corps texte d'un email."""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode("utf-8", errors="replace")
        # Fallback HTML
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    html = payload.decode("utf-8", errors="replace")
                    # Strip basique des tags HTML
                    text = re.sub(r'<[^>]+>', ' ', html)
                    text = re.sub(r'\s+', ' ', text).strip()
                    return text
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            return payload.decode("utf-8", errors="replace")
    return ""


def check_replies(since_hours: int = 1, auto_draft: bool = True) -> list[dict]:
    """Vérifie les emails reçus via IMAP, matche avec les prospects,
    et génère automatiquement un brouillon de réponse A-C-A.

    Args:
        since_hours: combien d'heures en arrière vérifier
        auto_draft: si True, génère automatiquement un brouillon A-C-A

    Returns:
        Liste de dicts avec les réponses détectées + brouillons
    """
    cfg = load_config()
    if not cfg.imap_user or not cfg.imap_password:
        log.warning("imap_not_configured")
        return []

    replies = []
    try:
        mail = imaplib.IMAP4_SSL(cfg.imap_host, cfg.imap_port)
        mail.login(cfg.imap_user, cfg.imap_password)
        mail.select("INBOX")

        since_date = (datetime.now() - timedelta(hours=since_hours)).strftime("%d-%b-%Y")
        _, message_ids = mail.search(None, f'(SINCE "{since_date}")')

        for msg_id in message_ids[0].split():
            _, msg_data = mail.fetch(msg_id, "(RFC822)")
            if not msg_data or not msg_data[0]:
                continue

            raw_email = msg_data[0][1]
            msg = emaillib.message_from_bytes(raw_email)

            from_addr = emaillib.utils.parseaddr(msg["From"])[1]
            subject = _decode_subject(msg["Subject"])
            body = _extract_body(msg)

            # Matcher avec un prospect
            prospect = get_prospect_by_email(from_addr)
            if prospect:
                log.info(f"reply_detected from_email={from_addr} subject={subject}")

                # Mettre à jour le statut du prospect
                update_prospect_status(prospect["id"], "replied")

                # Enregistrer la réponse en DB
                reply_id = insert_reply(
                    prospect_id=prospect["id"],
                    from_email=from_addr,
                    subject=subject,
                    body=body,
                )

                reply_info = {
                    "reply_id": reply_id,
                    "prospect_id": prospect["id"],
                    "prospect_name": prospect["name"],
                    "prospect_company": prospect["company"],
                    "from_email": from_addr,
                    "subject": subject,
                    "body": body,
                    "detected_at": datetime.now().isoformat(),
                    "draft": None,
                }

                # Générer automatiquement un brouillon A-C-A
                if auto_draft and cfg.openai_api_key:
                    try:
                        # Recharger le prospect pour avoir le brief
                        full_prospect = get_prospect_by_id(prospect["id"])
                        draft_result = generate_aca_reply(
                            prospect=full_prospect,
                            reply_subject=subject,
                            reply_body=body,
                        )
                        # Stocker le brouillon
                        draft_text = f"Sujet: {draft_result['subject']}\n\n{draft_result['body']}"
                        save_draft_response(reply_id, draft_text)
                        reply_info["draft"] = draft_result
                    except Exception as e:
                        log.warning(f"aca_draft_failed error={e}")

                replies.append(reply_info)

                # Webhook
                if cfg.webhook_url:
                    send_webhook(cfg.webhook_url, {
                        "event": "reply_detected",
                        "data": {
                            k: v for k, v in reply_info.items()
                            if k != "draft"
                        },
                    })

        mail.logout()

    except Exception as e:
        log.error(f"imap_error error={e}")

    return replies


def check_bounces() -> list[dict]:
    """Détecte les bounces via IMAP (emails de retour)."""
    cfg = load_config()
    if not cfg.imap_user or not cfg.imap_password:
        return []

    bounces = []
    try:
        mail = imaplib.IMAP4_SSL(cfg.imap_host, cfg.imap_port)
        mail.login(cfg.imap_user, cfg.imap_password)
        mail.select("INBOX")

        since_date = (datetime.now() - timedelta(hours=24)).strftime("%d-%b-%Y")
        _, message_ids = mail.search(
            None, f'(SINCE "{since_date}" FROM "mailer-daemon")'
        )

        for msg_id in message_ids[0].split():
            _, msg_data = mail.fetch(msg_id, "(RFC822)")
            if not msg_data or not msg_data[0]:
                continue

            raw_email = msg_data[0][1]
            msg = emaillib.message_from_bytes(raw_email)

            body = _extract_body(msg)
            emails_in_body = re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", body)
            for addr in emails_in_body:
                prospect = get_prospect_by_email(addr)
                if prospect:
                    update_prospect_status(prospect["id"], "bounced")
                    bounces.append({
                        "prospect_id": prospect["id"],
                        "email": addr,
                        "detected_at": datetime.now().isoformat(),
                    })
                    log.info(f"bounce_detected email={addr}")

        mail.logout()

    except Exception as e:
        log.error(f"imap_bounce_error error={e}")

    return bounces
