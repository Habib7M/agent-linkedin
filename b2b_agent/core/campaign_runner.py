"""Orchestrateur de campagne — exécute la séquence complète avec personnalisation profonde."""

import random
from datetime import datetime
from typing import Optional, Callable

import logging

from .config import load_config
from .db import (
    get_eligible_prospects,
    update_prospect_status,
    insert_send_result,
)
from .scorer import score_all_prospects
from .profile_analyzer import generate_personalization_brief
from .message_generator import generate_message
from .email_sender import send_email, RateLimiter
from .linkedin_preparer import prepare_linkedin_message

log = logging.getLogger(__name__)

# 🔧 CUSTOMIZE: séquence de prospection
SEQUENCE = [
    {"step": 1, "day": 0, "channel": "linkedin", "template": "cold"},
    {"step": 2, "day": 3, "channel": "email", "template": "cold"},
    {"step": 3, "day": 7, "channel": "linkedin", "template": "followup"},
    {"step": 4, "day": 14, "channel": "email", "template": "breakup"},
]


def run_campaign(
    min_score: int = 40,
    rate_limit: int = 50,
    dry_run: bool = True,
    progress_callback: Optional[Callable] = None,
) -> dict:
    """Lance une campagne de prospection avec personnalisation profonde.

    Pipeline par prospect :
    1. Scorer → éligibilité
    2. Analyser le profil → brief de personnalisation (stocké en DB, réutilisé)
    3. Générer le message → injecte brief + template + profil complet
    4. Envoyer (email) ou préparer (LinkedIn)

    Args:
        min_score: score minimum pour être contacté
        rate_limit: emails par heure
        dry_run: si True, génère sans envoyer
        progress_callback: fonction appelée avec (current, total, message)

    Returns:
        dict avec les stats de la campagne
    """
    log.info(f"campaign_start min_score={min_score} dry_run={dry_run}")

    # 1. Scorer tous les prospects
    score_all_prospects()

    # 2. Récupérer les éligibles
    prospects = get_eligible_prospects(min_score)
    total = len(prospects)

    if total == 0:
        return {"total": 0, "sent": 0, "failed": 0, "skipped": 0, "messages": []}

    rate_limiter = RateLimiter(max_per_hour=rate_limit)

    stats = {"total": total, "sent": 0, "failed": 0, "skipped": 0, "messages": []}

    for i, prospect in enumerate(prospects):
        current_step = prospect.get("current_step", 0)
        next_step_info = None

        # Trouver la prochaine étape
        for seq in SEQUENCE:
            if seq["step"] > current_step:
                next_step_info = seq
                break

        if not next_step_info:
            stats["skipped"] += 1
            continue

        # A/B variant (assigné une fois, conservé)
        variant = prospect.get("ab_variant") or random.choice(["a", "b"])

        channel = next_step_info["channel"]
        step_name = next_step_info["template"]
        step_num = next_step_info["step"]

        if progress_callback:
            progress_callback(
                i + 1, total,
                f"[{i+1}/{total}] {prospect['name']} — analyse profil + {channel} {step_name}"
            )

        # Vérifier si le canal est disponible
        if channel == "email" and not prospect.get("email"):
            stats["skipped"] += 1
            continue
        if channel == "linkedin" and not prospect.get("linkedin_url"):
            if prospect.get("email") and next_step_info["template"] in ("cold", "followup"):
                channel = "email"
            else:
                stats["skipped"] += 1
                continue

        # Générer le brief de personnalisation (si pas déjà fait)
        # Le brief est généré 1 fois et réutilisé pour toute la séquence
        if not prospect.get("personalization_brief"):
            try:
                if progress_callback:
                    progress_callback(
                        i + 1, total,
                        f"[{i+1}/{total}] {prospect['name']} — 🔍 analyse du profil..."
                    )
                generate_personalization_brief(prospect)
            except Exception as e:
                log.warning(f"brief_generation_failed prospect={prospect['name']} error={e}")
                # Continue quand même — le message sera moins personnalisé

        # Générer le message
        try:
            if progress_callback:
                progress_callback(
                    i + 1, total,
                    f"[{i+1}/{total}] {prospect['name']} — ✍️ rédaction {channel} {step_name}..."
                )
            result = generate_message(
                prospect=prospect,
                channel=channel,
                step=step_name,
                variant=variant,
                dry_run=dry_run,
            )
        except Exception as e:
            log.error(f"generation_error prospect={prospect['name']} error={e}")
            stats["failed"] += 1
            continue

        msg_info = {
            "prospect_name": prospect["name"],
            "company": prospect["company"],
            "channel": channel,
            "step": step_name,
            "variant": variant,
            "subject": result.get("subject", ""),
            "body": result.get("body", ""),
            "brief": result.get("brief", ""),
            "issues": result.get("issues", []),
        }

        if dry_run:
            stats["sent"] += 1
            stats["messages"].append(msg_info)
            continue

        # Envoyer
        if channel == "email":
            send_result = send_email(
                to_email=prospect["email"],
                subject=result["subject"],
                body=result["body"],
                prospect_id=prospect["id"],
                step=step_num,
                ab_variant=variant,
                rate_limiter=rate_limiter,
            )
        else:
            send_result = prepare_linkedin_message(
                prospect=prospect,
                message_body=result["body"],
                step=step_num,
                ab_variant=variant,
            )

        # Enregistrer
        insert_send_result(send_result)

        if send_result.status in ("sent", "ready_to_send"):
            update_prospect_status(
                prospect["id"],
                "contacted",
                current_step=step_num,
                ab_variant=variant,
                last_contacted_at=datetime.now().isoformat(),
            )
            stats["sent"] += 1
        elif send_result.status == "bounced":
            update_prospect_status(prospect["id"], "bounced")
            stats["failed"] += 1
        else:
            stats["failed"] += 1

        stats["messages"].append(msg_info)

    log.info(f"campaign_done {' '.join(f'{k}={v}' for k, v in stats.items() if k != 'messages')}")
    return stats
