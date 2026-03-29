"""Module centralisé pour les appels IA — Mistral AI.

Un seul endroit pour tous les appels à l'IA.
Gère les retries et le fallback automatiquement.
"""

import time
import structlog
from mistralai import Mistral
from .config import load_config

log = structlog.get_logger()


def appeler_ia(system_prompt: str, user_prompt: str, temperature: float = 0.7, max_tokens: int = 600) -> str:
    """Appelle l'IA Mistral et retourne la réponse texte.

    Gère automatiquement :
    - Retry en cas d'erreur temporaire (3 tentatives)
    - Fallback sur un modèle moins cher si le principal échoue

    Args:
        system_prompt: le contexte / rôle de l'IA
        user_prompt: la demande
        temperature: créativité (0.0 = strict, 1.0 = créatif)
        max_tokens: longueur max de la réponse

    Returns:
        Le texte de la réponse
    """
    cfg = load_config()
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

                # Si rate limit ou erreur temporaire, attendre et réessayer
                if "429" in error_str or "rate" in error_str.lower() or "500" in error_str:
                    time.sleep(2 ** attempt)  # 1s, 2s, 4s
                    continue
                else:
                    # Erreur permanente (mauvaise clé, etc.) → pas de retry
                    break

    raise Exception("L'IA n'a pas pu générer de réponse. Vérifiez votre clé API dans les Réglages.")


def appeler_ia_conversation(system_prompt: str, messages: list, temperature: float = 0.7, max_tokens: int = 600) -> str:
    """Appelle l'IA avec un historique de conversation (pour les corrections).

    Args:
        system_prompt: le contexte / rôle de l'IA
        messages: liste de dicts [{"role": "user/assistant", "content": "..."}]
        temperature: créativité
        max_tokens: longueur max

    Returns:
        Le texte de la réponse
    """
    cfg = load_config()
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
