"""Authentification, gestion des clients et quotas.

Chaque client a :
- Un identifiant unique (username)
- Un mot de passe
- Un quota mensuel (prospects + messages IA)
- Sa propre base de données SQLite (isolation complète)

Les clients sont stockés dans data/clients.json.
"""

import json
import hashlib
import secrets
from pathlib import Path
from datetime import datetime

CLIENTS_FILE = Path(__file__).resolve().parent.parent / "data" / "clients.json"

# Quotas par défaut
DEFAULT_QUOTA_PROSPECTS = 200
DEFAULT_QUOTA_MESSAGES = 200


def _hash_password(password: str, salt: str = "") -> str:
    """Hash un mot de passe avec un sel."""
    if not salt:
        salt = secrets.token_hex(16)
    hashed = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
    return f"{salt}:{hashed}"


def _verify_password(password: str, stored: str) -> bool:
    """Vérifie un mot de passe contre le hash stocké."""
    salt = stored.split(":")[0]
    return _hash_password(password, salt) == stored


def _load_clients() -> dict:
    """Charge la liste des clients."""
    CLIENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if CLIENTS_FILE.exists():
        return json.loads(CLIENTS_FILE.read_text(encoding="utf-8"))
    return {}


def _save_clients(clients: dict):
    """Sauvegarde la liste des clients."""
    CLIENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    CLIENTS_FILE.write_text(json.dumps(clients, indent=2, ensure_ascii=False), encoding="utf-8")


def _current_month() -> str:
    """Retourne le mois courant au format YYYY-MM."""
    return datetime.now().strftime("%Y-%m")


def create_client(username: str, password: str, display_name: str = "") -> bool:
    """Crée un nouveau client. Retourne True si créé, False si existe déjà."""
    clients = _load_clients()
    if username in clients:
        return False

    clients[username] = {
        "password": _hash_password(password),
        "display_name": display_name or username,
        "quota_prospects": DEFAULT_QUOTA_PROSPECTS,
        "quota_messages": DEFAULT_QUOTA_MESSAGES,
        "usage": {},  # {"2026-03": {"prospects": 12, "messages": 24}}
    }
    _save_clients(clients)
    return True


def authenticate(username: str, password: str) -> bool:
    """Vérifie les identifiants d'un client."""
    clients = _load_clients()
    if username not in clients:
        return False
    return _verify_password(password, clients[username]["password"])


def get_client_display_name(username: str) -> str:
    """Retourne le nom d'affichage d'un client."""
    clients = _load_clients()
    if username in clients:
        return clients[username].get("display_name", username)
    return username


def list_clients() -> list:
    """Liste tous les clients (avec quotas et utilisation)."""
    clients = _load_clients()
    month = _current_month()
    result = []
    for k, v in clients.items():
        usage = v.get("usage", {}).get(month, {})
        result.append({
            "username": k,
            "display_name": v.get("display_name", k),
            "quota_prospects": v.get("quota_prospects", DEFAULT_QUOTA_PROSPECTS),
            "quota_messages": v.get("quota_messages", DEFAULT_QUOTA_MESSAGES),
            "used_prospects": usage.get("prospects", 0),
            "used_messages": usage.get("messages", 0),
        })
    return result


def delete_client(username: str) -> bool:
    """Supprime un client."""
    clients = _load_clients()
    if username in clients:
        del clients[username]
        _save_clients(clients)
        return True
    return False


def get_client_db_path(username: str) -> Path:
    """Retourne le chemin de la base de données d'un client."""
    return Path(__file__).resolve().parent.parent / "data" / f"client_{username}.db"


def is_admin(username: str) -> bool:
    """Vérifie si un utilisateur est l'admin."""
    return username == "admin"


def change_password(username: str, new_password: str) -> bool:
    """Change le mot de passe d'un client."""
    clients = _load_clients()
    if username in clients:
        clients[username]["password"] = _hash_password(new_password)
        _save_clients(clients)
        return True
    return False


def update_quota(username: str, quota_prospects: int, quota_messages: int) -> bool:
    """Met à jour le quota d'un client (admin seulement)."""
    clients = _load_clients()
    if username in clients:
        clients[username]["quota_prospects"] = quota_prospects
        clients[username]["quota_messages"] = quota_messages
        _save_clients(clients)
        return True
    return False


def get_usage(username: str) -> dict:
    """Retourne l'utilisation du mois en cours."""
    clients = _load_clients()
    month = _current_month()
    if username in clients:
        usage = clients[username].get("usage", {}).get(month, {})
        return {
            "prospects": usage.get("prospects", 0),
            "messages": usage.get("messages", 0),
            "quota_prospects": clients[username].get("quota_prospects", DEFAULT_QUOTA_PROSPECTS),
            "quota_messages": clients[username].get("quota_messages", DEFAULT_QUOTA_MESSAGES),
        }
    return {"prospects": 0, "messages": 0, "quota_prospects": 0, "quota_messages": 0}


def record_usage(username: str, usage_type: str, count: int = 1) -> bool:
    """Enregistre l'utilisation (prospects ou messages).

    Args:
        username: identifiant du client
        usage_type: "prospects" ou "messages"
        count: nombre à ajouter

    Returns:
        True si le quota n'est pas dépassé, False sinon
    """
    if username == "admin":
        return True  # Admin pas de limite

    clients = _load_clients()
    if username not in clients:
        return False

    month = _current_month()

    # Initialiser usage si besoin
    if "usage" not in clients[username]:
        clients[username]["usage"] = {}
    if month not in clients[username]["usage"]:
        clients[username]["usage"][month] = {"prospects": 0, "messages": 0}

    current = clients[username]["usage"][month].get(usage_type, 0)
    quota_key = f"quota_{usage_type}"
    quota = clients[username].get(quota_key, 200)

    if current + count > quota:
        return False  # Quota dépassé

    clients[username]["usage"][month][usage_type] = current + count
    _save_clients(clients)
    return True


def check_quota(username: str, usage_type: str) -> bool:
    """Vérifie si le client a encore du quota disponible."""
    if username == "admin":
        return True

    usage = get_usage(username)
    quota_key = f"quota_{usage_type}"
    return usage[usage_type] < usage[quota_key]


def ensure_admin_exists():
    """Crée le compte admin s'il n'existe pas (premier lancement)."""
    import os
    clients = _load_clients()
    if "admin" not in clients:
        default_pwd = os.environ.get("ADMIN_PASSWORD", "Admin2024!")
        create_client("admin", default_pwd, "Administrateur")
