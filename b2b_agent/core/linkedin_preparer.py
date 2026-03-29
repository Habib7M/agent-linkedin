"""Préparation des messages LinkedIn — génération + export CSV."""

import csv
import io
from datetime import datetime
from typing import Optional

import structlog

from .models import SendResult

log = structlog.get_logger()


def prepare_linkedin_message(
    prospect: dict,
    message_body: str,
    step: int,
    ab_variant: Optional[str] = None,
) -> SendResult:
    """Prépare un message LinkedIn (pas d'envoi auto — stockage uniquement).

    Args:
        prospect: infos du prospect
        message_body: message généré par le LLM
        step: étape dans la séquence
        ab_variant: variante A/B

    Returns:
        SendResult avec status "ready_to_send"
    """
    log.info(
        "linkedin_prepared",
        prospect=prospect["name"],
        step=step,
        length=len(message_body),
    )

    return SendResult(
        prospect_id=prospect["id"],
        channel="linkedin",
        step=step,
        status="ready_to_send",
        message_subject="",
        message_preview=message_body[:100],
        ab_variant=ab_variant,
    )


def export_linkedin_csv(messages: list[dict]) -> str:
    """Exporte les messages LinkedIn prêts à envoyer en CSV.

    Args:
        messages: liste de dicts avec prospect info + message

    Returns:
        Contenu CSV en string
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Nom", "Entreprise", "URL LinkedIn", "Message", "Étape", "Variante", "Date"
    ])

    for m in messages:
        writer.writerow([
            m.get("name", ""),
            m.get("company", ""),
            m.get("linkedin_url", ""),
            m.get("message", ""),
            m.get("step", ""),
            m.get("variant", ""),
            datetime.now().strftime("%Y-%m-%d %H:%M"),
        ])

    return output.getvalue()
