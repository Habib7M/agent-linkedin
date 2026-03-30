"""Envoi de webhooks asynchrones."""

import httpx
import logging

log = logging.getLogger(__name__)


def send_webhook(url: str, payload: dict):
    """Envoie un webhook POST de manière non-bloquante.

    Args:
        url: URL du webhook (Zapier, Make, etc.)
        payload: données JSON à envoyer
    """
    if not url:
        return

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(url, json=payload)
            log.info(f"webhook_sent url={url} status={resp.status_code}")
    except Exception as e:
        log.error(f"webhook_error url={url} error={e}")
