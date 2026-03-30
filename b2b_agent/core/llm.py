"""Module centralisé pour les appels IA — Mistral AI via API REST.

Un seul endroit pour tous les appels à l'IA.
Gère les retries, le fallback et les quotas automatiquement.
La clé API est centralisée (pas besoin pour les clients).
Utilise httpx au lieu du SDK mistralai pour éviter les problèmes d'installation.
"""

import time
import httpx
import structlog
from .config import load_config

log = structlog.get_logger()

MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"


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


def _call_mistral(api_key: str, model: str, messages: list, temperature: float, max_tokens: int) -> str:
    """Appelle l'API Mistral directement via HTTP."""
    response = httpx.post(
        MISTRAL_API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        timeout=60.0,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"].strip()


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

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    # Essayer le modèle principal, puis le fallback
    models = [cfg.mistral_model, cfg.mistral_fallback_model]

    for model in models:
        for attempt in range(3):
            try:
                return _call_mistral(cfg.mistral_api_key, model, messages, temperature, max_tokens)

            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                log.warning("ia_retry", model=model, attempt=attempt + 1, status=status)

                if status in (429, 500, 502, 503):
                    time.sleep(2 ** attempt)
                    continue
                else:
                    break

            except Exception as e:
                log.warning("ia_retry", model=model, attempt=attempt + 1, error=str(e))
                time.sleep(2 ** attempt)
                continue

    raise Exception("L'IA n'a pas pu générer de réponse. Réessayez dans quelques instants.")


def appeler_ia_conversation(system_prompt: str, messages: list, temperature: float = 0.7, max_tokens: int = 600) -> str:
    """Appelle l'IA avec un historique de conversation (pour les corrections)."""
    # Vérifier le quota
    if not _check_and_record_quota():
        raise Exception("Quota mensuel atteint. Contactez l'administrateur pour augmenter votre quota.")

    cfg = load_config()

    if not cfg.mistral_api_key:
        raise Exception("Clé API non configurée. Contactez l'administrateur.")

    full_messages = [{"role": "system", "content": system_prompt}] + messages

    try:
        return _call_mistral(cfg.mistral_api_key, cfg.mistral_model, full_messages, temperature, max_tokens)
    except Exception as e:
        log.warning("ia_conversation_error", error=str(e))
        raise Exception("L'IA n'a pas pu générer de réponse.")
