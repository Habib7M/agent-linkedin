"""Module centralisé pour les appels IA — Mistral AI.

Un seul endroit pour tous les appels à l'IA.
Gère les retries, le fallback et les quotas automatiquement.
La clé API est centralisée (pas besoin pour les clients).
"""

import time
import structlog
from mistralai import Mistral
from .config import load_config

log = structlog.get_logger()


def _get_client_id() -> str:
    """Récupère l'ID du client connecté."""
    try:
        import streamlit as st
        return st.session_state.get("client_id", "admin")
    except Exception:
        return "admin"


def _check_and_record_quota() -> bool:
    """Vérifie le quota et enregistre l'utilisation. Retourne True si OK."""
    from .auth import check_quota, record_usage
    client_id = _get_client_id()
    if not check_quota(client_id, "messages"):
        return False
    record_usage(client_id, "messages", 1)
    return True


def appeler_ia(system_prompt: str, user_prompt: str, temperature: float = 0.7, max_tokens: int = 600) -> str:
    """Appelle l'IA Mistral et retourne la réponse texte.

    Gère automatiquement :
    - Vérification du quota mensuel
    - Retry en cas d'erreur temporaire (3 tentatives)
    - Fallback sur un modèle moins cher si le principal échoue
    """
    # Vérifier le quota
    if not _check_and_record_quota():
        raise Exception("Quota mensuel atteint. Contactez l'administrateur pour augmenter votre quota.")

    cfg = load_config()

    if not cfg.mistral_api_key:
        raise Exception("Clé API non configurée. Contactez l'administrateur.")

    client = Mistral(api_key=cfg.mistral_api_key)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    # Essayer le modèle principal, puis le fallback
    models = [cfg.mistral_model, cfg.mistral_fallback_model]

    for model in models:
        for attempt in range(3):
            try:
                response = client.chat.complete(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return response.choices[0].message.content.strip()

            except Exception as e:
                error_str = str(e)
                log.warning("ia_retry", model=model, attempt=attempt + 1, error=error_str)

                if "429" in error_str or "rate" in error_str.lower() or "500" in error_str:
                    time.sleep(2 ** attempt)
                    continue
                else:
                    break

    raise Exception("L'IA n'a pas pu générer de réponse. Réessayez dans quelques instants.")


def appeler_ia_conversation(system_prompt: str, messages: list, temperature: float = 0.7, max_tokens: int = 600) -> str:
    """Appelle l'IA avec un historique de conversation (pour les corrections)."""
    # Vérifier le quota
    if not _check_and_record_quota():
        raise Exception("Quota mensuel atteint. Contactez l'administrateur pour augmenter votre quota.")

    cfg = load_config()

    if not cfg.mistral_api_key:
        raise Exception("Clé API non configurée. Contactez l'administrateur.")

    client = Mistral(api_key=cfg.mistral_api_key)

    full_messages = [{"role": "system", "content": system_prompt}] + messages

    try:
        response = client.chat.complete(
            model=cfg.mistral_model,
            messages=full_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        log.warning("ia_conversation_error", error=str(e))
        raise Exception("L'IA n'a pas pu générer de réponse.")
