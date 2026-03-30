"""Configuration centralisée — lit .env en local, st.secrets en prod."""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass


@dataclass
class AppConfig:
    """Toute la config de l'app, chargée depuis env vars."""

    # Mistral AI
    mistral_api_key: str = ""
    mistral_model: str = "mistral-large-latest"
    mistral_fallback_model: str = "mistral-small-latest"

    # SMTP
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_sender_name: str = ""

    # IMAP (réponses)
    imap_host: str = "imap.gmail.com"
    imap_port: int = 993
    imap_user: str = ""
    imap_password: str = ""

    # Webhook
    webhook_url: str = ""

    # App
    app_password: str = ""
    rate_limit_per_hour: int = 50
    min_score: int = 15

    # Contexte métier
    coach_product: str = "Agent de prospection LinkedIn"
    coach_icp: str = "Coachs de vie"
    coach_value_prop: str = "Décrochez 5 à 15 RDV qualifiés par mois sur LinkedIn — sans y passer plus de 30 min/jour, grâce à un agent IA qui prospecte, personnalise et relance à votre place."


def load_config() -> AppConfig:
    """Charge la config depuis les variables d'environnement."""
    cfg = AppConfig()
    env_map = {
        "MISTRAL_API_KEY": "mistral_api_key",
        "MISTRAL_MODEL": "mistral_model",
        "MISTRAL_FALLBACK_MODEL": "mistral_fallback_model",
        "SMTP_HOST": "smtp_host",
        "SMTP_PORT": "smtp_port",
        "SMTP_USER": "smtp_user",
        "SMTP_PASSWORD": "smtp_password",
        "SMTP_SENDER_NAME": "smtp_sender_name",
        "IMAP_HOST": "imap_host",
        "IMAP_PORT": "imap_port",
        "IMAP_USER": "imap_user",
        "IMAP_PASSWORD": "imap_password",
        "WEBHOOK_URL": "webhook_url",
        "APP_PASSWORD": "app_password",
        "RATE_LIMIT_PER_HOUR": "rate_limit_per_hour",
        "MIN_SCORE": "min_score",
        "COACH_PRODUCT": "coach_product",
        "COACH_ICP": "coach_icp",
        "COACH_VALUE_PROP": "coach_value_prop",
    }

    # Essayer st.secrets d'abord (Streamlit Cloud), puis env vars
    secrets = {}
    try:
        import streamlit as st
        secrets = dict(st.secrets)
    except Exception:
        pass

    for env_key, attr in env_map.items():
        val = secrets.get(env_key) or os.getenv(env_key)
        if val is not None:
            current = getattr(cfg, attr)
            if isinstance(current, int):
                val = int(val)
            setattr(cfg, attr, val)

    return cfg
